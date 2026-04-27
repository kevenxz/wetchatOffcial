"""Workflow run step record routes."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query

from api.models import (
    CreateWorkflowRunStepRequest,
    UpdateWorkflowRunStepRequest,
    WorkflowRunStepRecord,
)
from api.store import (
    create_workflow_run_step,
    get_workflow_run_step,
    list_workflow_run_steps,
    update_workflow_run_step,
)

router = APIRouter(prefix="/workflow-runs", tags=["workflow-runs"])


@router.get("/steps", response_model=list[WorkflowRunStepRecord])
async def get_workflow_run_steps(
    task_id: Annotated[str | None, Query(description="Filter by task id")] = None,
    run_id: Annotated[str | None, Query(description="Filter by run id")] = None,
) -> list[WorkflowRunStepRecord]:
    return list_workflow_run_steps(task_id=task_id, run_id=run_id)


@router.post("/steps", response_model=WorkflowRunStepRecord, status_code=201)
async def add_workflow_run_step(body: CreateWorkflowRunStepRequest) -> WorkflowRunStepRecord:
    step = WorkflowRunStepRecord(
        run_step_id=str(uuid.uuid4()),
        run_id=body.run_id,
        task_id=body.task_id,
        step_name=body.step_name,
        status=body.status,
        payload=body.payload,
        error=body.error,
        started_at=body.started_at,
        ended_at=body.ended_at,
        created_at=datetime.now(tz=timezone.utc),
    )
    return create_workflow_run_step(step)


@router.get("/steps/{run_step_id}", response_model=WorkflowRunStepRecord)
async def get_workflow_run_step_detail(
    run_step_id: Annotated[str, Path(description="Workflow run step ID")],
) -> WorkflowRunStepRecord:
    step = get_workflow_run_step(run_step_id)
    if step is None:
        raise HTTPException(status_code=404, detail=f"workflow run step {run_step_id!r} not found")
    return step


@router.put("/steps/{run_step_id}", response_model=WorkflowRunStepRecord)
async def edit_workflow_run_step(
    run_step_id: Annotated[str, Path(description="Workflow run step ID")],
    body: UpdateWorkflowRunStepRequest,
) -> WorkflowRunStepRecord:
    patch = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    patch["updated_at"] = datetime.now(tz=timezone.utc)
    try:
        return update_workflow_run_step(run_step_id, patch)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
