"""Reusable service for pushing an article to WeChat draft box.

Covers the whole delivery stage: cover upload, illustration upload, draft creation
and the optional publish step. Draft creation and publishing are retried
independently so a publish failure never forces a duplicate draft.
"""
from __future__ import annotations

import asyncio

import httpx
import structlog

from workflow import runtime_settings
from workflow.utils.markdown_to_wechat import markdown_to_wechat_html
from workflow.utils.wechat_api import upload_article_image, upload_cover_material
from workflow.utils.wechat_publish import (
    WeChatPublishError,
    poll_publish_status,
    publish_failure_reason,
    submit_publish,
)
from workflow.utils.wechat_token import (
    _access_token_cache,  # noqa: F401  (re-exported for existing callers/tests)
    get_access_token,
    invalidate_access_token,
)

logger = structlog.get_logger(__name__)

TOKEN_ERROR_CODES = {40001, 40014, 42001, 42002}
DRAFT_ADD_URL = "https://api.weixin.qq.com/cgi-bin/draft/add"
ILLUSTRATION_UPLOAD_CONCURRENCY = 3


def _resolve_visual_asset_refs(article: dict) -> tuple[list[str], list[str]]:
    cover_candidates: list[str] = []
    illustration_refs: list[str] = [str(item).strip() for item in list(article.get("illustrations", [])) if str(item).strip()]

    cover_image_ref = str(article.get("cover_image", "")).strip()
    if cover_image_ref:
        cover_candidates.append(cover_image_ref)

    visual_assets = list(article.get("visual_assets", []))
    for asset in visual_assets:
        if not isinstance(asset, dict):
            continue
        image_ref = str(asset.get("url") or asset.get("path") or "").strip()
        if not image_ref:
            continue
        role = str(asset.get("role") or "").strip()
        if role == "cover" and image_ref not in cover_candidates:
            cover_candidates.append(image_ref)
            continue
        if image_ref not in illustration_refs:
            illustration_refs.append(image_ref)

    for image_ref in illustration_refs:
        if image_ref not in cover_candidates:
            cover_candidates.append(image_ref)
    return cover_candidates, illustration_refs


async def _get_access_token(app_id: str, app_secret: str, client: httpx.AsyncClient) -> str:
    """Backwards-compatible alias for the shared token cache."""
    return await get_access_token(app_id, app_secret, client)


async def _upload_illustrations(
    client: httpx.AsyncClient,
    illustration_refs: list[str],
    token: str,
) -> list[str]:
    """Upload in-article images concurrently while preserving their order."""
    if not illustration_refs:
        return []

    semaphore = runtime_settings.get_semaphore("wechat_upload", ILLUSTRATION_UPLOAD_CONCURRENCY)

    async def upload_one(image_url: str) -> str:
        async with semaphore:
            return await upload_article_image(client, image_url, token)

    return list(await asyncio.gather(*(upload_one(ref) for ref in illustration_refs)))


async def _submit_draft(
    client: httpx.AsyncClient,
    app_id: str,
    app_secret: str,
    draft_payload: dict,
    *,
    max_retries: int = 3,
) -> str:
    """Create the draft and return its ``media_id``."""
    last_error = ""
    for _attempt in range(1, max(1, max_retries) + 1):
        try:
            current_token = await get_access_token(app_id, app_secret, client)
            response = await client.post(f"{DRAFT_ADD_URL}?access_token={current_token}", json=draft_payload)
            response.raise_for_status()
            payload = response.json()

            errcode = payload.get("errcode", 0)
            if errcode != 0:
                if errcode in TOKEN_ERROR_CODES:
                    await invalidate_access_token(app_id)
                    raise ValueError(f"access token expired: {payload}")
                if errcode == 40007:
                    raise ValueError(f"invalid thumb_media_id for wechat draft add: {payload}")
                raise ValueError(f"wechat draft add failed: {payload}")

            media_id = payload.get("media_id")
            if not media_id:
                raise ValueError(f"wechat draft add missing media_id: {payload}")
            return str(media_id)
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)

    raise ValueError(last_error or "push to wechat draft failed")


async def _publish_draft(
    client: httpx.AsyncClient,
    app_id: str,
    app_secret: str,
    media_id: str,
    result: dict,
    *,
    poll_interval_seconds: float,
    poll_max_attempts: int,
) -> dict:
    """Submit the draft for publishing and poll until it settles."""
    try:
        token = await get_access_token(app_id, app_secret, client)
        publish_id = await submit_publish(client, token, media_id)
    except WeChatPublishError as exc:
        if exc.token_expired:
            await invalidate_access_token(app_id)
        logger.warning("wechat_publish_submit_failed", media_id=media_id, error=str(exc), exc_info=True)
        return {**result, "publish_status": "publish_failed", "publish_error": str(exc)}

    try:
        status = await poll_publish_status(
            client,
            await get_access_token(app_id, app_secret, client),
            publish_id,
            interval_seconds=poll_interval_seconds,
            max_attempts=poll_max_attempts,
        )
    except WeChatPublishError as exc:
        logger.warning("wechat_publish_poll_failed", publish_id=publish_id, error=str(exc), exc_info=True)
        return {
            **result,
            "publish_id": publish_id,
            "publish_status": "publishing",
            "publish_error": str(exc),
        }

    if status.get("published"):
        logger.info("wechat_publish_succeeded", media_id=media_id, publish_id=publish_id)
        return {**result, "publish_id": publish_id, "publish_status": "published", "publish_error": ""}

    if status.get("timed_out"):
        # Still publishing: not a failure, the operator can re-check later.
        return {
            **result,
            "publish_id": publish_id,
            "publish_status": "publishing",
            "publish_error": "",
        }

    reason = publish_failure_reason(status.get("status"))
    logger.warning("wechat_publish_failed", media_id=media_id, publish_id=publish_id, reason=reason)
    return {**result, "publish_id": publish_id, "publish_status": "publish_failed", "publish_error": reason}


async def push_article_to_wechat_draft(
    article: dict,
    app_id: str,
    app_secret: str,
    style_config: dict[str, str] | None = None,
    *,
    auto_publish: bool = False,
    publish_poll_interval_seconds: float = 5.0,
    publish_poll_max_attempts: int = 10,
) -> dict:
    """Push article content to the WeChat draft box and optionally publish it.

    Returns draft info plus a ``publish_status`` of ``draft_only``, ``publishing``,
    ``published`` or ``publish_failed``.
    """
    if not app_id or not app_secret:
        raise ValueError("missing app_id or app_secret")

    if not article:
        raise ValueError("empty article payload")

    async with httpx.AsyncClient(timeout=15.0) as client:
        token = await get_access_token(app_id, app_secret, client)

        cover_candidates, illustration_refs = _resolve_visual_asset_refs(article)

        thumb_media_id = ""
        for image_ref in cover_candidates:
            thumb_media_id = await upload_cover_material(client, image_ref, token)
            if thumb_media_id:
                break

        if not thumb_media_id:
            raise ValueError("failed to upload a valid cover image; draft/add requires thumb_media_id")

        wechat_illustrations = await _upload_illustrations(client, illustration_refs, token)

        html_content = markdown_to_wechat_html(
            md_text=str(article.get("content", "")),
            illustrations=wechat_illustrations,
            style_config=style_config,
        )
        draft_payload = {
            "articles": [
                {
                    "title": article.get("title", "自动生成文章"),
                    "content": html_content,
                    "thumb_media_id": thumb_media_id,
                }
            ]
        }

        media_id = await _submit_draft(client, app_id, app_secret, draft_payload)
        result = {
            "media_id": media_id,
            "url": "",
            "publish_status": "draft_only",
            "publish_id": "",
            "publish_error": "",
        }

        if not auto_publish:
            return result

        return await _publish_draft(
            client,
            app_id,
            app_secret,
            media_id,
            result,
            poll_interval_seconds=publish_poll_interval_seconds,
            poll_max_attempts=publish_poll_max_attempts,
        )
