"""Integration: the capture node consumes the snapshot, and the API exposes it.

Verified live during development: with a fresh snapshot covering the requested platforms,
``capture_hot_topics_node`` made **zero** upstream calls and still produced candidates, a
selected hotspot and rewritten keywords.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import api.hotspot_snapshot as snapshot
import workflow.agents.hotspot as hotspot_module
from api.main import app


@pytest.fixture(autouse=True)
def isolated_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshot, "SNAPSHOT_FILE", tmp_path / "hotspot_snapshot.json")
    snapshot.reset_cache()
    yield
    snapshot.reset_cache()


def _candidate(platform_id: str, title: str, rank: int = 1) -> dict:
    return {
        "title": title,
        "platform_name": platform_id,
        "provider_id": platform_id,
        "path": platform_id,
        "source": "newsnow",
        "rank": rank,
        "category": "社会",
        "platform_weight": 1.1,
        "hot_value": None,
        "url": f"https://example.com/{platform_id}/{rank}",
    }


def _write(candidates: list[dict], *, age_minutes: int = 0) -> None:
    snapshot._persist(
        {
            "captured_at": (datetime.now(tz=timezone.utc) - timedelta(minutes=age_minutes)).isoformat(),
            "source": "newsnow",
            "candidates": candidates,
            "candidate_count": len(candidates),
        }
    )


def _state(platforms: list[dict], *, keywords: str = "人工智能") -> dict:
    return {
        "task_id": "task-snapshot",
        "keywords": keywords,
        "original_keywords": keywords,
        "hotspot_capture_config": {
            "enabled": True,
            "source": "newsnow",
            "categories": [],
            "platforms": platforms,
            "filters": {"top_n_per_platform": 10, "min_selection_score": 0},
            "fallback_topics": [],
        },
    }


WEIBO = {"name": "微博热搜", "path": "weibo", "source": "newsnow", "provider_id": "weibo"}
TOPHUB = {"name": "某TopHub榜", "path": "/n/xxxx", "source": "tophub", "provider_id": "tophub"}


# --------------------------------------------------------------------------- #
# capture node
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_fresh_snapshot_serves_the_task_without_network(monkeypatch) -> None:
    _write([_candidate("weibo", "西藏那曲市7.0级地震"), _candidate("weibo", "国乒女团不敌日本", rank=2)])
    live = AsyncMock(side_effect=AssertionError("upstream must not be called"))
    monkeypatch.setattr(hotspot_module, "fetch_hotspot_platform_items", live)

    result = await hotspot_module.capture_hot_topics_node(_state([WEIBO]))

    live.assert_not_called()
    assert result["hotspot_candidates"]
    assert result["selected_hotspot"] is not None
    assert result["keywords"] == "西藏那曲市7.0级地震"
    assert result["hotspot_capture_error"] is None


@pytest.mark.asyncio
async def test_stale_snapshot_falls_back_to_a_live_fetch(monkeypatch) -> None:
    _write([_candidate("weibo", "旧热点")], age_minutes=600)
    live = AsyncMock(return_value=[_candidate("weibo", "实时热点")])
    monkeypatch.setattr(hotspot_module, "fetch_hotspot_platform_items", live)

    result = await hotspot_module.capture_hot_topics_node(_state([WEIBO]))

    live.assert_awaited()
    assert [item["title"] for item in result["hotspot_candidates"]] == ["实时热点"]


@pytest.mark.asyncio
async def test_partial_coverage_fetches_only_the_uncovered_platform(monkeypatch) -> None:
    _write([_candidate("weibo", "快照热点")])
    live = AsyncMock(return_value=[_candidate("tophub", "实时热点")])
    monkeypatch.setattr(hotspot_module, "fetch_hotspot_platform_items", live)

    result = await hotspot_module.capture_hot_topics_node(_state([WEIBO, TOPHUB]))

    assert live.await_count == 1
    fetched_platform = live.await_args.args[0]
    assert fetched_platform["provider_id"] == "tophub"
    titles = {item["title"] for item in result["hotspot_candidates"]}
    assert titles == {"快照热点", "实时热点"}


@pytest.mark.asyncio
async def test_snapshot_not_covering_any_platform_fetches_everything(monkeypatch) -> None:
    _write([_candidate("douyin", "无关平台热点")])
    live = AsyncMock(return_value=[_candidate("tophub", "实时热点")])
    monkeypatch.setattr(hotspot_module, "fetch_hotspot_platform_items", live)

    result = await hotspot_module.capture_hot_topics_node(_state([TOPHUB]))

    live.assert_awaited()
    assert [item["title"] for item in result["hotspot_candidates"]] == ["实时热点"]


@pytest.mark.asyncio
async def test_task_filters_still_apply_to_snapshot_candidates(monkeypatch) -> None:
    """The snapshot is ranked with no filter; the task's own filters must still bite."""
    _write([_candidate("weibo", "被排除的热点"), _candidate("weibo", "保留的热点", rank=2)])
    monkeypatch.setattr(hotspot_module, "fetch_hotspot_platform_items", AsyncMock(return_value=[]))

    state = _state([WEIBO])
    state["hotspot_capture_config"]["filters"]["exclude_keywords"] = ["排除"]
    result = await hotspot_module.capture_hot_topics_node(state)

    assert [item["title"] for item in result["hotspot_candidates"]] == ["保留的热点"]


@pytest.mark.asyncio
async def test_task_min_score_applies_to_snapshot_candidates(monkeypatch) -> None:
    _write([_candidate("weibo", "低分热点", rank=40)])
    monkeypatch.setattr(hotspot_module, "fetch_hotspot_platform_items", AsyncMock(return_value=[]))

    state = _state([WEIBO])
    state["hotspot_capture_config"]["filters"]["min_selection_score"] = 95
    result = await hotspot_module.capture_hot_topics_node(state)

    assert result["hotspot_candidates"] == []
    # No candidate passed the filter, so it degrades to the fallback topic rather than failing.
    assert result["keywords"] == "人工智能"
    assert result["hotspot_capture_error"]


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_snapshot_endpoint_reports_status(client: TestClient) -> None:
    _write([_candidate("weibo", "热点")])

    body = client.get("/api/hotspots/snapshot").json()

    assert body["available"] is True
    assert body["fresh"] is True
    assert body["candidate_count"] == 1
    assert body["refresh_interval_minutes"] >= 1
    assert len(body["known_platforms"]) == 16


def test_snapshot_endpoint_reports_missing_state(client: TestClient) -> None:
    body = client.get("/api/hotspots/snapshot").json()

    assert body["available"] is False
    assert body["due_for_refresh"] is True


def test_refresh_endpoint_returns_updated_status(client: TestClient, monkeypatch) -> None:
    async def fake_fetch(platform, *, top_n):
        return [_candidate(str(platform.get("provider_id")), "刷新热点")]

    monkeypatch.setattr(snapshot, "fetch_hotspot_platform_items", fake_fetch)
    monkeypatch.setenv("HOTSPOT_REFRESH_PLATFORMS", "weibo")

    response = client.post("/api/hotspots/snapshot/refresh")

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["candidate_count"] == 1
    assert body["failed_platforms"] == []


def test_refresh_endpoint_reports_upstream_failure_as_502(client: TestClient, monkeypatch) -> None:
    def exploding_platforms():
        raise RuntimeError("config blew up")

    monkeypatch.setattr(snapshot, "configured_platforms", exploding_platforms)

    response = client.post("/api/hotspots/snapshot/refresh")

    assert response.status_code == 502


def test_platform_catalogue_now_includes_newsnow(client: TestClient) -> None:
    items = client.get("/api/hotspots/platforms").json()["items"]

    sources = {item["source"] for item in items}
    assert "newsnow" in sources
    newsnow_items = [item for item in items if item["source"] == "newsnow"]
    assert len(newsnow_items) == 16
    # Existing sources must not be displaced.
    assert "tophub" in sources
