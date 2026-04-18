"""Reusable service for pushing an article to WeChat draft box."""
from __future__ import annotations

import time

import httpx

from workflow.utils.markdown_to_wechat import markdown_to_wechat_html
from workflow.utils.wechat_api import upload_article_image, upload_cover_material

_access_token_cache: dict[str, dict[str, float | str]] = {}


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
    now = time.time()
    cache = _access_token_cache.get(app_id, {"token": "", "expires_at": 0.0})
    token = str(cache.get("token", ""))
    expires_at = float(cache.get("expires_at", 0.0))
    if token and now < expires_at - 300:
        return token

    url = (
        "https://api.weixin.qq.com/cgi-bin/token"
        f"?grant_type=client_credential&appid={app_id}&secret={app_secret}"
    )
    response = await client.get(url)
    response.raise_for_status()
    payload = response.json()
    if payload.get("errcode", 0) != 0 or "access_token" not in payload:
        raise ValueError(f"failed to get access token: {payload}")

    token = payload["access_token"]
    expires_in = int(payload.get("expires_in", 7200))
    _access_token_cache[app_id] = {"token": token, "expires_at": now + expires_in}
    return token


async def push_article_to_wechat_draft(
    article: dict,
    app_id: str,
    app_secret: str,
    style_config: dict[str, str] | None = None,
) -> dict:
    """Push article content to WeChat draft box and return draft info."""
    if not app_id or not app_secret:
        raise ValueError("missing app_id or app_secret")

    if not article:
        raise ValueError("empty article payload")

    retry_count = 0
    max_retries = 3
    last_error = ""

    async with httpx.AsyncClient(timeout=15.0) as client:
        token = await _get_access_token(app_id, app_secret, client)

        cover_candidates, illustration_refs = _resolve_visual_asset_refs(article)

        thumb_media_id = ""
        for image_ref in cover_candidates:
            thumb_media_id = await upload_cover_material(client, image_ref, token)
            if thumb_media_id:
                break

        if not thumb_media_id:
            raise ValueError("failed to upload a valid cover image; draft/add requires thumb_media_id")

        wechat_illustrations: list[str] = []
        for image_url in illustration_refs:
            wechat_illustrations.append(
                await upload_article_image(client, image_url, token)
            )

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

        while retry_count < max_retries:
            try:
                current_token = await _get_access_token(app_id, app_secret, client)
                draft_url = (
                    "https://api.weixin.qq.com/cgi-bin/draft/add"
                    f"?access_token={current_token}"
                )
                response = await client.post(draft_url, json=draft_payload)
                response.raise_for_status()
                payload = response.json()

                errcode = payload.get("errcode", 0)
                if errcode != 0:
                    if errcode in (40001, 40014, 42001, 42002):
                        _access_token_cache.pop(app_id, None)
                        raise ValueError(f"access token expired: {payload}")
                    if errcode == 40007:
                        raise ValueError(f"invalid thumb_media_id for wechat draft add: {payload}")
                    raise ValueError(f"wechat draft add failed: {payload}")

                media_id = payload.get("media_id")
                if not media_id:
                    raise ValueError(f"wechat draft add missing media_id: {payload}")

                return {
                    "media_id": media_id,
                    "url": "",
                }
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                retry_count += 1

    raise ValueError(last_error or "push to wechat draft failed")
