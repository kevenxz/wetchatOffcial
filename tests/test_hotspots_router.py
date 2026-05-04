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
            "keywords": "OpenAI 新模型发布",
            "hotspot_capture_config": {"enabled": True},
            "hotspot_candidates": [
                {
                    "source": "tophub",
                    "category": "AI",
                    "platform_name": "知乎热榜",
                    "title": "OpenAI 新模型发布",
                    "url": "https://example.com/openai",
                    "selection_score": 92,
                    "extra_text": "热度 12000",
                }
            ],
            "selected_hotspot": {"title": "OpenAI 新模型发布"},
            "hotspot_capture_error": None,
        }

    try:
        monkeypatch.setattr(hotspots, "capture_hot_topics_node", fake_capture_hot_topics_node)
        client = TestClient(_build_app())

        response = client.post(
            "/api/hotspots/preview",
            json={
                "keywords": "热点预览",
                "hotspot_capture": {"enabled": True, "source": "tophub"},
            },
        )

        assert response.status_code == 200
        assert response.json()["hotspot_candidates"][0]["title"] == "OpenAI 新模型发布"
        topics = list(store.topic_store.values())
        assert len(topics) == 1
        assert topics[0].title == "OpenAI 新模型发布"
        assert topics[0].score == 92
        assert topics[0].metadata["platform_name"] == "知乎热榜"
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
                title="OpenAI 新模型发布",
                summary="模型能力更新",
                source="36氪",
                url="https://example.com/openai",
                score=92,
                tags=["AI"],
                metadata={
                    "selection_score": 92,
                    "risk_score": 8,
                    "channel_count": 5,
                    "platform_name": "36氪",
                },
                created_at=datetime.now(tz=timezone.utc),
            )
        )

        response = client.get("/api/hotspots/monitor")

        assert response.status_code == 200
        payload = response.json()
        assert payload["stats"]["total"] == 1
        assert payload["stats"]["recommended"] == 1
        assert payload["items"][0]["title"] == "OpenAI 新模型发布"
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
            "keywords": "OpenAI 新模型发布",
            "hotspot_capture_config": {"enabled": True},
            "hotspot_candidates": [
                {
                    "source": "tophub",
                    "category": "AI",
                    "platform_name": "知乎热榜",
                    "title": "OpenAI 新模型发布",
                    "url": "https://example.com/openai",
                    "selection_score": 92,
                    "risk_score": 8,
                    "extra_text": "热度 12000",
                }
            ],
            "selected_hotspot": {"title": "OpenAI 新模型发布"},
            "hotspot_capture_error": None,
        }

    try:
        monkeypatch.setattr(hotspots, "capture_hot_topics_node", fake_capture_hot_topics_node)
        client = TestClient(_build_app())

        response = client.post(
            "/api/hotspots/monitor/capture",
            json={
                "keywords": "热点监控",
                "hotspot_capture": {"enabled": True, "source": "tophub"},
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["items"][0]["title"] == "OpenAI 新模型发布"
        assert payload["items"][0]["recommended"] is True
        assert len(store.topic_store) == 1
    finally:
        store.topic_store.clear()
        store.topic_store.update(topic_backup)
