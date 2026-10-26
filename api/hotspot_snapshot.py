"""Cached hotspot snapshots, refreshed on a schedule.

Why this exists
---------------
Hotspots used to be fetched **synchronously while a task started**, so a slow or failing
upstream directly delayed (or degraded) every task. The production log showed how often
that bites: 429 ``tophub_fetch_retry``, 176 ``hotspot_source_unavailable`` and 70
``capture_hot_topics_platform_failed``.

This module pulls the hot lists on a timer instead, stores one snapshot, and lets task
creation read that snapshot when it is still fresh — falling back to a live fetch when it
is not. Nothing about the live path is removed, so behaviour cannot regress.

Storage uses :func:`api.persistence.write_json_file`, which already provides a unique
temporary name, a per-path lock and retry-on-sharing-violation.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import structlog

from api import persistence
from workflow.utils.hotspot_providers import fetch_hotspot_platform_items
from workflow.utils.hotspot_ranker import rank_hotspots
from workflow.utils.newsnow_catalog import NEWSNOW_PLATFORM_IDS, newsnow_platform_catalog

logger = structlog.get_logger(__name__)

DATA_DIR = Path("data")
SNAPSHOT_FILE = DATA_DIR / "hotspot_snapshot.json"

DEFAULT_REFRESH_INTERVAL_MINUTES = 60
# A refresh that yields nothing is retried much sooner than the normal interval.
DEFAULT_RETRY_INTERVAL_MINUTES = 5
DEFAULT_MAX_AGE_MINUTES = 180
DEFAULT_TOP_N_PER_PLATFORM = 15
# A snapshot is only useful if it covers the platforms the operator actually chooses.
# All 16 newsnow platforms cost 16 GETs per refresh, which is what the upstream is built for.
DEFAULT_REFRESH_SOURCE = "newsnow"

_lock = asyncio.Lock()
_cache: dict[str, Any] | None = None


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default


def refresh_interval_minutes() -> int:
    """How often the scheduled refresh runs (``1440`` gives a daily pull)."""
    return _env_int("HOTSPOT_REFRESH_INTERVAL_MINUTES", DEFAULT_REFRESH_INTERVAL_MINUTES)


def retry_interval_minutes() -> int:
    """How soon to retry after a refresh that produced nothing.

    Without this, a failed refresh was indistinguishable from a successful one for scheduling
    purposes: it stamped a fresh ``captured_at``, so ``due_for_refresh()`` stayed false for the
    whole interval. A total upstream outage therefore cost a full cycle of blackout — observed
    on 2026-10-24, when all 16 platforms failed at once and the next attempt would have been an
    hour later.
    """
    return _env_int("HOTSPOT_RETRY_INTERVAL_MINUTES", DEFAULT_RETRY_INTERVAL_MINUTES)


def max_age_minutes() -> int:
    """Age past which a snapshot is considered stale at task-creation time."""
    return _env_int("HOTSPOT_SNAPSHOT_MAX_AGE_MINUTES", DEFAULT_MAX_AGE_MINUTES)


def refresh_source() -> str:
    return (os.getenv("HOTSPOT_REFRESH_SOURCE") or DEFAULT_REFRESH_SOURCE).strip() or DEFAULT_REFRESH_SOURCE


def configured_platforms() -> list[dict[str, Any]]:
    """Platforms the scheduled refresh pulls.

    Defaults to every newsnow platform; ``HOTSPOT_REFRESH_PLATFORMS`` narrows it to a
    comma-separated id list.
    """
    requested = {
        item.strip()
        for item in (os.getenv("HOTSPOT_REFRESH_PLATFORMS") or "").split(",")
        if item.strip()
    }
    catalog = newsnow_platform_catalog([])
    if not requested:
        return catalog
    return [item for item in catalog if str(item.get("provider_id")) in requested]


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _load_from_disk() -> dict[str, Any]:
    payload = persistence.read_json_file(SNAPSHOT_FILE)
    return dict(payload) if isinstance(payload, dict) else {}


def get_snapshot() -> dict[str, Any]:
    """Return the current snapshot, loading it from disk on first use."""
    global _cache
    if _cache is None:
        _cache = _load_from_disk()
    return dict(_cache)


def reset_cache() -> None:
    """Drop the in-memory snapshot (used by tests and after an external rewrite)."""
    global _cache
    _cache = None


def snapshot_age_minutes(now: datetime | None = None) -> float | None:
    """Age of the snapshot in minutes, or ``None`` when there is no usable timestamp."""
    captured_at = _parse_time(get_snapshot().get("captured_at"))
    if captured_at is None:
        return None
    reference = now or _utc_now()
    return (reference - captured_at).total_seconds() / 60.0


def has_payload(snapshot: dict[str, Any] | None = None) -> bool:
    """Whether a snapshot actually carries candidates.

    A refresh where every platform failed still writes a valid file with a fresh timestamp but
    zero candidates. Treating that as "fresh" told operators the cache was healthy and, worse,
    delayed the retry by the full interval.
    """
    data = snapshot if snapshot is not None else get_snapshot()
    return bool(data.get("candidates"))


def last_attempt_succeeded(snapshot: dict[str, Any] | None = None) -> bool:
    """Whether the most recent refresh actually produced candidates.

    Snapshots written before this field existed default to "succeeded if it has candidates".
    """
    data = snapshot if snapshot is not None else get_snapshot()
    if not has_payload(data):
        return False
    return data.get("succeeded") is not False


def is_fresh(now: datetime | None = None) -> bool:
    """Whether the snapshot is usable: present, non-empty, fresh, and not a failed refresh."""
    age = snapshot_age_minutes(now)
    if age is None:
        return False
    if not has_payload():
        return False
    # A preserved snapshot from before a failed refresh is last-known-good, not current:
    # treating it as fresh would silently serve stale hotspots as if they were today's.
    if not last_attempt_succeeded():
        return False
    return age <= max_age_minutes()


def due_for_refresh(now: datetime | None = None) -> bool:
    """Whether the scheduled refresh should run now.

    A snapshot without candidates is retried on the shorter retry interval rather than being
    trusted for a full cycle.
    """
    snapshot = get_snapshot()
    reference = now or _utc_now()

    if not last_attempt_succeeded(snapshot):
        # Prefer the last attempt time: a failed refresh must not look like a recent success,
        # even when older candidates were preserved.
        last_attempt = _parse_time(snapshot.get("attempted_at")) or _parse_time(snapshot.get("captured_at"))
        if last_attempt is None:
            return True
        return reference - last_attempt >= timedelta(minutes=retry_interval_minutes())

    captured_at = _parse_time(snapshot.get("captured_at"))
    if captured_at is None:
        return True
    return reference - captured_at >= timedelta(minutes=refresh_interval_minutes())


def _platform_key(item: dict[str, Any]) -> set[str]:
    """Every identifier a snapshot entry might be matched by."""
    keys = {
        str(item.get("provider_id") or "").strip(),
        str(item.get("path") or "").strip(),
        str(item.get("name") or "").strip(),
        str(item.get("url") or "").strip(),
    }
    return {key for key in keys if key}


def candidates_for(platforms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Snapshot candidates restricted to the requested platforms.

    Returns an empty list when the snapshot does not cover them, which tells the caller to
    fetch live rather than silently producing fewer candidates.
    """
    snapshot = get_snapshot()
    candidates = [item for item in list(snapshot.get("candidates") or []) if isinstance(item, dict)]
    if not candidates:
        return []

    requested: set[str] = set()
    for platform in platforms:
        requested |= _platform_key(platform)
    if not requested:
        return candidates

    matched = [item for item in candidates if _platform_key(item) & requested]
    return matched


def recently_failed_platforms(now: datetime | None = None) -> set[str]:
    """Platform ids the most recent refresh attempted and got nothing from.

    Only meaningful while the snapshot is fresh. It exists because a platform that returns no
    items never appears in the snapshot, so it looked "uncovered" and was live-fetched on every
    single task — repeating a failure the background refresher had just confirmed, and adding
    seconds to task creation for no data. Measured: one such platform (``mktnews``) made an
    otherwise snapshot-served task take ~6s instead of ~0s.

    The next scheduled refresh still retries it, so a platform cannot get permanently stuck.
    """
    if not is_fresh(now):
        return set()
    snapshot = get_snapshot()
    return {str(item) for item in list(snapshot.get("failed_platforms") or []) if item}


def covered_platform_keys(candidates: list[dict[str, Any]]) -> set[str]:
    """All identifiers present in a candidate set, for deciding what still needs a fetch."""
    keys: set[str] = set()
    for item in candidates:
        keys |= _platform_key(item)
    return keys


def split_covered_platforms(
    platforms: list[dict[str, Any]],
    snapshot_candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split requested platforms into (served by the snapshot, still needs a fetch).

    A snapshot covering only part of the request must not silently shrink the candidate
    pool, so the uncovered platforms are still fetched live.
    """
    covered = covered_platform_keys(snapshot_candidates)
    from_snapshot: list[dict[str, Any]] = []
    need_live: list[dict[str, Any]] = []
    for platform in platforms:
        if _platform_key(platform) & covered:
            from_snapshot.append(platform)
        else:
            need_live.append(platform)
    return from_snapshot, need_live


async def refresh_hotspot_snapshot(*, force: bool = False, top_n: int | None = None) -> dict[str, Any]:
    """Fetch every configured platform and persist one ranked snapshot.

    Concurrent callers are serialised so a scheduled refresh and a manual refresh cannot
    both hit the upstream for the same platform set.
    """
    async with _lock:
        if not force and not due_for_refresh():
            logger.debug("hotspot_refresh_skipped_not_due", age_minutes=snapshot_age_minutes())
            return get_snapshot()

        platforms = [platform for platform in configured_platforms() if platform.get("enabled", True)]
        source = refresh_source()
        limit = top_n or _env_int("HOTSPOT_REFRESH_TOP_N", DEFAULT_TOP_N_PER_PLATFORM)
        started = _utc_now()

        results = await asyncio.gather(
            *[fetch_hotspot_platform_items(platform, top_n=limit) for platform in platforms],
            return_exceptions=True,
        )

        candidates: list[dict[str, Any]] = []
        failed: list[str] = []
        for platform, result in zip(platforms, results):
            label = str(platform.get("provider_id") or platform.get("name") or "?")
            if isinstance(result, Exception):
                failed.append(label)
                logger.warning(
                    "hotspot_refresh_platform_failed",
                    platform=label,
                    error=str(result),
                    exc_info=True,
                )
                continue
            if result:
                candidates.extend(result)
            else:
                failed.append(label)

        # Rank with no category filter: the snapshot is shared by every future task, so
        # scoring must not depend on one task's categories or keyword filters.
        ranked = rank_hotspots(candidates, categories=[], filters={"min_selection_score": 0})

        previous = get_snapshot()
        succeeded = bool(ranked)
        now_iso = _utc_now().isoformat()
        # Keep the last good candidates when the whole upstream is down. Replacing 210 real
        # candidates with nothing costs the only data we have and helps nobody: the snapshot is
        # still marked failed (so `is_fresh` is False and tasks fetch live), and the next attempt
        # happens on the retry interval. Observed 2026-10-25 when newsnow answered HTTP 500 for
        # all 16 platforms at once.
        served = ranked if succeeded else list(previous.get("candidates") or [])

        snapshot = {
            "captured_at": now_iso if succeeded else str(previous.get("captured_at") or ""),
            # Always recorded, even when nothing came back, so a failed refresh can be
            # retried on the shorter interval instead of blocking a full cycle.
            "attempted_at": now_iso,
            "succeeded": succeeded,
            "started_at": started.isoformat(),
            "source": source,
            "duration_ms": round((_utc_now() - started).total_seconds() * 1000),
            "platform_count": len(platforms),
            "failed_platforms": failed,
            # What *this attempt* fetched. Stays 0 on a failed refresh — the preserved data is
            # not this attempt's work.
            "raw_count": len(candidates) if succeeded else 0,
            # What the snapshot actually serves. Must agree with `candidates`, otherwise an
            # operator reading candidate_count=0 would conclude there is no data at all.
            "candidate_count": len(served),
            "preserved_from_previous": (not succeeded) and bool(served),
            "candidates": served,
        }
        if succeeded:
            snapshot["last_success_at"] = now_iso
        else:
            snapshot["last_success_at"] = str(previous.get("last_success_at") or previous.get("captured_at") or "")
            if snapshot["candidates"]:
                logger.warning(
                    "hotspot_snapshot_refresh_empty_kept_previous",
                    kept_candidates=len(snapshot["candidates"]),
                    failed_platforms=failed,
                )
        _persist(snapshot)
        logger.info(
            "hotspot_snapshot_refreshed",
            source=source,
            platforms=len(platforms),
            failed=len(failed),
            raw_count=len(candidates),
            candidate_count=len(ranked),
            duration_ms=snapshot["duration_ms"],
        )
        return snapshot


def _persist(snapshot: dict[str, Any]) -> None:
    """Write the snapshot through the hardened atomic writer and refresh the cache."""
    global _cache
    try:
        persistence.write_json_file(SNAPSHOT_FILE, snapshot)
    except Exception as exc:  # noqa: BLE001
        # Keeping the in-memory snapshot is better than losing a successful fetch, so this
        # is a warning: the data is still usable for this process.
        logger.warning("hotspot_snapshot_write_failed", error=str(exc), exc_info=True)
    _cache = snapshot


async def maybe_refresh_hotspot_snapshot() -> bool:
    """Scheduler hook: refresh when due. Never raises."""
    try:
        if not due_for_refresh():
            return False
        await refresh_hotspot_snapshot()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("hotspot_scheduled_refresh_failed", error=str(exc), exc_info=True)
        return False


def snapshot_status() -> dict[str, Any]:
    """Compact status for the API and the health view."""
    snapshot = get_snapshot()
    return {
        "available": has_payload(snapshot),
        "succeeded": bool(snapshot.get("succeeded", has_payload(snapshot))),
        "attempted_at": snapshot.get("attempted_at") or "",
        "captured_at": snapshot.get("captured_at") or "",
        "retry_interval_minutes": retry_interval_minutes(),
        "age_minutes": snapshot_age_minutes(),
        "fresh": is_fresh(),
        "due_for_refresh": due_for_refresh(),
        "source": snapshot.get("source") or refresh_source(),
        "platform_count": int(snapshot.get("platform_count") or 0),
        "failed_platforms": list(snapshot.get("failed_platforms") or []),
        "raw_count": int(snapshot.get("raw_count") or 0),
        "candidate_count": int(snapshot.get("candidate_count") or 0),
        "refresh_interval_minutes": refresh_interval_minutes(),
        "max_age_minutes": max_age_minutes(),
        "configured_platforms": [str(item.get("provider_id")) for item in configured_platforms()],
        "known_platforms": list(NEWSNOW_PLATFORM_IDS),
    }
