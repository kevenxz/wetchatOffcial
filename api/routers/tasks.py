"""任务 CRUD 路由。"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Annotated

import structlog
from fastapi import APIRouter, HTTPException, Path

from api.models import CreateTaskRequest, TaskResponse, TaskStatus
from api.store import task_store, save_tasks
from api.ws_manager import manager
from workflow.graph import run_workflow

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/tasks", tags=["tasks"])


async def _progress_callback(task_id: str, data: dict) -> None:
    """将工作流进度通过 WebSocket 广播给前端。"""
    # 同步更新内存中的任务状态
    task = task_store.get(task_id)
    if task:
        new_status = data.get("status", task.status)
        task.status = TaskStatus(new_status)
        task.updated_at = datetime.now(tz=timezone.utc)
        if new_status == "failed":
            task.error = data.get("message")
            
        if new_status in ("done", "failed") and data.get("result"):
            res = data["result"]
            if isinstance(res, dict):
                task.generated_article = res.get("generated_article")
                task.draft_info = res.get("draft_info")
            
        # 状态变更后持久化
        save_tasks()

    await manager.broadcast(task_id, data)


async def _run_task(task_id: str, keywords: str) -> None:
    """后台任务：运行 LangGraph 工作流。"""
    try:
        await run_workflow(task_id, keywords, progress_callback=_progress_callback)
    except Exception as exc:
        logger.exception("background_task_failed", task_id=task_id, error=str(exc))


@router.post("", response_model=TaskResponse, status_code=201)
async def create_task(body: CreateTaskRequest) -> TaskResponse:
    """创建新任务并在后台启动工作流。"""
    task = TaskResponse(
        task_id=str(uuid.uuid4()),
        keywords=body.keywords,
        status=TaskStatus.pending,
        created_at=datetime.now(tz=timezone.utc),
    )
    task_store[task.task_id] = task
    save_tasks()

    # 异步启动工作流（不阻塞响应）
    asyncio.create_task(_run_task(task.task_id, task.keywords))

    logger.info("task_created", task_id=task.task_id, keywords=task.keywords)
    return task


@router.get("", response_model=list[TaskResponse])
async def list_tasks() -> list[TaskResponse]:
    """获取所有任务列表（按创建时间倒序）。"""
    return sorted(task_store.values(), key=lambda t: t.created_at, reverse=True)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: Annotated[str, Path(description="任务 ID")],
) -> TaskResponse:
    """查询任务状态。"""
    task = task_store.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"任务 {task_id!r} 不存在")
    return task


@router.delete("/{task_id}", status_code=204, response_model=None)
async def delete_task(
    task_id: Annotated[str, Path(description="任务 ID")],
) -> None:
    """删除任务记录。"""
    if task_id not in task_store:
        raise HTTPException(status_code=404, detail=f"任务 {task_id!r} 不存在")
    del task_store[task_id]
    save_tasks()
