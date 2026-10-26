"""Tests for the scheduled hotspot snapshot.

The problem this solves: hotspots used to be fetched synchronously while a task started,
so a slow upstream delayed every task. The production log recorded 429
``tophub_fetch_retry``, 176 ``hotspot_source_unavailable`` and 70 platform failures.

The contract under test: a fresh snapshot is served without touching the network, a stale
one falls back to a live fetch, a partially-covered request fetches only the uncovered
platforms, and a total upstream failure degrades instead of raising.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import api.hotspot_snapshot as snapshot


@pytest.fixture(autouse=True)
def isolated_snapshot(tmp_path, monkeypatch):
    """Point the snapshot file at a temp dir and clear the module cache."""
    monkeypatch.setattr(snapshot, "SNAPSHOT_FILE", tmp_path / "hotspot_snapshot.json")
    snapshot.reset_cache()
    yield
    snapshot.reset_cache()


def _write_snapshot(captured_at: datetime, candidates: list[dict]) -> None:
    snapshot._persist(
        {
            "captured_at": captured_at.isoformat(),
            "source": "newsnow",
            "candidates": candidates,
            "candidate_count": len(candidates),
        }
    )


def _candidate(platform_id: str, title: str = "热点") -> dict:
    return {
        "title": title,
        "platform_name": platform_id,
        "provider_id": platform_id,
        "path": platform_id,
        "source": "newsnow",
        "rank": 1,
        "category": "社会",
        "url": f"https://example.com/{platform_id}",
    }


def _platform(platform_id: str) -> dict:
    return {"name": platform_id, "path": platform_id, "provider_id": platform_id, "source": "newsnow"}


# --------------------------------------------------------------------------- #
# freshness
# --------------------------------------------------------------------------- #


def test_missing_snapshot_is_not_fresh_and_is_due() -> None:
    assert snapshot.is_fresh() is False
    assert snapshot.due_for_refresh() is True
    assert snapshot.snapshot_age_minutes() is None


def test_recent_snapshot_is_fresh_and_not_due() -> None:
    _write_snapshot(datetime.now(tz=timezone.utc), [_candidate("weibo")])

    assert snapshot.is_fresh() is True
    assert snapshot.due_for_refresh() is False


def test_snapshot_older_than_max_age_is_stale(monkeypatch) -> None:
    monkeypatch.setenv("HOTSPOT_SNAPSHOT_MAX_AGE_MINUTES", "60")
    _write_snapshot(datetime.now(tz=timezone.utc) - timedelta(minutes=120), [_candidate("weibo")])

    assert snapshot.is_fresh() is False
    # Still not due if the refresh interval has not elapsed.
    assert snapshot.snapshot_age_minutes() == pytest.approx(120, abs=2)


def test_refresh_interval_controls_due(monkeypatch) -> None:
    monkeypatch.setenv("HOTSPOT_REFRESH_INTERVAL_MINUTES", "30")
    _write_snapshot(datetime.now(tz=timezone.utc) - timedelta(minutes=45), [_candidate("weibo")])

    assert snapshot.refresh_interval_minutes() == 30
    assert snapshot.due_for_refresh() is True


def test_daily_interval_is_supported(monkeypatch) -> None:
    """`1440` is the operator's explicitly requested "daily pull"."""
    monkeypatch.setenv("HOTSPOT_REFRESH_INTERVAL_MINUTES", "1440")
    _write_snapshot(datetime.now(tz=timezone.utc) - timedelta(hours=2), [_candidate("weibo")])

    assert snapshot.refresh_interval_minutes() == 1440
    assert snapshot.due_for_refresh() is False


def test_unparseable_timestamp_is_treated_as_missing() -> None:
    snapshot._persist({"captured_at": "not-a-time", "candidates": [_candidate("weibo")]})

    assert snapshot.snapshot_age_minutes() is None
    assert snapshot.is_fresh() is False
    assert snapshot.due_for_refresh() is True


# --------------------------------------------------------------------------- #
# platform coverage
# --------------------------------------------------------------------------- #


def test_candidates_are_filtered_to_the_requested_platforms() -> None:
    _write_snapshot(
        datetime.now(tz=timezone.utc),
        [_candidate("weibo"), _candidate("zhihu"), _candidate("douyin")],
    )

    matched = snapshot.candidates_for([_platform("weibo")])
    assert [item["provider_id"] for item in matched] == ["weibo"]


def test_uncovered_platform_yields_nothing_so_caller_fetches_live() -> None:
    _write_snapshot(datetime.now(tz=timezone.utc), [_candidate("weibo")])

    assert snapshot.candidates_for([{"name": "TopHub 榜", "path": "/n/xxx", "provider_id": "tophub"}]) == []


def test_partial_coverage_splits_into_snapshot_and_live() -> None:
    """A partial match must not silently shrink the candidate pool."""
    _write_snapshot(datetime.now(tz=timezone.utc), [_candidate("weibo")])

    covered, need_live = snapshot.split_covered_platforms(
        [_platform("weibo"), {"name": "TopHub", "path": "/n/xxx", "provider_id": "tophub"}],
        snapshot.candidates_for([_platform("weibo")]),
    )

    assert [item["provider_id"] for item in covered] == ["weibo"]
    assert [item["provider_id"] for item in need_live] == ["tophub"]


def test_empty_platform_request_returns_everything() -> None:
    _write_snapshot(datetime.now(tz=timezone.utc), [_candidate("weibo"), _candidate("zhihu")])

    assert len(snapshot.candidates_for([])) == 2


# --------------------------------------------------------------------------- #
# refresh
# --------------------------------------------------------------------------- #


def test_configured_platforms_default_to_all_newsnow_platforms() -> None:
    assert len(snapshot.configured_platforms()) == 16


def test_configured_platforms_can_be_narrowed(monkeypatch) -> None:
    monkeypatch.setenv("HOTSPOT_REFRESH_PLATFORMS", "weibo, zhihu")

    ids = [item["provider_id"] for item in snapshot.configured_platforms()]
    assert ids == ["weibo", "zhihu"]


@pytest.mark.asyncio
async def test_refresh_persists_a_ranked_snapshot(monkeypatch) -> None:
    async def fake_fetch(platform, *, top_n):
        return [_candidate(str(platform.get("provider_id")), title=f"{platform.get('provider_id')}热点")]

    monkeypatch.setattr(snapshot, "fetch_hotspot_platform_items", fake_fetch)
    monkeypatch.setenv("HOTSPOT_REFRESH_PLATFORMS", "weibo,zhihu")

    result = await snapshot.refresh_hotspot_snapshot(force=True)

    assert result["platform_count"] == 2
    assert result["raw_count"] == 2
    assert result["candidate_count"] == 2
    assert snapshot.SNAPSHOT_FILE.exists()
    assert snapshot.snapshot_status()["available"] is True
    # Candidates carry their ranking so a task can re-rank with its own filters.
    assert all("selection_score" in item for item in result["candidates"])


@pytest.mark.asyncio
async def test_refresh_isolates_a_failing_platform(monkeypatch) -> None:
    async def flaky_fetch(platform, *, top_n):
        if str(platform.get("provider_id")) == "zhihu":
            raise RuntimeError("upstream exploded")
        return [_candidate("weibo")]

    monkeypatch.setattr(snapshot, "fetch_hotspot_platform_items", flaky_fetch)
    monkeypatch.setenv("HOTSPOT_REFRESH_PLATFORMS", "weibo,zhihu")

    result = await snapshot.refresh_hotspot_snapshot(force=True)

    assert result["failed_platforms"] == ["zhihu"]
    assert result["candidate_count"] == 1


@pytest.mark.asyncio
async def test_total_upstream_failure_produces_an_empty_but_valid_snapshot(monkeypatch) -> None:
    async def dead_fetch(platform, *, top_n):
        raise RuntimeError("everything is down")

    monkeypatch.setattr(snapshot, "fetch_hotspot_platform_items", dead_fetch)
    monkeypatch.setenv("HOTSPOT_REFRESH_PLATFORMS", "weibo")

    result = await snapshot.refresh_hotspot_snapshot(force=True)

    assert result["candidate_count"] == 0
    assert result["failed_platforms"] == ["weibo"]
    status = snapshot.snapshot_status()
    assert status["available"] is False
    assert status["failed_platforms"] == ["weibo"]


@pytest.mark.asyncio
async def test_platform_returning_nothing_counts_as_failed(monkeypatch) -> None:
    async def empty_fetch(platform, *, top_n):
        return []

    monkeypatch.setattr(snapshot, "fetch_hotspot_platform_items", empty_fetch)
    monkeypatch.setenv("HOTSPOT_REFRESH_PLATFORMS", "weibo")

    result = await snapshot.refresh_hotspot_snapshot(force=True)

    assert result["failed_platforms"] == ["weibo"]


@pytest.mark.asyncio
async def test_refresh_is_skipped_when_not_due(monkeypatch) -> None:
    calls = {"n": 0}

    async def counting_fetch(platform, *, top_n):
        calls["n"] += 1
        return [_candidate("weibo")]

    monkeypatch.setattr(snapshot, "fetch_hotspot_platform_items", counting_fetch)
    monkeypatch.setenv("HOTSPOT_REFRESH_PLATFORMS", "weibo")

    await snapshot.refresh_hotspot_snapshot(force=True)
    first = calls["n"]
    await snapshot.refresh_hotspot_snapshot(force=False)

    assert calls["n"] == first, "a not-due refresh must not call the upstream"


@pytest.mark.asyncio
async def test_concurrent_refreshes_do_not_both_hit_the_upstream(monkeypatch) -> None:
    """The lock keeps a scheduled refresh and a manual one from duplicating work."""
    calls = {"n": 0}
    started = asyncio.Event()

    async def slow_fetch(platform, *, top_n):
        calls["n"] += 1
        started.set()
        await asyncio.sleep(0.05)
        return [_candidate("weibo")]

    monkeypatch.setattr(snapshot, "fetch_hotspot_platform_items", slow_fetch)
    monkeypatch.setenv("HOTSPOT_REFRESH_PLATFORMS", "weibo")

    results = await asyncio.gather(
        snapshot.refresh_hotspot_snapshot(force=True),
        snapshot.refresh_hotspot_snapshot(force=False),
    )

    assert calls["n"] == 1
    # The second call returns the snapshot the first one produced.
    assert results[0]["captured_at"] == results[1]["captured_at"]


@pytest.mark.asyncio
async def test_scheduler_hook_never_raises(monkeypatch) -> None:
    async def dead_fetch(platform, *, top_n):
        raise RuntimeError("boom")

    monkeypatch.setattr(snapshot, "fetch_hotspot_platform_items", dead_fetch)
    monkeypatch.setenv("HOTSPOT_REFRESH_PLATFORMS", "weibo")

    # A failure inside the fetch is contained, so this still reports "refreshed".
    assert await snapshot.maybe_refresh_hotspot_snapshot() is True


@pytest.mark.asyncio
async def test_scheduler_hook_swallows_unexpected_errors(monkeypatch) -> None:
    def exploding_platforms():
        raise RuntimeError("config blew up")

    monkeypatch.setattr(snapshot, "configured_platforms", exploding_platforms)

    assert await snapshot.maybe_refresh_hotspot_snapshot() is False


# --------------------------------------------------------------------------- #
# persistence
# --------------------------------------------------------------------------- #


def test_snapshot_survives_a_process_restart(tmp_path, monkeypatch) -> None:
    _write_snapshot(datetime.now(tz=timezone.utc), [_candidate("weibo")])
    snapshot.reset_cache()

    assert snapshot.is_fresh() is True
    assert len(snapshot.candidates_for([_platform("weibo")])) == 1


def test_corrupt_snapshot_file_degrades_to_empty(tmp_path) -> None:
    Path(snapshot.SNAPSHOT_FILE).write_text("{not json", encoding="utf-8")
    snapshot.reset_cache()

    assert snapshot.is_fresh() is False
    assert snapshot.candidates_for([]) == []


def test_write_failure_keeps_the_in_memory_snapshot(monkeypatch) -> None:
    """A successful fetch must not be lost just because the file could not be written."""
    def failing_write(path, payload):
        raise PermissionError("[WinError 5] locked")

    monkeypatch.setattr(snapshot.persistence, "write_json_file", failing_write)

    snapshot._persist({"captured_at": datetime.now(tz=timezone.utc).isoformat(), "candidates": [_candidate("weibo")]})

    assert len(snapshot.get_snapshot().get("candidates") or []) == 1


def test_status_reports_what_an_operator_needs() -> None:
    _write_snapshot(datetime.now(tz=timezone.utc), [_candidate("weibo")])

    status = snapshot.snapshot_status()

    assert status["available"] is True
    assert status["fresh"] is True
    assert status["candidate_count"] == 1
    assert status["refresh_interval_minutes"] >= 1
    assert len(status["known_platforms"]) == 16


# --------------------------------------------------------------------------- #
# a failed refresh must not throw away good data
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_total_outage_keeps_the_previous_candidates(monkeypatch) -> None:
    """Observed 2026-10-25: newsnow answered HTTP 500 for all 16 platforms at once.

    The refresh replaced 210 real candidates with nothing, so the only data we had was gone
    until the upstream recovered. Keeping it costs nothing — the snapshot is still marked
    failed, so it is never served as if it were current.
    """
    async def good_fetch(platform, *, top_n):
        return [_candidate("weibo", "真实热点")]

    monkeypatch.setattr(snapshot, "fetch_hotspot_platform_items", good_fetch)
    monkeypatch.setenv("HOTSPOT_REFRESH_PLATFORMS", "weibo")
    await snapshot.refresh_hotspot_snapshot(force=True)
    assert len(snapshot.get_snapshot()["candidates"]) == 1

    async def dead_fetch(platform, *, top_n):
        raise RuntimeError("HTTP 500")

    monkeypatch.setattr(snapshot, "fetch_hotspot_platform_items", dead_fetch)
    await snapshot.refresh_hotspot_snapshot(force=True)

    kept = snapshot.get_snapshot()
    assert len(kept["candidates"]) == 1, "the candidates must survive an outage"
    assert kept["succeeded"] is False
    assert kept["candidate_count"] == 1


@pytest.mark.asyncio
async def test_preserved_candidates_are_never_treated_as_fresh(monkeypatch) -> None:
    """Otherwise a preserved snapshot would be served as if it were today's hotspots."""
    _write_snapshot(datetime.now(tz=timezone.utc), [_candidate("weibo")])

    async def dead_fetch(platform, *, top_n):
        raise RuntimeError("HTTP 500")

    monkeypatch.setattr(snapshot, "fetch_hotspot_platform_items", dead_fetch)
    monkeypatch.setenv("HOTSPOT_REFRESH_PLATFORMS", "weibo")
    await snapshot.refresh_hotspot_snapshot(force=True)

    assert snapshot.has_payload() is True
    assert snapshot.last_attempt_succeeded() is False
    assert snapshot.is_fresh() is False


@pytest.mark.asyncio
async def test_failed_refresh_retries_on_the_short_interval(monkeypatch) -> None:
    """A failed refresh must not block the next attempt for a full cycle."""
    stale = datetime.now(tz=timezone.utc) - timedelta(minutes=30)
    snapshot._persist(
        {
            "captured_at": stale.isoformat(),
            "attempted_at": stale.isoformat(),
            "succeeded": False,
            "candidates": [_candidate("weibo")],
        }
    )
    monkeypatch.setenv("HOTSPOT_REFRESH_INTERVAL_MINUTES", "60")
    monkeypatch.setenv("HOTSPOT_RETRY_INTERVAL_MINUTES", "5")

    # 30 minutes have passed: well short of the 60-minute interval, well past the 5-minute retry.
    assert snapshot.due_for_refresh() is True


@pytest.mark.asyncio
async def test_recovered_refresh_replaces_the_preserved_data(monkeypatch) -> None:
    """Recovery must actually take effect, not leave the stale copy in place."""
    _write_snapshot(datetime.now(tz=timezone.utc), [_candidate("weibo", "旧热点")])

    async def dead_fetch(platform, *, top_n):
        raise RuntimeError("HTTP 500")

    monkeypatch.setattr(snapshot, "fetch_hotspot_platform_items", dead_fetch)
    monkeypatch.setenv("HOTSPOT_REFRESH_PLATFORMS", "weibo")
    await snapshot.refresh_hotspot_snapshot(force=True)
    assert snapshot.get_snapshot()["candidates"][0]["title"] == "旧热点"

    async def good_fetch(platform, *, top_n):
        return [_candidate("weibo", "新热点")]

    monkeypatch.setattr(snapshot, "fetch_hotspot_platform_items", good_fetch)
    await snapshot.refresh_hotspot_snapshot(force=True)

    recovered = snapshot.get_snapshot()
    assert recovered["candidates"][0]["title"] == "新热点"
    assert recovered["succeeded"] is True
    assert snapshot.is_fresh() is True


def test_last_success_timestamp_is_preserved_across_failures() -> None:
    """Operators need to know how old the newest real data is."""
    good = datetime.now(tz=timezone.utc) - timedelta(hours=3)
    snapshot._persist(
        {
            "captured_at": good.isoformat(),
            "attempted_at": good.isoformat(),
            "last_success_at": good.isoformat(),
            "succeeded": True,
            "candidates": [_candidate("weibo")],
        }
    )

    assert snapshot.get_snapshot()["last_success_at"] == good.isoformat()


def test_recently_failed_platforms_is_only_trusted_when_fresh() -> None:
    """A stale failure list says nothing about what the upstream is doing now."""
    snapshot._persist(
        {
            "captured_at": (datetime.now(tz=timezone.utc) - timedelta(hours=10)).isoformat(),
            "attempted_at": (datetime.now(tz=timezone.utc) - timedelta(hours=10)).isoformat(),
            "succeeded": True,
            "failed_platforms": ["mktnews"],
            "candidates": [_candidate("weibo")],
        }
    )

    assert snapshot.recently_failed_platforms() == set()


def test_recently_failed_platforms_reported_when_fresh() -> None:
    snapshot._persist(
        {
            "captured_at": datetime.now(tz=timezone.utc).isoformat(),
            "attempted_at": datetime.now(tz=timezone.utc).isoformat(),
            "succeeded": True,
            "failed_platforms": ["mktnews"],
            "candidates": [_candidate("weibo")],
        }
    )

    assert snapshot.recently_failed_platforms() == {"mktnews"}
