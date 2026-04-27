from __future__ import annotations

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
