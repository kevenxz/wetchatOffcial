from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import store
from api.routers import workflow_runs


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(workflow_runs.router, prefix="/api")
    return app


def test_workflow_run_step_create_list_and_update(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(store, "WORKFLOW_RUN_STEPS_FILE", tmp_path / "workflow_run_steps.json")
    step_backup = dict(store.workflow_run_step_store)
    store.workflow_run_step_store.clear()

    try:
        client = TestClient(_build_app())
        create_response = client.post(
            "/api/workflow-runs/steps",
            json={
                "run_id": "run-1",
                "task_id": "task-1",
                "step_name": "plan_article",
                "status": "running",
                "payload": {"progress": 30},
            },
        )
        assert create_response.status_code == 201
        created = create_response.json()
        assert created["step_name"] == "plan_article"
        assert created["status"] == "running"

        list_response = client.get("/api/workflow-runs/steps?task_id=task-1")
        assert list_response.status_code == 200
        assert [item["run_step_id"] for item in list_response.json()] == [created["run_step_id"]]

        update_response = client.put(
            f"/api/workflow-runs/steps/{created['run_step_id']}",
            json={"status": "succeeded", "payload": {"progress": 100}},
        )
        assert update_response.status_code == 200
        updated = update_response.json()
        assert updated["status"] == "succeeded"
        assert updated["payload"] == {"progress": 100}
        assert updated["updated_at"] is not None
    finally:
        store.workflow_run_step_store.clear()
        store.workflow_run_step_store.update(step_backup)


def test_workflow_run_step_returns_404_for_missing_record(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(store, "WORKFLOW_RUN_STEPS_FILE", tmp_path / "workflow_run_steps.json")
    step_backup = dict(store.workflow_run_step_store)
    store.workflow_run_step_store.clear()

    try:
        client = TestClient(_build_app())
        response = client.get("/api/workflow-runs/steps/missing")
        assert response.status_code == 404
    finally:
        store.workflow_run_step_store.clear()
        store.workflow_run_step_store.update(step_backup)
