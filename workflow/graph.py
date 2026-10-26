"""Workflow graph definition and execution entry."""
from __future__ import annotations

import asyncio
import functools
import inspect
import uuid
import time
from collections.abc import Callable, Coroutine
from datetime import datetime, timezone
from typing import Any

import structlog
from langgraph.graph import END, StateGraph

from api.models import WorkflowRunStepRecord, WorkflowRunStepStatus
from api.store import create_workflow_run_step, update_workflow_run_step
from workflow.article_generation import normalize_generation_config
from workflow.config import build_config_snapshot
from workflow.agents.hotspot import capture_hot_topics_node
from workflow.agents.image import image_agent_node
from workflow.agents.outline import outline_planner_base_node
from workflow.agents.planner import planner_agent_node
from workflow.agents.virality import design_viral_strategy_node
from workflow.agents.writer import compose_draft_node
from workflow.nodes.assemble_article import assemble_article_node
from workflow.nodes.evidence_pack import build_evidence_pack_node
from workflow.nodes.error_handler import error_handler
from workflow.nodes.intake import intake_task_brief_node
from workflow.nodes.merge_outline_strategy import merge_outline_strategy_node
from workflow.nodes.normalize_draft import normalize_draft_node
from workflow.nodes.parallel_review import parallel_review_node
from workflow.nodes.quality_gate import quality_gate_node
from workflow.nodes.fetch_hotspot_source import fetch_hotspot_source_node
from workflow.nodes.research_plan import plan_research_node
from workflow.nodes.resolve_article_type import resolve_article_type_node
from workflow.nodes.run_research import run_research_node
from workflow.nodes.targeted_revision import targeted_revision_node
from workflow.nodes.topic_decision import analyze_hotspot_opportunities_node
from workflow.nodes.ui_feedback import ui_feedback_node
from workflow.nodes.visual_plan import plan_visual_assets_node
from workflow.tools.wechat_draft import push_to_draft_node
from workflow.state import WorkflowState
from workflow.utils.step_trace import sanitize_step_payload

logger = structlog.get_logger(__name__)

ProgressCallback = Callable[[str, dict], Coroutine[Any, Any, None]]


def _create_step_record(
    *,
    run_id: str,
    task_id: str,
    node_name: str,
    input_state: dict,
    started_at: datetime,
) -> WorkflowRunStepRecord:
    return create_workflow_run_step(
        WorkflowRunStepRecord(
            run_step_id=str(uuid.uuid4()),
            run_id=run_id,
            task_id=task_id,
            step_name=node_name,
            status=WorkflowRunStepStatus.running,
            payload={
                "input_state": sanitize_step_payload(input_state),
            },
            started_at=started_at,
            created_at=started_at,
        )
    )


def _complete_step_record(
    *,
    run_step_id: str,
    input_state: dict,
    output: dict,
    state_after: dict,
    started_at: datetime,
    ended_at: datetime,
    status_message: str,
) -> None:
    duration_ms = round((ended_at - started_at).total_seconds() * 1000)
    update_workflow_run_step(
        run_step_id,
        {
            "status": WorkflowRunStepStatus.failed if output.get("status") == "failed" else WorkflowRunStepStatus.succeeded,
            "payload": {
                "input_state": sanitize_step_payload(input_state),
                "output": sanitize_step_payload(output),
                "state_after": sanitize_step_payload(state_after),
                "progress": output.get("progress"),
                "duration_ms": duration_ms,
                "status_message": status_message,
            },
            "error": str(output.get("error") or "")[:2000] or None,
            "ended_at": ended_at,
            "updated_at": ended_at,
        },
    )


def _build_result_payload(final_state: dict | None) -> dict:
    """Build the task result payload persisted by API callbacks."""
    state = final_state or {}
    quality_state = state.get("quality_state") if isinstance(state.get("quality_state"), dict) else {}
    quality_report = state.get("quality_report") or quality_state.get("quality_report")
    return {
        "generation_config": state.get("generation_config"),
        "mode": state.get("mode"),
        "config_snapshot": state.get("config_snapshot"),
        "keywords": state.get("keywords"),
        "original_keywords": state.get("original_keywords"),
        "hotspot_capture_config": state.get("hotspot_capture_config"),
        "hotspot_candidates": state.get("hotspot_candidates"),
        "selected_hotspot": state.get("selected_hotspot"),
        "selected_topic": state.get("selected_topic"),
        "hotspot_capture_error": state.get("hotspot_capture_error"),
        "task_brief": state.get("task_brief"),
        "planning_state": state.get("planning_state"),
        "research_state": state.get("research_state"),
        "writing_state": state.get("writing_state"),
        "visual_state": state.get("visual_state"),
        "viral_state": state.get("viral_state"),
        "quality_state": state.get("quality_state"),
        "quality_report": quality_report,
        "human_review_required": bool(quality_report and not quality_report.get("ready_to_publish")),
        "user_intent": state.get("user_intent"),
        "style_profile": state.get("style_profile"),
        "article_blueprint": state.get("article_blueprint"),
        "article_plan": state.get("article_plan"),
        "outline_result": state.get("outline_result") or dict(state.get("planning_state") or {}).get("outline_result"),
        "generated_article": state.get("generated_article"),
        "final_article": state.get("final_article"),
        "draft_info": state.get("draft_info"),
        "publish_records": state.get("publish_records"),
        "article_theme": state.get("article_theme"),
        "completed_nodes": state.get("completed_nodes"),
    }


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
    if state.get("status") == "cancelled":
        return "cancelled"
    return "error" if state.get("status") == "failed" else "next"


def _guard_node(name: str, node: Callable) -> Callable:
    """Wrap a node with resume and cancellation checks.

    * **Resume**: a node already recorded in ``completed_nodes`` returns an empty
      update, so a retry re-runs only the failed node and its downstream nodes
      instead of the whole pipeline.
    * **Cancellation**: a node boundary is the safest place to stop a running
      workflow, and it reports ``cancelled`` rather than ``failed``.
    """

    @functools.wraps(node)
    async def guarded(state: WorkflowState) -> dict:
        task_id = str(state.get("task_id") or "")

        from api import task_control

        if task_id and task_control.is_cancelled(task_id):
            return {
                "status": "cancelled",
                "current_skill": name,
                "error": "task cancelled by operator",
            }
        if name in set(state.get("completed_nodes") or []):
            logger.info("workflow_node_skipped_resumed", task_id=task_id, node=name)
            return {}
        return await node(state)

    return guarded


def _terminal_route(state: WorkflowState) -> str | None:
    """Return the terminal route for a failed or cancelled run, else ``None``."""
    status = state.get("status")
    if status == "cancelled":
        return "cancelled"
    if status == "failed":
        return "error"
    return None


def _edge_map(**routes: str) -> dict[str, str]:
    """Build a conditional-edge map that always handles terminal states.

    ``cancelled`` lands on ``ui_feedback`` so the run finalizes with an honest
    status instead of cascading through the remaining nodes or failing.
    """
    mapping = {"error": "error_handler", "cancelled": "ui_feedback"}
    mapping.update(routes)
    return mapping


def _route_planning_fanout(state: WorkflowState) -> str | list[str]:
    """Fan out the distribution strategy and the article blueprint.

    Both only depend on the evidence pack, so they are planned concurrently and
    joined by ``merge_outline_strategy``.
    """
    terminal = _terminal_route(state)
    if terminal:
        return "error_handler" if terminal == "error" else "cancelled"
    return ["design_viral_strategy", "outline_planner"]


def _route_draft_fanout(state: WorkflowState) -> str | list[str]:
    """Fan out the review branch and the visual branch after the draft is ready.

    Both targets are one step deep by construction, so the join at ``quality_gate``
    waits for both before deciding.
    """
    terminal = _terminal_route(state)
    if terminal:
        return "error_handler" if terminal == "error" else "cancelled"
    return ["parallel_review", "image_agent"]


def _route_quality_action(state: WorkflowState) -> str:
    terminal = _terminal_route(state)
    if terminal:
        return terminal

    action = state.get("quality_state", {}).get("next_action")
    if action == "revise_writing":
        return "revise_writing"
    if action == "revise_visuals":
        return "revise_visuals"
    if action == "human_review":
        return "human_review"
    if state.get("skip_auto_push"):
        return "skip_push"
    return "pass"


def _route_revision_target(state: WorkflowState) -> str:
    terminal = _terminal_route(state)
    if terminal:
        return terminal

    action = state.get("quality_state", {}).get("revision_route")
    if action == "revise_writing":
        return "revise_writing"
    if action == "revise_visuals":
        return "revise_visuals"
    if state.get("skip_auto_push"):
        return "skip_push"
    return "pass"


def _route_after_assemble(state: WorkflowState) -> str:
    terminal = _terminal_route(state)
    if terminal:
        return terminal
    publish_policy = dict(state.get("config_snapshot", {}).get("publish_policy") or {})
    if state.get("skip_auto_push") or state.get("human_review_required"):
        return "skip_push"
    if not publish_policy.get("auto_publish_to_draft", True):
        return "skip_push"
    return "next"


def build_graph() -> StateGraph:
    """Build and compile the workflow graph."""
    graph = StateGraph(WorkflowState)

    # Every node is wrapped so a resumed run skips finished work and a cancelled
    # run stops at the next node boundary instead of cascading.
    graph.add_node("intake_task_brief", _guard_node("intake_task_brief", intake_task_brief_node))
    graph.add_node("planner_agent", _guard_node("planner_agent", planner_agent_node))
    graph.add_node("analyze_hotspot_opportunities", _guard_node("analyze_hotspot_opportunities", analyze_hotspot_opportunities_node))
    graph.add_node("fetch_hotspot_source", _guard_node("fetch_hotspot_source", fetch_hotspot_source_node))
    graph.add_node("assemble_article", _guard_node("assemble_article", assemble_article_node))
    graph.add_node("plan_research", _guard_node("plan_research", plan_research_node))
    graph.add_node("run_research", _guard_node("run_research", run_research_node))
    graph.add_node("build_evidence_pack", _guard_node("build_evidence_pack", build_evidence_pack_node))
    graph.add_node("resolve_article_type", _guard_node("resolve_article_type", resolve_article_type_node))
    graph.add_node("design_viral_strategy", _guard_node("design_viral_strategy", design_viral_strategy_node))
    graph.add_node("outline_planner", _guard_node("outline_planner", outline_planner_base_node))
    graph.add_node("merge_outline_strategy", _guard_node("merge_outline_strategy", merge_outline_strategy_node))
    graph.add_node("compose_draft", _guard_node("compose_draft", compose_draft_node))
    graph.add_node("normalize_draft", _guard_node("normalize_draft", normalize_draft_node))
    graph.add_node("parallel_review", _guard_node("parallel_review", parallel_review_node))
    graph.add_node("plan_visual_assets", _guard_node("plan_visual_assets", plan_visual_assets_node))
    graph.add_node("image_agent", _guard_node("image_agent", image_agent_node))
    graph.add_node("quality_gate", _guard_node("quality_gate", quality_gate_node))
    graph.add_node("targeted_revision", _guard_node("targeted_revision", targeted_revision_node))
    graph.add_node("capture_hot_topics", _guard_node("capture_hot_topics", capture_hot_topics_node))
    graph.add_node("push_to_draft", _guard_node("push_to_draft", push_to_draft_node))
    graph.add_node("ui_feedback", _guard_node("ui_feedback", ui_feedback_node))
    graph.add_node("error_handler", error_handler)

    graph.set_entry_point("capture_hot_topics")
    graph.add_conditional_edges("capture_hot_topics", _route_status, _edge_map(next="intake_task_brief"))
    graph.add_conditional_edges("intake_task_brief", _route_status, _edge_map(next="planner_agent"))
    graph.add_conditional_edges("planner_agent", _route_status, _edge_map(next="analyze_hotspot_opportunities"))
    graph.add_conditional_edges("analyze_hotspot_opportunities", _route_status, _edge_map(next="fetch_hotspot_source"))
    graph.add_conditional_edges("fetch_hotspot_source", _route_status, _edge_map(next="plan_research"))
    graph.add_conditional_edges("plan_research", _route_status, _edge_map(next="run_research"))
    graph.add_conditional_edges("run_research", _route_status, _edge_map(next="build_evidence_pack"))
    graph.add_conditional_edges("build_evidence_pack", _route_status, _edge_map(next="resolve_article_type"))

    # Fan-out: the distribution strategy and the article blueprint only depend on the
    # evidence pack, so they are planned concurrently and merged deterministically.
    graph.add_conditional_edges(
        "resolve_article_type",
        _route_planning_fanout,
        {
            "error_handler": "error_handler",
            "cancelled": "ui_feedback",
            "design_viral_strategy": "design_viral_strategy",
            "outline_planner": "outline_planner",
        },
    )
    graph.add_conditional_edges(
        "design_viral_strategy",
        _route_status,
        _edge_map(next="merge_outline_strategy"),
    )
    graph.add_conditional_edges(
        "outline_planner",
        _route_status,
        _edge_map(next="merge_outline_strategy"),
    )
    graph.add_conditional_edges(
        "merge_outline_strategy",
        _route_status,
        _edge_map(next="compose_draft"),
    )
    graph.add_conditional_edges("compose_draft", _route_status, _edge_map(next="normalize_draft"))

    # Fan-out: `plan_visual_assets` is deterministic and cheap, so it runs on the
    # trunk first. Both resulting branches are then exactly ONE step deep, which is
    # what makes the join at `quality_gate` a true barrier. A longer branch would
    # let the join fire early with incomplete visual state and then fire again.
    graph.add_conditional_edges(
        "normalize_draft",
        _route_status,
        _edge_map(next="plan_visual_assets"),
    )
    graph.add_conditional_edges(
        "plan_visual_assets",
        _route_draft_fanout,
        {
            "error_handler": "error_handler",
            "cancelled": "ui_feedback",
            "parallel_review": "parallel_review",
            "image_agent": "image_agent",
        },
    )

    # Fan-in: the quality gate waits for both the reviews and the visual assets.
    graph.add_conditional_edges(
        "parallel_review",
        _route_status,
        _edge_map(next="quality_gate"),
    )
    graph.add_conditional_edges(
        "image_agent",
        _route_status,
        _edge_map(next="quality_gate"),
    )
    graph.add_conditional_edges(
        "quality_gate",
        _route_quality_action,
        {
            **_edge_map(),
            "pass": "assemble_article",
            "skip_push": "assemble_article",
            "human_review": "assemble_article",
            "revise_writing": "targeted_revision",
            "revise_visuals": "targeted_revision",
        },
    )
    graph.add_conditional_edges(
        "targeted_revision",
        _route_revision_target,
        {
            **_edge_map(),
            "pass": "assemble_article",
            "skip_push": "ui_feedback",
            "revise_writing": "compose_draft",
            "revise_visuals": "image_agent",
        },
    )
    graph.add_conditional_edges(
        "assemble_article",
        _route_after_assemble,
        {
            **_edge_map(),
            "next": "push_to_draft",
            "skip_push": "ui_feedback",
        },
    )
    graph.add_conditional_edges("push_to_draft", _route_status, _edge_map(next="ui_feedback"))
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
    publish_targets: list[dict] | None = None,
    article_theme: str | None = None,
) -> WorkflowState:
    """Run workflow and stream progress via callback."""
    start = time.monotonic()
    run_id = str(uuid.uuid4())

    # Bind the correlation ids for this run so every line the workflow emits carries them.
    # A background task has its own context, so these do not leak into other tasks or into
    # the request that started it. `run_id` distinguishes retries of the same task.
    structlog.contextvars.bind_contextvars(task_id=task_id, run_id=run_id)

    if resume_state:
        initial_state = dict(resume_state)
        initial_state["status"] = "running"
        initial_state["error"] = None
        initial_state["retry_count"] = 0
        raw_generation_config = generation_config if generation_config is not None else initial_state.get("generation_config")
        initial_state["generation_config"] = normalize_generation_config(raw_generation_config)
        if hotspot_capture_config is not None:
            initial_state["hotspot_capture_config"] = dict(hotspot_capture_config)
        if publish_targets is not None:
            initial_state["publish_targets"] = list(publish_targets)
        if article_theme is not None:
            initial_state["article_theme"] = article_theme
        initial_state.setdefault("publish_targets", [])
        initial_state.setdefault("publish_records", [])
        initial_state.setdefault("article_theme", None)
        initial_state.setdefault("task_brief", {})
        initial_state.setdefault("planning_state", {})
        initial_state.setdefault("research_state", {})
        initial_state.setdefault("writing_state", {})
        initial_state.setdefault("visual_state", {})
        initial_state.setdefault("viral_state", {})
        initial_state.setdefault("quality_state", {})
        initial_state.setdefault("user_intent", {})
        initial_state.setdefault("style_profile", {})
        initial_state.setdefault("article_blueprint", {})
        initial_state.setdefault("search_queries", [])
        initial_state.setdefault("search_results", [])
        initial_state.setdefault("extracted_contents", [])
        initial_state.setdefault("hotspot_capture_config", {})
        initial_state["config_snapshot"] = build_config_snapshot(
            generation_config=raw_generation_config,
            hotspot_capture_config=initial_state.get("hotspot_capture_config"),
            skip_auto_push=skip_auto_push,
        )
        initial_state["mode"] = initial_state["config_snapshot"]["mode"]
        initial_state.setdefault("hotspot_candidates", [])
        initial_state.setdefault("selected_hotspot", None)
        initial_state.setdefault("selected_topic", None)
        initial_state.setdefault("hotspot_capture_error", None)
        initial_state.setdefault("original_keywords", initial_state.get("keywords", keywords))
        initial_state.setdefault("article_plan", {})
        initial_state.setdefault("outline_result", {})
        initial_state.setdefault("generated_article", {})
        initial_state.setdefault("final_article", {})
        initial_state.setdefault("revision_count", 0)
        if "skip_auto_push" not in initial_state:
            initial_state["skip_auto_push"] = skip_auto_push
        logger.info(
            "workflow_resume",
            task_id=task_id,
            skill="workflow",
            status="running",
            resume_from=initial_state.get("current_skill", "unknown"),
            run_id=run_id,
        )
    else:
        normalized_generation_config = normalize_generation_config(generation_config)
        config_snapshot = build_config_snapshot(
            generation_config=generation_config,
            hotspot_capture_config=hotspot_capture_config or {},
            skip_auto_push=skip_auto_push,
        )
        initial_state = {
            "task_id": task_id,
            "mode": config_snapshot["mode"],
            "keywords": keywords,
            "original_keywords": keywords,
            "generation_config": normalized_generation_config,
            "config_snapshot": config_snapshot,
            "hotspot_capture_config": dict(hotspot_capture_config or {}),
            "task_brief": {},
            "planning_state": {},
            "research_state": {},
            "writing_state": {},
            "visual_state": {},
            "viral_state": {},
            "quality_state": {},
            "user_intent": {},
            "style_profile": {},
            "article_blueprint": {},
            "search_queries": [],
            "search_results": [],
            "extracted_contents": [],
            "hotspot_candidates": [],
            "selected_hotspot": None,
            "selected_topic": None,
            "hotspot_capture_error": None,
            "article_plan": {},
            "outline_result": {},
            "generated_article": {},
            "final_article": {},
            "draft_info": None,
            "publish_targets": list(publish_targets or []),
            "publish_records": [],
            "article_theme": article_theme,
            "retry_count": 0,
            "revision_count": 0,
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
            run_id=run_id,
        )

    if progress_callback:
        await progress_callback(
            task_id,
                {
                    "task_id": task_id,
                    "run_id": run_id,
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
                input_state = dict(current_state)
                step_started_at = datetime.now(tz=timezone.utc)
                step = None
                try:
                    step = _create_step_record(
                        run_id=run_id,
                        task_id=task_id,
                        node_name=node_name,
                        input_state=input_state,
                        started_at=step_started_at,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "workflow_step_trace_create_failed",
                        task_id=task_id,
                        node=node_name,
                        error=str(exc),
                        exc_info=True,
                    )
                current_state.update(output)
                final_state = current_state
                # Record progress so a retry can resume from the failed node instead
                # of re-running the whole pipeline.
                if node_name != "error_handler" and output and output.get("status") != "cancelled":
                    completed = list(current_state.get("completed_nodes") or [])
                    if node_name not in completed:
                        completed.append(node_name)
                    current_state["completed_nodes"] = completed
                step_ended_at = datetime.now(tz=timezone.utc)
                status_message = f"node [{node_name}] done"
                if step is not None:
                    try:
                        _complete_step_record(
                            run_step_id=step.run_step_id,
                            input_state=input_state,
                            output=dict(output),
                            state_after=dict(current_state),
                            started_at=step_started_at,
                            ended_at=step_ended_at,
                            status_message=status_message,
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "workflow_step_trace_update_failed",
                            task_id=task_id,
                            node=node_name,
                            error=str(exc),
                            exc_info=True,
                        )
                if progress_callback:
                    await progress_callback(
                        task_id,
                        {
                            "task_id": task_id,
                            "run_id": run_id,
                            "run_step_id": step.run_step_id if step is not None else None,
                            "status": output.get("status", "running"),
                            "current_skill": output.get("current_skill", node_name),
                            "progress": output.get("progress", 0),
                            "message": status_message,
                            "result": None,
                        },
                    )

        duration_ms = round((time.monotonic() - start) * 1000)
        raw_status = str((final_state or {}).get("status") or "")
        if raw_status == "failed":
            final_status = "failed"
            final_message = "workflow failed"
        elif raw_status == "cancelled":
            final_status = "cancelled"
            final_message = "workflow cancelled by operator"
        else:
            final_status = "done"
            final_message = "workflow done"
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
                    "run_id": run_id,
                    "status": final_status,
                    "current_skill": "",
                    "progress": 100
                    if final_status == "done"
                    else int((final_state or {}).get("progress", 0) or 0),
                    "message": final_message,
                    "result": _build_result_payload(final_state),
                },
            )
    except asyncio.CancelledError:
        duration_ms = round((time.monotonic() - start) * 1000)
        logger.info(
            "workflow_cancelled",
            task_id=task_id,
            skill="workflow",
            status="cancelled",
            duration_ms=duration_ms,
        )
        if progress_callback:
            await progress_callback(
                task_id,
                {
                    "task_id": task_id,
                    "run_id": run_id,
                    "status": "cancelled",
                    "current_skill": "",
                    "progress": 0,
                    "message": "workflow cancelled by operator",
                    "result": _build_result_payload(current_state),
                },
            )
        current_state["status"] = "cancelled"
        return current_state
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
                    "run_id": run_id,
                    "status": "failed",
                    "current_skill": "",
                    "progress": 0,
                    "message": f"workflow failed: {exc}",
                    "result": None,
                },
            )
    finally:
        # Release the correlation ids on every exit path (including the early return in
        # the CancelledError branch) so a retry or the next task starts with a clean slate.
        structlog.contextvars.unbind_contextvars("task_id", "run_id")

    return final_state or initial_state
