"""Task CRUD routes."""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Annotated

import structlog
from fastapi import APIRouter, HTTPException, Path

from api.models import CreateTaskRequest, TaskResponse, TaskStatus
from api.store import delete_workflow_run_steps_for_task, save_tasks, task_store
from api.workflow_sync import sync_task_from_workflow_event
from api.ws_manager import manager
from workflow.graph import run_workflow

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/tasks", tags=["tasks"])


async def _progress_callback(task_id: str, data: dict) -> None:
    """Persist workflow progress and broadcast it to WebSocket clients."""
    task = task_store.get(task_id)
    if task:
        sync_task_from_workflow_event(task, data)
        save_tasks()

    await manager.broadcast(task_id, data)


async def _run_task(
    task_id: str,
    keywords: str,
    generation_config: dict,
    hotspot_capture_config: dict | None,
) -> None:
    """Run a LangGraph workflow in the background."""
    try:
        await run_workflow(
            task_id,
            keywords,
            generation_config=generation_config,
            hotspot_capture_config=hotspot_capture_config,
            progress_callback=_progress_callback,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("background_task_failed", task_id=task_id, error=str(exc))


@router.post("", response_model=TaskResponse, status_code=201)
async def create_task(body: CreateTaskRequest) -> TaskResponse:
    """Create a task and start the workflow asynchronously."""
    task = TaskResponse(
        task_id=str(uuid.uuid4()),
        keywords=body.keywords,
        original_keywords=body.keywords,
        generation_config=body.generation_config,
        status=TaskStatus.pending,
        created_at=datetime.now(tz=timezone.utc),
        hotspot_capture_config=body.hotspot_capture_config,
    )
    task_store[task.task_id] = task
    save_tasks()

    asyncio.create_task(
        _run_task(
            task.task_id,
            task.keywords,
            task.generation_config.model_dump(),
            task.hotspot_capture_config,
        )
    )

    logger.info("task_created", task_id=task.task_id, keywords=task.keywords)
    return task


async def _retry_task(task_id: str, keywords: str, memory_state: dict, generation_config: dict) -> None:
    """Retry a workflow using the persisted task state as seed context."""
    try:
        await run_workflow(
            task_id,
            keywords,
            generation_config=generation_config,
            hotspot_capture_config=memory_state.get("hotspot_capture_config"),
            progress_callback=_progress_callback,
            resume_state=memory_state,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("background_task_retry_failed", task_id=task_id, error=str(exc))


@router.post("/{task_id}/retry", response_model=TaskResponse)
async def retry_task(
    task_id: Annotated[str, Path(description="Task ID")],
) -> TaskResponse:
    """Retry a failed or completed task with its current persisted configuration."""
    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"task {task_id!r} not found")

    if task.status not in (TaskStatus.failed, TaskStatus.done):
        raise HTTPException(status_code=400, detail="only failed or completed tasks can be retried")

    task.status = TaskStatus.pending
    task.error = None
    task.human_review_required = False
    save_tasks()

    memory_state = {
        "task_id": task.task_id,
        "mode": task.mode or "manual",
        "keywords": task.keywords,
        "original_keywords": task.original_keywords or task.keywords,
        "generation_config": task.generation_config.model_dump(),
        "config_snapshot": task.config_snapshot or {},
        "hotspot_capture_config": task.hotspot_capture_config or {},
        "task_brief": task.task_brief or {},
        "planning_state": task.planning_state or {},
        "research_state": task.research_state or {},
        "writing_state": task.writing_state or {},
        "visual_state": task.visual_state or {},
        "quality_state": task.quality_state or {},
        "hotspot_candidates": task.hotspot_candidates or [],
        "selected_hotspot": task.selected_hotspot,
        "selected_topic": task.selected_topic,
        "hotspot_capture_error": task.hotspot_capture_error,
        "user_intent": task.user_intent or {},
        "style_profile": task.style_profile or {},
        "article_blueprint": task.article_blueprint or {},
        "search_queries": [],
        "search_results": [],
        "extracted_contents": [],
        "article_plan": task.article_plan or {},
        "outline_result": task.outline_result or {},
        "generated_article": task.generated_article or {},
        "final_article": task.final_article or {},
        "draft_info": task.draft_info,
        "retry_count": 0,
        "error": None,
        "status": "running",
        "current_skill": "",
        "progress": 0,
        "skip_auto_push": False,
    }

    asyncio.create_task(
        _retry_task(
            task.task_id,
            task.keywords,
            memory_state,
            task.generation_config.model_dump(),
        )
    )

    logger.info("task_retry_started", task_id=task.task_id)
    return task


@router.get("", response_model=list[TaskResponse])
async def list_tasks() -> list[TaskResponse]:
    """List all tasks by creation time descending."""
    return sorted(task_store.values(), key=lambda t: t.created_at, reverse=True)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: Annotated[str, Path(description="Task ID")],
) -> TaskResponse:
    """Get one task."""
    task = task_store.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"task {task_id!r} not found")
    return task


@router.delete("/{task_id}", status_code=204, response_model=None)
async def delete_task(
    task_id: Annotated[str, Path(description="Task ID")],
) -> None:
    """Delete one task record."""
    if task_id not in task_store:
        raise HTTPException(status_code=404, detail=f"task {task_id!r} not found")
    del task_store[task_id]
    delete_workflow_run_steps_for_task(task_id)
    save_tasks()
