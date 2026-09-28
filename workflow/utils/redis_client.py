"""Lazy, failure-tolerant Redis client shared across the workflow.

Redis is optional: when ``REDIS_URL`` is unset, unreachable, or fails to answer a
ping, every caller receives ``None`` and degrades gracefully instead of raising.
"""
from __future__ import annotations

import os
import time
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Back off before retrying a failed connection so a down Redis never adds latency
# to every request on a small single-machine deployment.
_RETRY_COOLDOWN_SECONDS = 60.0

_client: Any = None
_unavailable_until: float = 0.0


def redis_url() -> str:
    """Return the configured Redis URL, or an empty string."""
    return (os.getenv("REDIS_URL") or "").strip()


async def get_redis() -> Any | None:
    """Return a connected Redis client, or ``None`` when Redis is unavailable."""
    global _client, _unavailable_until

    url = redis_url()
    if not url:
        return None
    if _client is not None:
        return _client
    if time.monotonic() < _unavailable_until:
        return None

    try:
        from redis.asyncio import Redis

        client = Redis.from_url(url, decode_responses=True)
        await client.ping()
    except Exception as exc:  # noqa: BLE001
        _unavailable_until = time.monotonic() + _RETRY_COOLDOWN_SECONDS
        logger.warning("redis_unavailable", error=str(exc))
        return None

    _client = client
    logger.info("redis_connected")
    return _client


def reset_redis_state() -> None:
    """Forget the cached client and cooldown (used by tests)."""
    global _client, _unavailable_until
    _client = None
    _unavailable_until = 0.0
