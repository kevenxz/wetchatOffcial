"""Publish an existing WeChat draft to the official account.

``draft/add`` only fills the draft box; publishing requires a second call. Both
steps are kept here so the draft and publish stages can be retried independently.
"""
from __future__ import annotations

import asyncio

import httpx
import structlog

logger = structlog.get_logger(__name__)

FREEPUBLISH_SUBMIT_URL = "https://api.weixin.qq.com/cgi-bin/freepublish/submit"
FREEPUBLISH_GET_URL = "https://api.weixin.qq.com/cgi-bin/freepublish/get"

# WeChat reports publish progress asynchronously through these status codes.
PUBLISH_STATUS_SUCCESS = 0
PUBLISH_STATUS_PUBLISHING = 1

TOKEN_ERROR_CODES = {40001, 40014, 42001, 42002}


class WeChatPublishError(RuntimeError):
    """Raised when WeChat refuses or fails to publish a draft."""

    def __init__(self, message: str, *, errcode: int | None = None, token_expired: bool = False) -> None:
        super().__init__(message)
        self.errcode = errcode
        self.token_expired = token_expired


async def submit_publish(client: httpx.AsyncClient, access_token: str, media_id: str) -> str:
    """Submit a draft for publishing and return WeChat's ``publish_id``."""
    response = await client.post(
        f"{FREEPUBLISH_SUBMIT_URL}?access_token={access_token}",
        json={"media_id": media_id},
    )
    response.raise_for_status()
    payload = response.json()

    errcode = int(payload.get("errcode", 0) or 0)
    if errcode != 0:
        raise WeChatPublishError(
            f"wechat freepublish/submit failed: {payload}",
            errcode=errcode,
            token_expired=errcode in TOKEN_ERROR_CODES,
        )

    publish_id = str(payload.get("publish_id") or "")
    if not publish_id:
        raise WeChatPublishError(f"wechat freepublish/submit missing publish_id: {payload}")
    return publish_id


async def fetch_publish_status(client: httpx.AsyncClient, access_token: str, publish_id: str) -> dict:
    """Fetch the current publish status for one ``publish_id``."""
    response = await client.post(
        f"{FREEPUBLISH_GET_URL}?access_token={access_token}",
        json={"publish_id": publish_id},
    )
    response.raise_for_status()
    payload = response.json()

    errcode = int(payload.get("errcode", 0) or 0)
    if errcode != 0:
        raise WeChatPublishError(
            f"wechat freepublish/get failed: {payload}",
            errcode=errcode,
            token_expired=errcode in TOKEN_ERROR_CODES,
        )
    return payload


def _article_status(payload: dict) -> int | None:
    detail = payload.get("article_detail")
    if isinstance(detail, dict):
        item = detail.get("item")
        if isinstance(item, list) and item:
            first = item[0]
            if isinstance(first, dict) and first.get("idx") is not None:
                pass
        status = detail.get("status")
        if status is not None:
            return int(status)
    if payload.get("publish_status") is not None:
        return int(payload["publish_status"])
    return None


async def poll_publish_status(
    client: httpx.AsyncClient,
    access_token: str,
    publish_id: str,
    *,
    interval_seconds: float = 5.0,
    max_attempts: int = 10,
) -> dict:
    """Poll until the publish reaches a terminal state.

    Returns a dict with ``status``, ``published``, ``publish_id`` and the last raw
    payload. ``published`` is only True for a confirmed success.
    """
    last_payload: dict = {}
    for attempt in range(1, max(1, max_attempts) + 1):
        last_payload = await fetch_publish_status(client, access_token, publish_id)
        status = _article_status(last_payload)
        if status == PUBLISH_STATUS_SUCCESS:
            return {"status": status, "published": True, "publish_id": publish_id, "payload": last_payload}
        if status is not None and status != PUBLISH_STATUS_PUBLISHING:
            return {"status": status, "published": False, "publish_id": publish_id, "payload": last_payload}
        if attempt < max_attempts:
            await asyncio.sleep(interval_seconds)

    return {
        "status": _article_status(last_payload),
        "published": False,
        "publish_id": publish_id,
        "payload": last_payload,
        "timed_out": True,
    }


def publish_failure_reason(status: int | None) -> str:
    """Translate a WeChat publish status code into an operator-facing reason."""
    reasons = {
        2: "原创校验失败",
        3: "常规发布失败",
        4: "平台审核不通过",
        5: "发布成功后文章被删除",
        6: "发布成功后账号被屏蔽",
        7: "审核失败",
    }
    if status is None:
        return "发布状态未知"
    return reasons.get(status, f"发布失败（状态码 {status}）")
