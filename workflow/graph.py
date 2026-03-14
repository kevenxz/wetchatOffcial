"""LangGraph 工作流定义：StateGraph 构建与节点注册。"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Coroutine
from typing import Any

import structlog
from langgraph.graph import END, StateGraph

from workflow.state import WorkflowState
from workflow.skills.search_web import search_web_node
from workflow.skills.fetch_extract import fetch_extract_node
from workflow.skills.generate_article import generate_article_node
from workflow.skills.generate_images import generate_images_node
from workflow.skills.push_to_draft import push_to_draft_node
from workflow.skills.ui_feedback import ui_feedback_node
from workflow.skills.error_handler import error_handler

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# 类型别名：进度回调 (task_id, data_dict) -> None
# ---------------------------------------------------------------------------
ProgressCallback = Callable[[str, dict], Coroutine[Any, Any, None]]


# ---------------------------------------------------------------------------
# 节点：initialize — 任务初始化
# ---------------------------------------------------------------------------
async def initialize_node(state: WorkflowState) -> dict:
    """初始化节点：标记任务为 running，准备后续执行。"""
    start = time.monotonic()

    logger.info(
        "skill_start",
        task_id=state["task_id"],
        skill="initialize",
        status="running",
        keywords=state["keywords"],
    )

    # 模拟初始化耗时（环境检查等）
    await asyncio.sleep(0.5)

    duration_ms = round((time.monotonic() - start) * 1000)
    logger.info(
        "skill_done",
        task_id=state["task_id"],
        skill="initialize",
        status="done",
        duration_ms=duration_ms,
    )

    return {
        "status": "running",
        "current_skill": "initialize",
        "progress": 10,
    }


# ---------------------------------------------------------------------------
# 路由条件
# ---------------------------------------------------------------------------
def _route_status(state: WorkflowState) -> str:
    """检查状态，如果有失败则流转到 error_handler"""
    return "error" if state.get("status") == "failed" else "next"

# ---------------------------------------------------------------------------
# 构建 StateGraph
# ---------------------------------------------------------------------------
def build_graph() -> StateGraph:
    """构建并返回编译后的工作流图。"""
    graph = StateGraph(WorkflowState)

    # 注册节点
    graph.add_node("initialize", initialize_node)
    graph.add_node("search_web", search_web_node)
    graph.add_node("fetch_extract", fetch_extract_node)
    graph.add_node("generate_article", generate_article_node)
    graph.add_node("generate_images", generate_images_node)
    graph.add_node("push_to_draft", push_to_draft_node)
    graph.add_node("ui_feedback", ui_feedback_node)
    graph.add_node("error_handler", error_handler)

    # 设定边和路由
    graph.set_entry_point("initialize")
    graph.add_edge("initialize", "search_web")
    
    graph.add_conditional_edges("search_web", _route_status, {"error": "error_handler", "next": "fetch_extract"})
    graph.add_conditional_edges("fetch_extract", _route_status, {"error": "error_handler", "next": "generate_article"})
    graph.add_conditional_edges("generate_article", _route_status, {"error": "error_handler", "next": "generate_images"})
    graph.add_conditional_edges("generate_images", _route_status, {"error": "error_handler", "next": "push_to_draft"})
    graph.add_conditional_edges("push_to_draft", _route_status, {"error": "error_handler", "next": "ui_feedback"})
    
    graph.add_edge("ui_feedback", END)
    graph.add_edge("error_handler", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# 运行入口
# ---------------------------------------------------------------------------
_compiled_graph = build_graph()


async def run_workflow(
    task_id: str,
    keywords: str,
    progress_callback: ProgressCallback | None = None,
) -> WorkflowState:
    """异步运行工作流，并在每个节点完成后调用进度回调。

    Args:
        task_id: 任务唯一 ID。
        keywords: 用户输入的关键词。
        progress_callback: 可选的进度回调函数。

    Returns:
        最终的 WorkflowState。
    """
    start = time.monotonic()

    initial_state: WorkflowState = {
        "task_id": task_id,
        "keywords": keywords,
        "search_results": [],
        "extracted_contents": [],
        "generated_article": {},
        "draft_info": None,
        "retry_count": 0,
        "error": None,
        "status": "pending",
        "current_skill": "",
        "progress": 0,
    }

    logger.info(
        "workflow_start",
        task_id=task_id,
        skill="workflow",
        status="running",
        keywords=keywords,
    )

    # 通知客户端任务已开始
    if progress_callback:
        await progress_callback(task_id, {
            "task_id": task_id,
            "status": "pending",
            "current_skill": "",
            "progress": 0,
            "message": "任务已创建，准备执行…",
            "result": None,
        })

    final_state: WorkflowState | None = None

    try:
        async for event in _compiled_graph.astream(initial_state):
            # LangGraph astream 每一步返回 {node_name: output_dict}
            for node_name, output in event.items():
                if progress_callback:
                    await progress_callback(task_id, {
                        "task_id": task_id,
                        "status": output.get("status", "running"),
                        "current_skill": output.get("current_skill", node_name),
                        "progress": output.get("progress", 0),
                        "message": f"节点 [{node_name}] 执行完成",
                        "result": None,
                    })
                final_state = output  # type: ignore[assignment]

        duration_ms = round((time.monotonic() - start) * 1000)
        
        # 检查最终状态是否失败
        is_failed = final_state and final_state.get("status") == "failed"
        final_status = "failed" if is_failed else "done"
        final_message = "工作流执行失败" if is_failed else "任务执行完成"

        logger.info(
            f"workflow_{final_status}",
            task_id=task_id,
            skill="workflow",
            status=final_status,
            duration_ms=duration_ms,
        )

        if progress_callback:
            await progress_callback(task_id, {
                "task_id": task_id,
                "status": final_status,
                "current_skill": "",
                "progress": 100 if not is_failed else final_state.get("progress", 0),
                "message": final_message,
                "result": {
                    "generated_article": final_state.get("generated_article") if final_state else None,
                    "draft_info": final_state.get("draft_info") if final_state else None,
                },
            })

    except Exception as exc:
        duration_ms = round((time.monotonic() - start) * 1000)

        logger.exception(
            "workflow_failed",
            task_id=task_id,
            skill="workflow",
            status="failed",
            duration_ms=duration_ms,
            error=str(exc),
        )

        if progress_callback:
            await progress_callback(task_id, {
                "task_id": task_id,
                "status": "failed",
                "current_skill": "",
                "progress": 0,
                "message": f"工作流执行失败：{exc}",
                "result": None,
            })

    return final_state or initial_state
