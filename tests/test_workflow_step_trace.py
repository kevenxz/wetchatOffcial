from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import store
from api.models import GenerationConfig, TaskResponse, TaskStatus, WorkflowRunStepRecord, WorkflowRunStepStatus
from api.routers import tasks
from workflow import graph as workflow_graph
from workflow.utils.step_trace import sanitize_step_payload


def test_sanitize_step_payload_redacts_sensitive_fields_and_truncates_text() -> None:
    payload = sanitize_step_payload(
        {
            "api_key": "secret-key",
            "nested": {"access_token": "token-value", "safe": "ok"},
            "text": "x" * 6000,
        }
    )

    assert payload["api_key"] == "[REDACTED]"
    assert payload["nested"]["access_token"] == "[REDACTED]"
    assert payload["nested"]["safe"] == "ok"
    assert payload["text"]["truncated"] is True
    assert payload["text"]["length"] == 6000


@pytest.mark.asyncio
async def test_run_workflow_records_step_input_and_output(monkeypatch, tmp_path) -> None:
    class FakeGraph:
        async def astream(self, _initial_state):  # noqa: ANN001
            yield {
                "planner_agent": {
                    "status": "running",
                    "current_skill": "planner_agent",
                    "progress": 12,
                    "planning_state": {"search_contract": {"topic": "AI"}},
                }
            }

    step_backup = dict(store.workflow_run_step_store)
    store.workflow_run_step_store.clear()
    monkeypatch.setattr(store, "WORKFLOW_RUN_STEPS_FILE", tmp_path / "workflow_run_steps.json")
    monkeypatch.setattr(workflow_graph, "_compiled_graph", FakeGraph())

    try:
        await workflow_graph.run_workflow(
            task_id="task-trace",
            keywords="AI",
            generation_config={},
            hotspot_capture_config={},
        )

        steps = store.list_workflow_run_steps(task_id="task-trace")
        assert len(steps) == 1
        step = steps[0]
        assert step.step_name == "planner_agent"
        assert step.status == WorkflowRunStepStatus.succeeded
        assert step.payload["input_state"]["keywords"] == "AI"
        assert step.payload["output"]["planning_state"]["search_contract"]["topic"] == "AI"
        assert step.payload["state_after"]["planning_state"]["search_contract"]["topic"] == "AI"
        assert step.payload["duration_ms"] >= 0
    finally:
        store.workflow_run_step_store.clear()
        store.workflow_run_step_store.update(step_backup)


def test_delete_task_removes_workflow_steps(monkeypatch, tmp_path) -> None:
    app = FastAPI()
    app.include_router(tasks.router, prefix="/api")
    client = TestClient(app)
    task_backup = dict(store.task_store)
    step_backup = dict(store.workflow_run_step_store)
    store.task_store.clear()
    store.workflow_run_step_store.clear()
    monkeypatch.setattr(store, "TASKS_FILE", tmp_path / "tasks.json")
    monkeypatch.setattr(store, "WORKFLOW_RUN_STEPS_FILE", tmp_path / "workflow_run_steps.json")

    task = TaskResponse(
        task_id="task-delete-steps",
        keywords="AI",
        original_keywords="AI",
        generation_config=GenerationConfig(),
        status=TaskStatus.done,
        created_at=datetime.now(tz=timezone.utc),
    )
    store.task_store[task.task_id] = task
    store.workflow_run_step_store["step-1"] = WorkflowRunStepRecord(
        run_step_id="step-1",
        run_id="run-1",
        task_id=task.task_id,
        step_name="planner_agent",
        status=WorkflowRunStepStatus.succeeded,
        payload={},
        created_at=datetime.now(tz=timezone.utc),
    )

    try:
        response = client.delete(f"/api/tasks/{task.task_id}")

        assert response.status_code == 204
        assert task.task_id not in store.task_store
        assert store.list_workflow_run_steps(task_id=task.task_id) == []
    finally:
        store.task_store.clear()
        store.task_store.update(task_backup)
        store.workflow_run_step_store.clear()
        store.workflow_run_step_store.update(step_backup)
