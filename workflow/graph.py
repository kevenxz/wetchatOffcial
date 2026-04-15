"""Workflow graph definition and execution entry."""
from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Coroutine
from typing import Any

import structlog
from langgraph.graph import END, StateGraph

from workflow.article_generation import normalize_generation_config
from workflow.skills.analyze_hotspot_opportunities import analyze_hotspot_opportunities_node
from workflow.skills.build_evidence_pack import build_evidence_pack_node
from workflow.skills.compose_draft import compose_draft_node
from workflow.skills.intake_task_brief import intake_task_brief_node
from workflow.skills.planner_agent import planner_agent_node
from workflow.skills.generate_visual_assets import generate_visual_assets_node
from workflow.skills.plan_article_angle import plan_article_angle_node
from workflow.skills.plan_research import plan_research_node
from workflow.skills.plan_visual_assets import plan_visual_assets_node
from workflow.skills.quality_gate import quality_gate_node
from workflow.skills.resolve_article_type import resolve_article_type_node
from workflow.skills.review_article_draft import review_article_draft_node
from workflow.skills.review_visual_assets import review_visual_assets_node
from workflow.skills.run_research import run_research_node
from workflow.skills.targeted_revision import targeted_revision_node
from workflow.skills.build_article_blueprint import build_article_blueprint_node
from workflow.skills.capture_hot_topics import capture_hot_topics_node
from workflow.skills.error_handler import error_handler
from workflow.skills.fetch_extract import fetch_extract_node
from workflow.skills.generate_article import generate_article_node
from workflow.skills.generate_images import generate_images_node
from workflow.skills.infer_style_profile import infer_style_profile_node
from workflow.skills.interpret_user_intent import interpret_user_intent_node
from workflow.skills.plan_search_queries import plan_search_queries_node
from workflow.skills.push_to_draft import push_to_draft_node
from workflow.skills.rank_sources import rank_sources_node
from workflow.skills.search_web import search_web_node
from workflow.skills.ui_feedback import ui_feedback_node
from workflow.state import WorkflowState

logger = structlog.get_logger(__name__)

ProgressCallback = Callable[[str, dict], Coroutine[Any, Any, None]]


async def initialize_node(state: WorkflowState) -> dict:
    """Workflow first node: mark running and perform lightweight init."""
    start = time.monotonic()
    logger.info(
        "skill_start",
        task_id=state["task_id"],
        skill="initialize",
        status="running",
        keywords=state["keywords"],
    )

    await asyncio.sleep(0.2)
    duration_ms = round((time.monotonic() - start) * 1000)
    logger.info(
        "skill_done",
        task_id=state["task_id"],
        skill="initialize",
        status="done",
        duration_ms=duration_ms,
    )
    return {"status": "running", "current_skill": "initialize", "progress": 8}


def _route_status(state: WorkflowState) -> str:
    return "error" if state.get("status") == "failed" else "next"


def _route_after_generate_images(state: WorkflowState) -> str:
    if state.get("status") == "failed":
        return "error"
    if state.get("skip_auto_push"):
        return "skip_push"
    return "next"


def _route_quality_action(state: WorkflowState) -> str:
    if state.get("status") == "failed":
        return "error"

    action = state.get("quality_state", {}).get("next_action")
    if action == "revise_writing":
        return "revise_writing"
    if action == "revise_visuals":
        return "revise_visuals"
    return "pass"


def _route_revision_target(state: WorkflowState) -> str:
    if state.get("status") == "failed":
        return "error"

    action = state.get("quality_state", {}).get("revision_route")
    if action == "revise_writing":
        return "revise_writing"
    if action == "revise_visuals":
        return "revise_visuals"
    return "pass"


def build_graph() -> StateGraph:
    """Build and compile the workflow graph."""
    graph = StateGraph(WorkflowState)

    graph.add_node("intake_task_brief", intake_task_brief_node)
    graph.add_node("planner_agent", planner_agent_node)
    graph.add_node("analyze_hotspot_opportunities", analyze_hotspot_opportunities_node)
    graph.add_node("plan_research", plan_research_node)
    graph.add_node("run_research", run_research_node)
    graph.add_node("build_evidence_pack", build_evidence_pack_node)
    graph.add_node("resolve_article_type", resolve_article_type_node)
    graph.add_node("plan_article_angle", plan_article_angle_node)
    graph.add_node("compose_draft", compose_draft_node)
    graph.add_node("review_article_draft", review_article_draft_node)
    graph.add_node("plan_visual_assets", plan_visual_assets_node)
    graph.add_node("generate_visual_assets", generate_visual_assets_node)
    graph.add_node("review_visual_assets", review_visual_assets_node)
    graph.add_node("quality_gate", quality_gate_node)
    graph.add_node("targeted_revision", targeted_revision_node)
    graph.add_node("initialize", initialize_node)
    graph.add_node("capture_hot_topics", capture_hot_topics_node)
    graph.add_node("interpret_user_intent", interpret_user_intent_node)
    graph.add_node("infer_style_profile", infer_style_profile_node)
    graph.add_node("build_article_blueprint", build_article_blueprint_node)
    graph.add_node("plan_search_queries", plan_search_queries_node)
    graph.add_node("search_web", search_web_node)
    graph.add_node("rank_sources", rank_sources_node)
    graph.add_node("fetch_extract", fetch_extract_node)
    graph.add_node("generate_article", generate_article_node)
    graph.add_node("generate_images", generate_images_node)
    graph.add_node("push_to_draft", push_to_draft_node)
    graph.add_node("ui_feedback", ui_feedback_node)
    graph.add_node("error_handler", error_handler)

    graph.set_entry_point("intake_task_brief")
    graph.add_conditional_edges("intake_task_brief", _route_status, {"error": "error_handler", "next": "planner_agent"})
    graph.add_conditional_edges("planner_agent", _route_status, {"error": "error_handler", "next": "analyze_hotspot_opportunities"})
    graph.add_conditional_edges("analyze_hotspot_opportunities", _route_status, {"error": "error_handler", "next": "plan_research"})
    graph.add_conditional_edges("plan_research", _route_status, {"error": "error_handler", "next": "run_research"})
    graph.add_conditional_edges("run_research", _route_status, {"error": "error_handler", "next": "build_evidence_pack"})
    graph.add_conditional_edges("build_evidence_pack", _route_status, {"error": "error_handler", "next": "resolve_article_type"})
    graph.add_conditional_edges("resolve_article_type", _route_status, {"error": "error_handler", "next": "plan_article_angle"})
    graph.add_conditional_edges("plan_article_angle", _route_status, {"error": "error_handler", "next": "compose_draft"})
    graph.add_conditional_edges("compose_draft", _route_status, {"error": "error_handler", "next": "review_article_draft"})
    graph.add_conditional_edges("review_article_draft", _route_status, {"error": "error_handler", "next": "plan_visual_assets"})
    graph.add_conditional_edges("plan_visual_assets", _route_status, {"error": "error_handler", "next": "generate_visual_assets"})
    graph.add_conditional_edges("generate_visual_assets", _route_status, {"error": "error_handler", "next": "review_visual_assets"})
    graph.add_conditional_edges("review_visual_assets", _route_status, {"error": "error_handler", "next": "quality_gate"})
    graph.add_conditional_edges(
        "quality_gate",
        _route_quality_action,
        {"error": "error_handler", "pass": "push_to_draft", "revise_writing": "targeted_revision", "revise_visuals": "targeted_revision"},
    )
    graph.add_conditional_edges(
        "targeted_revision",
        _route_revision_target,
        {"error": "error_handler", "pass": "push_to_draft", "revise_writing": "compose_draft", "revise_visuals": "generate_visual_assets"},
    )
    graph.add_conditional_edges("capture_hot_topics", _route_status, {"error": "error_handler", "next": "interpret_user_intent"})
    graph.add_conditional_edges("interpret_user_intent", _route_status, {"error": "error_handler", "next": "infer_style_profile"})
    graph.add_conditional_edges("infer_style_profile", _route_status, {"error": "error_handler", "next": "build_article_blueprint"})
    graph.add_conditional_edges("build_article_blueprint", _route_status, {"error": "error_handler", "next": "plan_search_queries"})
    graph.add_conditional_edges("plan_search_queries", _route_status, {"error": "error_handler", "next": "search_web"})
    graph.add_conditional_edges("search_web", _route_status, {"error": "error_handler", "next": "rank_sources"})
    graph.add_conditional_edges("rank_sources", _route_status, {"error": "error_handler", "next": "fetch_extract"})
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
    generation_config: dict | None = None,
    hotspot_capture_config: dict | None = None,
    progress_callback: ProgressCallback | None = None,
    resume_state: dict | None = None,
    skip_auto_push: bool = False,
) -> WorkflowState:
    """Run workflow and stream progress via callback."""
    start = time.monotonic()

    if resume_state:
        initial_state = dict(resume_state)
        initial_state["status"] = "running"
        initial_state["error"] = None
        initial_state["retry_count"] = 0
        initial_state["generation_config"] = normalize_generation_config(
            generation_config if generation_config is not None else initial_state.get("generation_config")
        )
        if hotspot_capture_config is not None:
            initial_state["hotspot_capture_config"] = dict(hotspot_capture_config)
        initial_state.setdefault("task_brief", {})
        initial_state.setdefault("planning_state", {})
        initial_state.setdefault("research_state", {})
        initial_state.setdefault("writing_state", {})
        initial_state.setdefault("visual_state", {})
        initial_state.setdefault("quality_state", {})
        initial_state.setdefault("user_intent", {})
        initial_state.setdefault("style_profile", {})
        initial_state.setdefault("article_blueprint", {})
        initial_state.setdefault("search_queries", [])
        initial_state.setdefault("search_results", [])
        initial_state.setdefault("extracted_contents", [])
        initial_state.setdefault("hotspot_capture_config", {})
        initial_state.setdefault("hotspot_candidates", [])
        initial_state.setdefault("selected_hotspot", None)
        initial_state.setdefault("hotspot_capture_error", None)
        initial_state.setdefault("original_keywords", initial_state.get("keywords", keywords))
        initial_state.setdefault("article_plan", {})
        initial_state.setdefault("generated_article", {})
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
        normalized_generation_config = normalize_generation_config(generation_config)
        initial_state = {
            "task_id": task_id,
            "keywords": keywords,
            "original_keywords": keywords,
            "generation_config": normalized_generation_config,
            "hotspot_capture_config": dict(hotspot_capture_config or {}),
            "task_brief": {},
            "planning_state": {},
            "research_state": {},
            "writing_state": {},
            "visual_state": {},
            "quality_state": {},
            "user_intent": {},
            "style_profile": {},
            "article_blueprint": {},
            "search_queries": [],
            "search_results": [],
            "extracted_contents": [],
            "hotspot_candidates": [],
            "selected_hotspot": None,
            "hotspot_capture_error": None,
            "article_plan": {},
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
            generation_config=normalized_generation_config,
            hotspot_capture_enabled=bool((hotspot_capture_config or {}).get("enabled")),
            skip_auto_push=skip_auto_push,
        )

    if progress_callback:
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
                        "generation_config": final_state.get("generation_config") if final_state else None,
                        "keywords": final_state.get("keywords") if final_state else None,
                        "original_keywords": final_state.get("original_keywords") if final_state else None,
                        "hotspot_capture_config": final_state.get("hotspot_capture_config") if final_state else None,
                        "hotspot_candidates": final_state.get("hotspot_candidates") if final_state else None,
                        "selected_hotspot": final_state.get("selected_hotspot") if final_state else None,
                        "hotspot_capture_error": final_state.get("hotspot_capture_error") if final_state else None,
                        "user_intent": final_state.get("user_intent") if final_state else None,
                        "style_profile": final_state.get("style_profile") if final_state else None,
                        "article_blueprint": final_state.get("article_blueprint") if final_state else None,
                        "article_plan": final_state.get("article_plan") if final_state else None,
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
