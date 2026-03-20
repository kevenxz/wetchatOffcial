"""Workflow graph definition and execution entry."""
from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Coroutine
from typing import Any

import structlog
from langgraph.graph import END, StateGraph

from workflow.skills.error_handler import error_handler
from workflow.skills.fetch_extract import fetch_extract_node
from workflow.skills.generate_article import generate_article_node
from workflow.skills.generate_images import generate_images_node
from workflow.skills.push_to_draft import push_to_draft_node
from workflow.skills.search_web import search_web_node
from workflow.skills.ui_feedback import ui_feedback_node
from workflow.state import WorkflowState

logger = structlog.get_logger(__name__)

ProgressCallback = Callable[[str, dict], Coroutine[Any, Any, None]]


async def initialize_node(state: WorkflowState) -> dict:
    """Workflow first node: mark running and simulate lightweight init step."""
    start = time.monotonic()
    logger.info(
        "skill_start",
        task_id=state["task_id"],
        skill="initialize",
        status="running",
        keywords=state["keywords"],
    )

    await asyncio.sleep(0.5)
    duration_ms = round((time.monotonic() - start) * 1000)
    logger.info(
        "skill_done",
        task_id=state["task_id"],
        skill="initialize",
        status="done",
        duration_ms=duration_ms,
    )
    return {"status": "running", "current_skill": "initialize", "progress": 10}


def _route_status(state: WorkflowState) -> str:
    """Generic error-first router used by most nodes."""
    return "error" if state.get("status") == "failed" else "next"


def _route_after_generate_images(state: WorkflowState) -> str:
    """Route after image generation.

    When `skip_auto_push=True`, workflow exits via `ui_feedback` and the caller
    can perform custom push logic (e.g. schedule multi-account push).
    """
    if state.get("status") == "failed":
        return "error"
    if state.get("skip_auto_push"):
        return "skip_push"
    return "next"


def build_graph() -> StateGraph:
    """Build and compile the workflow graph."""
    graph = StateGraph(WorkflowState)

    graph.add_node("initialize", initialize_node)
    graph.add_node("search_web", search_web_node)
    graph.add_node("fetch_extract", fetch_extract_node)
    graph.add_node("generate_article", generate_article_node)
    graph.add_node("generate_images", generate_images_node)
    graph.add_node("push_to_draft", push_to_draft_node)
    graph.add_node("ui_feedback", ui_feedback_node)
    graph.add_node("error_handler", error_handler)

    graph.set_entry_point("initialize")
    graph.add_edge("initialize", "search_web")

    graph.add_conditional_edges("search_web", _route_status, {"error": "error_handler", "next": "fetch_extract"})
    graph.add_conditional_edges("fetch_extract", _route_status, {"error": "error_handler", "next": "generate_article"})
    graph.add_conditional_edges("generate_article", _route_status, {"error": "error_handler", "next": "generate_images"})
    graph.add_conditional_edges(
        "generate_images",
        _route_after_generate_images,
        {"error": "error_handler", "next": "push_to_draft", "skip_push": "ui_feedback"},
    )
    graph.add_conditional_edges("push_to_draft", _route_status, {"error": "error_handler", "next": "ui_feedback"})
    graph.add_edge("ui_feedback", END)
    graph.add_edge("error_handler", END)

    return graph.compile()


_compiled_graph = build_graph()


async def run_workflow(
    task_id: str,
    keywords: str,
    progress_callback: ProgressCallback | None = None,
    resume_state: dict | None = None,
    skip_auto_push: bool = False,
) -> WorkflowState:
    """Run workflow and stream progress via callback.

    Args:
        skip_auto_push: True to skip built-in push_to_draft node.
    """
    start = time.monotonic()

    if resume_state:
        initial_state = dict(resume_state)
        initial_state["status"] = "running"
        initial_state["error"] = None
        initial_state["retry_count"] = 0
        if "skip_auto_push" not in initial_state:
            initial_state["skip_auto_push"] = skip_auto_push
        logger.info(
            "workflow_resume",
            task_id=task_id,
            skill="workflow",
            status="running",
            resume_from=initial_state.get("current_skill", "unknown"),
        )
    else:
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
            "skip_auto_push": skip_auto_push,
        }
        logger.info(
            "workflow_start",
            task_id=task_id,
            skill="workflow",
            status="running",
            keywords=keywords,
            skip_auto_push=skip_auto_push,
        )

    if progress_callback:
        # Send initial state to allow UI to render immediate feedback.
        await progress_callback(
            task_id,
            {
                "task_id": task_id,
                "status": "pending",
                "current_skill": "",
                "progress": 0,
                "message": "task created, preparing workflow",
                "result": None,
            },
        )

    final_state: dict | None = None
    current_state = dict(initial_state)

    try:
        async for event in _compiled_graph.astream(initial_state):
            for node_name, output in event.items():
                current_state.update(output)
                final_state = current_state
                if progress_callback:
                    # Emit each node completion so client can render fine-grained steps.
                    await progress_callback(
                        task_id,
                        {
                            "task_id": task_id,
                            "status": output.get("status", "running"),
                            "current_skill": output.get("current_skill", node_name),
                            "progress": output.get("progress", 0),
                            "message": f"node [{node_name}] done",
                            "result": None,
                        },
                    )

        duration_ms = round((time.monotonic() - start) * 1000)
        is_failed = bool(final_state and final_state.get("status") == "failed")
        final_status = "failed" if is_failed else "done"
        final_message = "workflow failed" if is_failed else "workflow done"
        logger.info(
            f"workflow_{final_status}",
            task_id=task_id,
            skill="workflow",
            status=final_status,
            duration_ms=duration_ms,
        )

        if progress_callback:
            await progress_callback(
                task_id,
                {
                    "task_id": task_id,
                    "status": final_status,
                    "current_skill": "",
                    "progress": 100 if not is_failed else int(final_state.get("progress", 0) if final_state else 0),
                    "message": final_message,
                    "result": {
                        "generated_article": final_state.get("generated_article") if final_state else None,
                        "draft_info": final_state.get("draft_info") if final_state else None,
                    },
                },
            )
    except Exception as exc:  # noqa: BLE001
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
            await progress_callback(
                task_id,
                {
                    "task_id": task_id,
                    "status": "failed",
                    "current_skill": "",
                    "progress": 0,
                    "message": f"workflow failed: {exc}",
                    "result": None,
                },
            )

    return final_state or initial_state
