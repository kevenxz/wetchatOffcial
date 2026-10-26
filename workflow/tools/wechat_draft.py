"""Workflow skill: push generated article to WeChat draft box.

Targets are bound to the task at creation time (``publish_targets``). Global
``WECHAT_APP_ID``/``WECHAT_APP_SECRET`` remain only as a fallback for installs
without configured accounts, and every fallback or mock result is explicitly
marked so an operator never mistakes it for a real delivery.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone

import structlog

from api.store import get_account, resolve_theme_style
from workflow.state import WorkflowState
from workflow.utils.wechat_draft_service import push_article_to_wechat_draft

logger = structlog.get_logger(__name__)


def _asset_ref(asset: dict) -> str:
    return str(asset.get("url") or asset.get("path") or "").strip()


def _merge_visual_assets(article: dict, visual_state: dict) -> dict:
    merged_article = dict(article)
    if merged_article.get("cover_image") and merged_article.get("illustrations"):
        return merged_article

    assets = list(visual_state.get("assets") or [])
    if not assets:
        return merged_article

    cover_image = str(merged_article.get("cover_image") or "").strip()
    illustrations = [str(item).strip() for item in list(merged_article.get("illustrations") or []) if str(item).strip()]

    for asset in assets:
        if not isinstance(asset, dict):
            continue
        image_ref = _asset_ref(asset)
        if not image_ref:
            continue
        role = str(asset.get("role") or "").strip()
        if not cover_image and role == "cover":
            cover_image = image_ref
            continue
        if image_ref not in illustrations:
            illustrations.append(image_ref)

    if cover_image:
        merged_article["cover_image"] = cover_image
    elif illustrations:
        merged_article["cover_image"] = illustrations[0]

    merged_article["illustrations"] = illustrations
    merged_article["visual_assets"] = assets
    return merged_article


def _publish_policy(state: WorkflowState) -> dict:
    return dict((state.get("config_snapshot") or {}).get("publish_policy") or {})


def _resolve_targets(state: WorkflowState) -> list[dict]:
    """Return the bound publish targets, skipping unknown or disabled accounts."""
    targets: list[dict] = []
    for raw in list(state.get("publish_targets") or []):
        if isinstance(raw, str):
            account_id = raw.strip()
            platform = "wechat_mp"
        elif isinstance(raw, dict):
            account_id = str(raw.get("account_id") or "").strip()
            platform = str(raw.get("platform") or "wechat_mp")
        else:
            continue
        if not account_id:
            continue
        account = get_account(account_id)
        if account is None:
            logger.warning("push_target_account_missing", account_id=account_id)
            continue
        if not account.enabled:
            logger.warning("push_target_account_disabled", account_id=account_id)
            continue
        targets.append(
            {
                "account_id": account.account_id,
                "account_name": account.name,
                "platform": account.platform.value if hasattr(account.platform, "value") else platform,
                "app_id": account.app_id,
                "app_secret": account.app_secret,
            }
        )
    return targets


def _build_record(
    *,
    target: dict | None,
    status: str,
    draft_info: dict | None = None,
    error: str = "",
    theme_name: str = "",
) -> dict:
    payload = draft_info or {}
    return {
        "push_id": f"{target['account_id'] if target else 'env'}-{int(time.time() * 1000)}",
        "account_id": target["account_id"] if target else "",
        "account_name": target["account_name"] if target else "env_fallback",
        "platform": target["platform"] if target else "wechat_mp",
        "pushed_at": datetime.now(tz=timezone.utc).isoformat(),
        "status": status,
        "draft_info": draft_info or None,
        "error": error or None,
        "publish_status": payload.get("publish_status") or ("failed" if status == "failed" else "draft_only"),
        "publish_id": payload.get("publish_id") or "",
        "theme_name": theme_name,
    }


async def _push_to_target(
    article: dict,
    target: dict,
    style_config: dict[str, str],
    theme_name: str,
    publish_policy: dict,
) -> tuple[dict, dict]:
    """Push to one account; returns ``(draft_info, push_record)``."""
    try:
        draft_info = await push_article_to_wechat_draft(
            article=article,
            app_id=target["app_id"],
            app_secret=target["app_secret"],
            style_config=style_config,
            auto_publish=bool(publish_policy.get("auto_publish", False)),
            publish_poll_interval_seconds=float(publish_policy.get("publish_poll_interval_seconds") or 5),
            publish_poll_max_attempts=int(publish_policy.get("publish_poll_max_attempts") or 10),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "push_to_draft_account_failed",
            account_id=target["account_id"],
            error=str(exc),
            exc_info=True,
        )
        return {}, _build_record(target=target, status="failed", error=str(exc), theme_name=theme_name)

    return draft_info, _build_record(
        target=target,
        status="success",
        draft_info=draft_info,
        theme_name=theme_name,
    )


async def push_to_draft_node(state: WorkflowState) -> dict:
    task_id = state["task_id"]
    article = _merge_visual_assets(
        dict(state.get("final_article") or state.get("generated_article") or {}),
        dict(state.get("visual_state") or {}),
    )
    start_time = time.monotonic()

    logger.info("skill_start", task_id=task_id, skill="push_to_draft", status="running")

    if not article:
        duration_ms = round((time.monotonic() - start_time) * 1000)
        error_msg = "no generated article content to push"
        logger.error(
            "skill_failed",
            task_id=task_id,
            skill="push_to_draft",
            status="failed",
            duration_ms=duration_ms,
            error=error_msg,
        )
        return {"status": "failed", "current_skill": "push_to_draft", "error": error_msg}

    publish_policy = _publish_policy(state)
    theme_name, style_config = resolve_theme_style(state.get("article_theme"))
    targets = _resolve_targets(state)

    if targets:
        records: list[dict] = []
        first_success: dict = {}
        for target in targets:
            draft_info, record = await _push_to_target(article, target, style_config, theme_name, publish_policy)
            records.append(record)
            if draft_info and not first_success:
                first_success = draft_info

        duration_ms = round((time.monotonic() - start_time) * 1000)
        if not first_success:
            error_msg = "all bound accounts failed to accept the draft"
            logger.error(
                "skill_failed",
                task_id=task_id,
                skill="push_to_draft",
                status="failed",
                duration_ms=duration_ms,
                error=error_msg,
                target_count=len(targets),
            )
            return {
                "status": "failed",
                "current_skill": "push_to_draft",
                "error": error_msg,
                "publish_records": records,
            }

        logger.info(
            "skill_done",
            task_id=task_id,
            skill="push_to_draft",
            status="done",
            duration_ms=duration_ms,
            target_count=len(targets),
            media_id=first_success.get("media_id"),
            publish_status=first_success.get("publish_status"),
        )
        return {
            "status": "running",
            "current_skill": "push_to_draft",
            "progress": 95,
            "draft_info": first_success,
            "publish_records": records,
        }

    # Fallback path: no accounts bound to this task.
    app_id = os.getenv("WECHAT_APP_ID")
    app_secret = os.getenv("WECHAT_APP_SECRET")

    if not app_id or not app_secret:
        logger.warning(
            "wechat_api_mock",
            task_id=task_id,
            message="no bound publish target and no WECHAT_APP_ID/WECHAT_APP_SECRET; returning a mock draft",
        )
        mock_draft = {
            "media_id": "mock_media_id_12345",
            "url": "https://mp.weixin.qq.com/mock_draft_preview",
            "publish_status": "draft_only",
            "publish_id": "",
            "publish_error": "",
            "mock": True,
            "source": "mock",
        }
        return {
            "status": "running",
            "current_skill": "push_to_draft",
            "progress": 95,
            "draft_info": mock_draft,
            "publish_records": [
                _build_record(target=None, status="success", draft_info=mock_draft, theme_name=theme_name)
            ],
        }

    try:
        draft_info = await push_article_to_wechat_draft(
            article=article,
            app_id=app_id,
            app_secret=app_secret,
            style_config=style_config,
            auto_publish=bool(publish_policy.get("auto_publish", False)),
        )
    except Exception as exc:  # noqa: BLE001
        duration_ms = round((time.monotonic() - start_time) * 1000)
        error_msg = str(exc)
        logger.error(
            "skill_failed",
            task_id=task_id,
            skill="push_to_draft",
            status="failed",
            duration_ms=duration_ms,
            error=error_msg,
            exc_info=True,
        )
        return {
            "status": "failed",
            "current_skill": "push_to_draft",
            "error": error_msg,
            "publish_records": [_build_record(target=None, status="failed", error=error_msg, theme_name=theme_name)],
        }

    draft_info = {**draft_info, "source": "env_fallback"}
    duration_ms = round((time.monotonic() - start_time) * 1000)
    logger.info(
        "skill_done",
        task_id=task_id,
        skill="push_to_draft",
        status="done",
        duration_ms=duration_ms,
        media_id=draft_info.get("media_id"),
        publish_status=draft_info.get("publish_status"),
    )

    return {
        "status": "running",
        "current_skill": "push_to_draft",
        "progress": 95,
        "draft_info": draft_info,
        "publish_records": [_build_record(target=None, status="success", draft_info=draft_info, theme_name=theme_name)],
    }
