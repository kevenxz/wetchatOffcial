"""Centralized runtime tuning knobs for the article generation chain.

All values are environment driven so that the single-machine 2C2G deployment can
trade latency against resource pressure without code changes.
"""
from __future__ import annotations

import asyncio
import os
import weakref

_DEFAULT_RESEARCH_CONCURRENCY = 4
_DEFAULT_IMAGE_CONCURRENCY = 2
_DEFAULT_LLM_CONCURRENCY = 3
_DEFAULT_LLM_TIMEOUT_SECONDS = 90.0
_DEFAULT_LLM_MAX_RETRIES = 1
_DEFAULT_SEARCH_CACHE_TTL_SECONDS = 21600
_DEFAULT_PLANNER_MODE = "rules"

PLANNER_MODES = {"rules", "llm", "auto"}


def _env_str(name: str, default: str) -> str:
    raw = (os.getenv(name) or "").strip()
    return raw or default


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, min(value, maximum))


def _env_float(name: str, default: float, *, minimum: float, maximum: float) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return max(minimum, min(value, maximum))


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def research_concurrency() -> int:
    """Concurrent research queries per workflow run."""
    return _env_int("RESEARCH_CONCURRENCY", _DEFAULT_RESEARCH_CONCURRENCY, minimum=1, maximum=8)


def image_concurrency() -> int:
    """Concurrent image generation calls per workflow run."""
    return _env_int("IMAGE_CONCURRENCY", _DEFAULT_IMAGE_CONCURRENCY, minimum=1, maximum=4)


def llm_concurrency() -> int:
    """Process-wide concurrent LLM call ceiling."""
    return _env_int("LLM_CONCURRENCY", _DEFAULT_LLM_CONCURRENCY, minimum=1, maximum=8)


def llm_timeout_seconds() -> float:
    """Per-request LLM timeout; prevents the SDK 600s default long tail."""
    return _env_float("LLM_TIMEOUT_SECONDS", _DEFAULT_LLM_TIMEOUT_SECONDS, minimum=10.0, maximum=600.0)


def llm_max_retries() -> int:
    """LLM retry budget; the SDK default of 2 amplifies latency spikes."""
    return _env_int("LLM_MAX_RETRIES", _DEFAULT_LLM_MAX_RETRIES, minimum=0, maximum=3)


def planner_mode() -> str:
    """Research-contract planning mode: rules | llm | auto."""
    mode = _env_str("PLANNER_MODE", _DEFAULT_PLANNER_MODE).lower()
    return mode if mode in PLANNER_MODES else _DEFAULT_PLANNER_MODE


def search_cache_enabled() -> bool:
    """Whether search results are cached in Redis."""
    return _env_bool("SEARCH_CACHE_ENABLED", True)


def search_cache_ttl_seconds() -> int:
    """Search result cache TTL in seconds."""
    return _env_int("SEARCH_CACHE_TTL_SECONDS", _DEFAULT_SEARCH_CACHE_TTL_SECONDS, minimum=0, maximum=604800)


_semaphores: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, dict[str, asyncio.Semaphore]]" = (
    weakref.WeakKeyDictionary()
)


def get_semaphore(name: str, limit: int) -> asyncio.Semaphore:
    """Return a per-event-loop semaphore.

    Semaphores are cached per running loop so that concurrent workflows share one
    budget while independent test event loops stay isolated.
    """
    loop = asyncio.get_running_loop()
    bucket = _semaphores.get(loop)
    if bucket is None:
        bucket = {}
        _semaphores[loop] = bucket
    semaphore = bucket.get(name)
    if semaphore is None or getattr(semaphore, "_dsh_limit", None) != limit:
        semaphore = asyncio.Semaphore(limit)
        setattr(semaphore, "_dsh_limit", limit)
        bucket[name] = semaphore
    return semaphore
