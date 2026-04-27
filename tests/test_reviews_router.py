from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import store
from api.models import GenerationConfig, TaskResponse, TaskStatus
from api.routers import reviews


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(reviews.router, prefix="/api")
    return app


def test_review_queue_pending_and_decisions(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(store, "REVIEWS_FILE", tmp_path / "reviews.json")
    monkeypatch.setattr(store, "TASKS_FILE", tmp_path / "tasks.json")
    review_backup = dict(store.review_store)
    task_backup = dict(store.task_store)
    store.review_store.clear()
    store.task_store.clear()

    try:
        from datetime import datetime, timezone

        store.task_store["task-1"] = TaskResponse(
            task_id="task-1",
            keywords="Review this topic",
            original_keywords="Review this topic",
            generation_config=GenerationConfig(),
            status=TaskStatus.done,
            created_at=datetime.now(tz=timezone.utc),
            human_review_required=True,
            quality_report={"ready_to_publish": False, "article_score": 70},
            quality_state={"human_review_required": True, "ready_to_publish": False},
        )
        client = TestClient(_build_app())
        create_response = client.post(
            "/api/reviews",
            json={
                "target_type": "task",
                "target_id": "task-1",
                "title": "Review this topic",
                "payload": {"score": 91},
            },
        )
        assert create_response.status_code == 201
        created = create_response.json()
        assert created["status"] == "pending"

        pending_response = client.get("/api/reviews/pending")
        assert pending_response.status_code == 200
        assert [item["review_id"] for item in pending_response.json()] == [created["review_id"]]

        approve_response = client.post(
            f"/api/reviews/{created['review_id']}/approve",
            json={"comment": "ok", "reviewer_id": "u-admin"},
        )
        assert approve_response.status_code == 200
        approved = approve_response.json()
        assert approved["status"] == "approved"
        assert approved["decision"] == "approved"
        assert approved["comment"] == "ok"
        assert approved["reviewer_id"] == "u-admin"
        assert approved["decided_at"] is not None
        assert store.task_store["task-1"].human_review_required is False
        assert store.task_store["task-1"].quality_report["ready_to_publish"] is True

        pending_after_decision = client.get("/api/reviews/pending")
        assert pending_after_decision.json() == []
    finally:
        store.review_store.clear()
        store.review_store.update(review_backup)
        store.task_store.clear()
        store.task_store.update(task_backup)


def test_review_reject_and_request_revision(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(store, "REVIEWS_FILE", tmp_path / "reviews.json")
    review_backup = dict(store.review_store)
    store.review_store.clear()

    try:
        client = TestClient(_build_app())
        first = client.post(
            "/api/reviews",
            json={"target_id": "draft-1", "title": "Draft review"},
        ).json()
        second = client.post(
            "/api/reviews",
            json={"target_id": "draft-2", "title": "Draft review 2"},
        ).json()

        reject_response = client.post(f"/api/reviews/{first['review_id']}/reject", json={})
        revision_response = client.post(
            f"/api/reviews/{second['review_id']}/request-revision",
            json={"comment": "needs sources"},
        )

        assert reject_response.status_code == 200
        assert reject_response.json()["status"] == "rejected"
        assert revision_response.status_code == 200
        assert revision_response.json()["status"] == "revision_requested"
        assert revision_response.json()["comment"] == "needs sources"
    finally:
        store.review_store.clear()
        store.review_store.update(review_backup)


def test_review_decision_returns_404_for_missing_review(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(store, "REVIEWS_FILE", tmp_path / "reviews.json")
    review_backup = dict(store.review_store)
    store.review_store.clear()

    try:
        client = TestClient(_build_app())
        response = client.post("/api/reviews/missing/approve", json={})
        assert response.status_code == 404
    finally:
        store.review_store.clear()
        store.review_store.update(review_backup)
