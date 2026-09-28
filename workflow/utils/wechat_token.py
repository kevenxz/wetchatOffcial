"""Shared WeChat ``access_token`` cache.

WeChat issues one token per app and rate-limits how often it can be fetched, so the
token is cached in Redis (shared across restarts) with an in-process fallback for
when Redis is not configured.
"""
from __future__ import annotations

import json
import time

import httpx
import structlog

from workflow.utils.redis_client import get_redis

logger = structlog.get_logger(__name__)

TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"

# Refresh slightly before expiry so an in-flight request never uses a dead token.
EXPIRY_SKEW_SECONDS = 300
DEFAULT_EXPIRES_IN = 7200

# In-process fallback cache, also used when Redis is unavailable.
_access_token_cache: dict[str, dict[str, float | str]] = {}


def token_cache_key(app_id: str) -> str:
    """Redis key holding one app's cached token."""
    return f"wechat:token:{app_id}"


def _is_fresh(expires_at: float, now: float) -> bool:
    return bool(expires_at) and now < expires_at - EXPIRY_SKEW_SECONDS


async def _read_shared_token(app_id: str, now: float) -> str:
    client = await get_redis()
    if client is None:
        return ""
    try:
        raw = await client.get(token_cache_key(app_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("wechat_token_read_failed", error=str(exc))
        return ""
    if not raw:
        return ""

    try:
        payload = json.loads(raw)
    except Exception:  # noqa: BLE001
        return ""

    token = str(payload.get("token") or "")
    expires_at = float(payload.get("expires_at") or 0.0)
    if token and _is_fresh(expires_at, now):
        _access_token_cache[app_id] = {"token": token, "expires_at": expires_at}
        return token
    return ""


async def _store_shared_token(app_id: str, token: str, expires_at: float, now: float) -> None:
    client = await get_redis()
    if client is None:
        return
    ttl = int(max(60.0, expires_at - now))
    try:
        await client.set(
            token_cache_key(app_id),
            json.dumps({"token": token, "expires_at": expires_at}),
            ex=ttl,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("wechat_token_write_failed", error=str(exc))


async def get_access_token(app_id: str, app_secret: str, client: httpx.AsyncClient) -> str:
    """Return a valid access token, reusing any cached one."""
    now = time.time()

    cached = _access_token_cache.get(app_id, {"token": "", "expires_at": 0.0})
    token = str(cached.get("token") or "")
    if token and _is_fresh(float(cached.get("expires_at") or 0.0), now):
        return token

    shared_token = await _read_shared_token(app_id, now)
    if shared_token:
        return shared_token

    url = f"{TOKEN_URL}?grant_type=client_credential&appid={app_id}&secret={app_secret}"
    response = await client.get(url)
    response.raise_for_status()
    payload = response.json()
    if payload.get("errcode", 0) != 0 or "access_token" not in payload:
        raise ValueError(f"failed to get access token: {payload}")

    token = str(payload["access_token"])
    expires_at = now + int(payload.get("expires_in", DEFAULT_EXPIRES_IN))
    _access_token_cache[app_id] = {"token": token, "expires_at": expires_at}
    await _store_shared_token(app_id, token, expires_at, now)
    return token


async def invalidate_access_token(app_id: str) -> None:
    """Drop a cached token after WeChat reports it as expired."""
    _access_token_cache.pop(app_id, None)
    client = await get_redis()
    if client is None:
        return
    try:
        await client.delete(token_cache_key(app_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("wechat_token_invalidate_failed", error=str(exc))
