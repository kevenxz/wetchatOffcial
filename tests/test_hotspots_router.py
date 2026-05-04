from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import store
from api.routers import hotspots


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(hotspots.router, prefix="/api")
    return app


def test_hotspot_preview_persists_candidates_to_topic_pool(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(store, "TOPICS_FILE", tmp_path / "topics.json")
    topic_backup = dict(store.topic_store)
    store.topic_store.clear()

    async def fake_capture_hot_topics_node(_state):
        return {
            "keywords": "OpenAI release",
            "hotspot_capture_config": {"enabled": True},
            "hotspot_candidates": [
                {
                    "source": "tophub",
                    "category": "AI",
                    "platform_name": "zhihu",
                    "title": "OpenAI releases new model",
                    "url": "https://example.com/openai",
                    "selection_score": 92,
                    "extra_text": "hot 12000",
                }
            ],
            "selected_hotspot": {"title": "OpenAI releases new model"},
            "hotspot_capture_error": None,
        }

    try:
        monkeypatch.setattr(hotspots, "capture_hot_topics_node", fake_capture_hot_topics_node)
        client = TestClient(_build_app())

        response = client.post(
            "/api/hotspots/preview",
            json={
                "keywords": "preview",
                "hotspot_capture": {"enabled": True, "source": "tophub"},
            },
        )

        assert response.status_code == 200
        assert response.json()["hotspot_candidates"][0]["title"] == "OpenAI releases new model"
        topics = list(store.topic_store.values())
        assert len(topics) == 1
        assert topics[0].title == "OpenAI releases new model"
        assert topics[0].score == 92
        assert topics[0].metadata["platform_name"] == "zhihu"
    finally:
        store.topic_store.clear()
        store.topic_store.update(topic_backup)


def test_hotspot_monitor_returns_normalized_items(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(store, "TOPICS_FILE", tmp_path / "topics.json")
    topic_backup = dict(store.topic_store)
    store.topic_store.clear()

    try:
        client = TestClient(_build_app())
        store.create_topic(
            store.TopicCandidate(
                topic_id="topic-1",
                title="OpenAI releases new model",
                summary="model capability update",
                source="36kr",
                url="https://example.com/openai",
                score=92,
                tags=["AI"],
                metadata={
                    "selection_score": 92,
                    "risk_score": 8,
                    "channel_count": 5,
                    "platform_name": "36kr",
                },
                created_at=datetime.now(tz=timezone.utc),
            )
        )

        response = client.get("/api/hotspots/monitor")

        assert response.status_code == 200
        payload = response.json()
        assert payload["stats"]["total"] == 1
        assert payload["stats"]["recommended"] == 1
        assert payload["items"][0]["title"] == "OpenAI releases new model"
        assert payload["items"][0]["category"] == "AI"
        assert payload["items"][0]["hot_score"] == 92
        assert payload["items"][0]["account_fit_score"] == 92
        assert payload["items"][0]["risk_score"] == 8
        assert payload["items"][0]["recommended"] is True
    finally:
        store.topic_store.clear()
        store.topic_store.update(topic_backup)


def test_hotspot_monitor_capture_persists_and_returns_monitor(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(store, "TOPICS_FILE", tmp_path / "topics.json")
    topic_backup = dict(store.topic_store)
    store.topic_store.clear()

    async def fake_capture_hot_topics_node(_state):
        return {
            "keywords": "OpenAI release",
            "hotspot_capture_config": {"enabled": True},
            "hotspot_candidates": [
                {
                    "source": "tophub",
                    "category": "AI",
                    "platform_name": "zhihu",
                    "title": "OpenAI releases new model",
                    "url": "https://example.com/openai",
                    "selection_score": 92,
                    "risk_score": 8,
                    "extra_text": "hot 12000",
                }
            ],
            "selected_hotspot": {"title": "OpenAI releases new model"},
            "hotspot_capture_error": None,
        }

    try:
        monkeypatch.setattr(hotspots, "capture_hot_topics_node", fake_capture_hot_topics_node)
        client = TestClient(_build_app())

        response = client.post(
            "/api/hotspots/monitor/capture",
            json={
                "keywords": "monitor",
                "hotspot_capture": {"enabled": True, "source": "tophub"},
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["items"][0]["title"] == "OpenAI releases new model"
        assert payload["items"][0]["recommended"] is True
        assert len(store.topic_store) == 1
    finally:
        store.topic_store.clear()
        store.topic_store.update(topic_backup)


def test_hotspot_platform_catalog_returns_builtin_n_paths() -> None:
    client = TestClient(_build_app())

    response = client.get("/api/hotspots/platforms?categories=科技&categories=AI&limit_per_category=4")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "tophub"
    paths = {item["path"] for item in payload["items"]}
    assert "/n/mproPpoq6O" in paths
    assert "/n/Q1Vd5Ko85R" in paths
    assert all(path.startswith("/n/") for path in paths)


def test_hotspot_platform_catalog_discovers_multiple_sources_when_builtin_misses(monkeypatch) -> None:
    class FakeTopHubClient:
        async def fetch_category_platforms(self, category, *, limit=20):
            return [
                {
                    "name": f"{category}-A",
                    "path": f"/n/{category}-a",
                    "category": category,
                    "weight": 1,
                    "enabled": True,
                },
                {
                    "name": f"{category}-B",
                    "path": "/n/shared",
                    "category": category,
                    "weight": 1,
                    "enabled": True,
                },
            ][:limit]

    monkeypatch.setattr(hotspots, "TopHubClient", FakeTopHubClient)
    client = TestClient(_build_app())

    response = client.get("/api/hotspots/platforms?categories=Finance&limit_per_category=2")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "tophub"
    assert [item["path"] for item in payload["items"]] == ["/n/Finance-a", "/n/shared"]


def test_hotspot_monitor_capture_accepts_multiple_platforms(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(store, "TOPICS_FILE", tmp_path / "topics.json")
    topic_backup = dict(store.topic_store)
    store.topic_store.clear()
    captured_platforms = []

    async def fake_capture_hot_topics_node(state):
        captured_platforms.extend(state["hotspot_capture_config"]["platforms"])
        return {
            "keywords": "OpenAI release",
            "hotspot_capture_config": state["hotspot_capture_config"],
            "hotspot_candidates": [],
            "selected_hotspot": None,
            "hotspot_capture_error": None,
        }

    try:
        monkeypatch.setattr(hotspots, "capture_hot_topics_node", fake_capture_hot_topics_node)
        client = TestClient(_build_app())

        response = client.post(
            "/api/hotspots/monitor/capture",
            json={
                "keywords": "hotspot monitor",
                "hotspot_capture": {
                    "enabled": True,
                    "source": "tophub",
                    "platforms": [
                        {"name": "36kr", "path": "/n/Q1Vd5Ko85R", "weight": 1.2, "enabled": True},
                        {"name": "zhihu", "path": "https://tophub.today/n/mproPpoq6O", "weight": 1, "enabled": True},
                    ],
                },
            },
        )

        assert response.status_code == 200
        assert [item["path"] for item in captured_platforms] == ["/n/Q1Vd5Ko85R", "/n/mproPpoq6O"]
        assert captured_platforms[0]["weight"] == 1.2
    finally:
        store.topic_store.clear()
        store.topic_store.update(topic_backup)
