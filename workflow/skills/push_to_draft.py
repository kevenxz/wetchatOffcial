"""Workflow skill: push generated article to WeChat draft box."""
from __future__ import annotations

import os
import time

import structlog

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


async def push_to_draft_node(state: WorkflowState) -> dict:
    task_id = state["task_id"]
    article = _merge_visual_assets(
        dict(state.get("generated_article") or {}),
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

    app_id = os.getenv("WECHAT_APP_ID")
    app_secret = os.getenv("WECHAT_APP_SECRET")

    if not app_id or not app_secret:
        logger.warning(
            "wechat_api_mock",
            task_id=task_id,
            message="missing WECHAT_APP_ID or WECHAT_APP_SECRET, using mock draft result",
        )
        return {
            "status": "running",
            "current_skill": "push_to_draft",
            "progress": 95,
            "draft_info": {
                "media_id": "mock_media_id_12345",
                "url": "https://mp.weixin.qq.com/mock_draft_preview",
            },
        }

    try:
        draft_info = await push_article_to_wechat_draft(article=article, app_id=app_id, app_secret=app_secret)
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
        )
        return {
            "status": "failed",
            "current_skill": "push_to_draft",
            "error": error_msg,
        }

    duration_ms = round((time.monotonic() - start_time) * 1000)
    logger.info(
        "skill_done",
        task_id=task_id,
        skill="push_to_draft",
        status="done",
        duration_ms=duration_ms,
        media_id=draft_info.get("media_id"),
    )

    return {
        "status": "running",
        "current_skill": "push_to_draft",
        "progress": 95,
        "draft_info": draft_info,
    }
