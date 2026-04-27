from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import Mock

from api import store
from api.routers import topics


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(topics.router, prefix="/api")
    return app


def test_topic_crud_ignore_and_convert_to_task(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(store, "TOPICS_FILE", tmp_path / "topics.json")
    monkeypatch.setattr(store, "TASKS_FILE", tmp_path / "tasks.json")
    topic_backup = dict(store.topic_store)
    task_backup = dict(store.task_store)
    store.topic_store.clear()
    store.task_store.clear()
    create_task_mock = Mock()

    def fake_create_task(coro):
        coro.close()
        create_task_mock()
        return None

    monkeypatch.setattr(topics.asyncio, "create_task", fake_create_task)

    try:
        client = TestClient(_build_app())
        create_response = client.post(
            "/api/topics",
            json={
                "title": "AI search market shift",
                "summary": "Signals for a new article angle",
                "source": "manual",
                "score": 82,
                "tags": ["ai", "search", "ai"],
            },
        )

        assert create_response.status_code == 201
        created = create_response.json()
        assert created["title"] == "AI search market shift"
        assert created["status"] == "pending"
        assert created["tags"] == ["ai", "search"]

        update_response = client.put(
            f"/api/topics/{created['topic_id']}",
            json={"summary": "Updated angle", "score": 88},
        )
        assert update_response.status_code == 200
        assert update_response.json()["summary"] == "Updated angle"
        assert update_response.json()["score"] == 88

        list_response = client.get("/api/topics?status=pending")
        assert list_response.status_code == 200
        assert [item["topic_id"] for item in list_response.json()] == [created["topic_id"]]

        ignore_response = client.post(f"/api/topics/{created['topic_id']}/ignore")
        assert ignore_response.status_code == 200
        assert ignore_response.json()["status"] == "ignored"

        convert_response = client.post(
            f"/api/topics/{created['topic_id']}/convert-to-task",
            json={},
        )
        assert convert_response.status_code == 201
        task = convert_response.json()
        assert task["keywords"] == "AI search market shift"
        assert task["status"] == "pending"
        assert task["selected_topic"]["topic_id"] == created["topic_id"]

        topic_detail = client.get(f"/api/topics/{created['topic_id']}").json()
        assert topic_detail["status"] == "converted"
        assert topic_detail["task_id"] == task["task_id"]
        create_task_mock.assert_called_once()
    finally:
        store.topic_store.clear()
        store.topic_store.update(topic_backup)
        store.task_store.clear()
        store.task_store.update(task_backup)


def test_topic_detail_returns_404_for_missing_topic(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(store, "TOPICS_FILE", tmp_path / "topics.json")
    topic_backup = dict(store.topic_store)
    store.topic_store.clear()

    try:
        client = TestClient(_build_app())
        response = client.get("/api/topics/missing")
        assert response.status_code == 404
    finally:
        store.topic_store.clear()
        store.topic_store.update(topic_backup)
