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
from workflow.article_generation import normalize_generation_config
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
                next_generation_config = res.get("generation_config")
                if isinstance(next_generation_config, dict):
                    task.generation_config = task.generation_config.model_copy(update=next_generation_config)
                next_keywords = res.get("keywords")
                if isinstance(next_keywords, str) and next_keywords.strip():
                    task.keywords = next_keywords.strip()
                next_original_keywords = res.get("original_keywords")
                if isinstance(next_original_keywords, str) and next_original_keywords.strip():
                    task.original_keywords = next_original_keywords.strip()
                hotspot_capture_config = res.get("hotspot_capture_config")
                if isinstance(hotspot_capture_config, dict):
                    task.hotspot_capture_config = hotspot_capture_config
                hotspot_candidates = res.get("hotspot_candidates")
                if isinstance(hotspot_candidates, list):
                    task.hotspot_candidates = hotspot_candidates
                selected_hotspot = res.get("selected_hotspot")
                if isinstance(selected_hotspot, dict) or selected_hotspot is None:
                    task.selected_hotspot = selected_hotspot
                task.task_brief = res.get("task_brief")
                task.planning_state = res.get("planning_state")
                task.research_state = res.get("research_state")
                task.writing_state = res.get("writing_state")
                task.visual_state = res.get("visual_state")
                task.quality_state = res.get("quality_state")
                task.user_intent = res.get("user_intent")
                task.style_profile = res.get("style_profile")
                task.article_blueprint = res.get("article_blueprint")
                task.article_plan = res.get("article_plan")
                task.generated_article = res.get("generated_article")
                task.draft_info = res.get("draft_info")
            
        # 状态变更后持久化
        save_tasks()

    await manager.broadcast(task_id, data)


async def _run_task(task_id: str, keywords: str, generation_config: dict) -> None:
    """后台任务：运行 LangGraph 工作流。"""
    try:
        await run_workflow(
            task_id,
            keywords,
            generation_config=generation_config,
            hotspot_capture_config=None,
            progress_callback=_progress_callback,
        )
    except Exception as exc:
        logger.exception("background_task_failed", task_id=task_id, error=str(exc))


@router.post("", response_model=TaskResponse, status_code=201)
async def create_task(body: CreateTaskRequest) -> TaskResponse:
    """创建新任务并在后台启动工作流。"""
    task = TaskResponse(
        task_id=str(uuid.uuid4()),
        keywords=body.keywords,
        original_keywords=body.keywords,
        generation_config=body.generation_config,
        status=TaskStatus.pending,
        created_at=datetime.now(tz=timezone.utc),
    )
    task_store[task.task_id] = task
    save_tasks()

    # 异步启动工作流（不阻塞响应）
    asyncio.create_task(
        _run_task(
            task.task_id,
            task.keywords,
            normalize_generation_config(task.generation_config.model_dump()),
        )
    )

    logger.info("task_created", task_id=task.task_id, keywords=task.keywords)
    return task


async def _retry_task(task_id: str, keywords: str, memory_state: dict, generation_config: dict) -> None:
    """后台任务：从指定状态恢复并重试 LangGraph 工作流。"""
    try:
        await run_workflow(
            task_id,
            keywords,
            generation_config=generation_config,
            hotspot_capture_config=memory_state.get("hotspot_capture_config"),
            progress_callback=_progress_callback,
            resume_state=memory_state,
        )
    except Exception as exc:
        logger.exception("background_task_retry_failed", task_id=task_id, error=str(exc))


@router.post("/{task_id}/retry", response_model=TaskResponse)
async def retry_task(
    task_id: Annotated[str, Path(description="任务 ID")],
) -> TaskResponse:
    """重新执行失败的任务，将从失败跳过的节点继续执行。"""
    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_id!r} 不存在")
        
    if task.status not in (TaskStatus.failed, TaskStatus.done):
        raise HTTPException(status_code=400, detail="只能重试失败或已终止的任务")
        
    # 重置外层任务状态为等待中
    task.status = TaskStatus.pending
    task.error = None
    save_tasks()
    
    # 尝试将 Pydantic model 转换回 state 期望的 dict 结构以供恢复
    memory_state = {
        "task_id": task.task_id,
        "keywords": task.keywords,
        "original_keywords": task.original_keywords or task.keywords,
        "generation_config": normalize_generation_config(task.generation_config.model_dump()),
        "hotspot_capture_config": task.hotspot_capture_config or {},
        "task_brief": task.task_brief or {},
        "planning_state": task.planning_state or {},
        "research_state": task.research_state or {},
        "writing_state": task.writing_state or {},
        "visual_state": task.visual_state or {},
        "quality_state": task.quality_state or {},
        "hotspot_candidates": task.hotspot_candidates or [],
        "selected_hotspot": task.selected_hotspot,
        "hotspot_capture_error": None,
        "user_intent": task.user_intent or {},
        "style_profile": task.style_profile or {},
        "article_blueprint": task.article_blueprint or {},
        "search_queries": [],
        "search_results": [],
        "extracted_contents": [],
        "article_plan": task.article_plan or {},
        "generated_article": task.generated_article or {},
        "draft_info": task.draft_info,
        "retry_count": 0,
        "error": None,
        "status": "running",
        "current_skill": "",
        "progress": 0,
        "skip_auto_push": False,
        # 很多提取的信息没有通过 TaskResponse 落盘，如果在实际中我们需要完整恢复，应该将 run_workflow 的 final_state 返回持久化。
        # 这里为了简化，只透传必要字段，对于丢失的 content 列表，如果在此阶段之后还需要可能就会失败。
        # 由于失败往往是在推送报错，到了这步 generated_article 已经存在了。
    }
    
    # 异步启动工作流
    asyncio.create_task(
        _retry_task(
            task.task_id,
            task.keywords,
            memory_state,
            normalize_generation_config(task.generation_config.model_dump()),
        )
    )
    
    logger.info("task_retry_started", task_id=task.task_id)
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
