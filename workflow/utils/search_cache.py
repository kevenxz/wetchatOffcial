"""Redis-backed cache for search provider responses.

Scheduled hotspot runs frequently repeat the same queries. Caching the provider
response removes that network round trip entirely, which is the single largest
remaining cost in the research stage after query-level concurrency.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

import structlog

from workflow import runtime_settings
from workflow.utils.redis_client import get_redis

logger = structlog.get_logger(__name__)

CACHE_PREFIX = "search:v1"


def cache_key(provider: str, query: str, limit: int) -> str:
    """Build a stable cache key for one provider query."""
    digest = hashlib.sha1(
        f"{provider}|{query.strip().lower()}|{int(limit)}".encode("utf-8")
    ).hexdigest()
    return f"{CACHE_PREFIX}:{digest}"


def _cache_enabled() -> bool:
    return runtime_settings.search_cache_enabled() and runtime_settings.search_cache_ttl_seconds() > 0


async def get_cached_search(provider: str, query: str, limit: int) -> list[dict[str, Any]] | None:
    """Return cached search results, or ``None`` on miss or when Redis is down."""
    if not _cache_enabled():
        return None

    client = await get_redis()
    if client is None:
        return None

    try:
        raw = await client.get(cache_key(provider, query, limit))
    except Exception as exc:  # noqa: BLE001
        logger.warning("search_cache_get_failed", error=str(exc), exc_info=True)
        return None

    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except Exception:  # noqa: BLE001
        return None
    return payload if isinstance(payload, list) else None


async def set_cached_search(provider: str, query: str, limit: int, results: list[dict[str, Any]]) -> None:
    """Store search results; failures are logged and swallowed."""
    if not results or not _cache_enabled():
        return

    client = await get_redis()
    if client is None:
        return

    try:
        await client.set(
            cache_key(provider, query, limit),
            json.dumps(results, ensure_ascii=False),
            ex=runtime_settings.search_cache_ttl_seconds(),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("search_cache_set_failed", error=str(exc), exc_info=True)
