"""End-to-end graph execution with stubbed nodes.

Node-level unit tests cannot catch state-merge problems: the graph fans out twice,
and LangGraph refuses concurrent writes to the same state key unless that key
declares a reducer. These tests walk the whole compiled graph so a missing reducer
(or a broken edge) fails loudly instead of only appearing in production.
"""
from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import patch

import pytest

from workflow.graph import build_graph


def _node(name: str, output: dict):
    async def run(state: dict) -> dict:
        return output

    return run


def _running(skill: str, progress: int, **extra) -> dict:
    return {"status": "running", "current_skill": skill, "progress": progress, **extra}


def _stub_nodes() -> dict[str, object]:
    """Every node stubbed with a minimal output that keeps routing forward."""
    return {
        "capture_hot_topics_node": _node("capture_hot_topics", _running("capture_hot_topics", 12)),
        "intake_task_brief_node": _node("intake_task_brief", _running("intake_task_brief", 6)),
        "planner_agent_node": _node("planner_agent", _running("planner_agent", 12, planning_state={})),
        "analyze_hotspot_opportunities_node": _node("analyze_hotspot", _running("analyze_hotspot_opportunities", 18)),
        "plan_research_node": _node("plan_research", _running("plan_research", 24)),
        "run_research_node": _node("run_research", _running("run_research", 30)),
        "build_evidence_pack_node": _node("build_evidence_pack", _running("build_evidence_pack", 34)),
        "resolve_article_type_node": _node("resolve_article_type", _running("resolve_article_type", 38)),
        # Fan-out leg 1: both of these report the same bookkeeping keys.
        "design_viral_strategy_node": _node(
            "design_viral_strategy", _running("design_viral_strategy", 48, viral_state={"strategy": {}})
        ),
        "outline_planner_base_node": _node(
            "outline_planner", _running("outline_planner", 44, outline_result={"outline": []}, planning_state={})
        ),
        "merge_outline_strategy_node": _node(
            "merge_outline_strategy", _running("merge_outline_strategy", 52, outline_result={"outline": []})
        ),
        "compose_draft_node": _node(
            "compose_draft", _running("compose_draft", 54, writing_state={"draft": {"title": "t", "content": "c"}})
        ),
        "normalize_draft_node": _node("normalize_draft", _running("normalize_draft", 56)),
        # Fan-out leg 2: same bookkeeping keys again.
        "parallel_review_node": _node(
            "parallel_review",
            _running("parallel_review", 66, writing_state={"article_review": {"passed": True, "score": 88}}),
        ),
        "plan_visual_assets_node": _node(
            "plan_visual_assets", _running("plan_visual_assets", 68, visual_state={"image_briefs": []})
        ),
        # The visual review runs inside image_agent so this branch stays one step
        # deep and the join at quality_gate remains a true barrier.
        "image_agent_node": _node(
            "image_agent",
            _running(
                "image_agent",
                78,
                visual_state={"assets": [], "visual_review": {"passed": True}},
            ),
        ),
        "quality_gate_node": _node(
            "quality_gate",
            _running("quality_gate", 88, quality_state={"next_action": "pass"}, human_review_required=False),
        ),
        "assemble_article_node": _node(
            "assemble_article",
            _running("assemble_article", 94, final_article={"title": "t", "content": "c"}, human_review_required=False),
        ),
        "push_to_draft_node": _node("push_to_draft", _running("push_to_draft", 95, draft_info={"media_id": "m"})),
        "ui_feedback_node": _node("ui_feedback", {"status": "done", "current_skill": "ui_feedback", "progress": 100}),
    }


@pytest.mark.asyncio
async def test_full_pipeline_runs_with_stubbed_nodes() -> None:
    """The whole graph must execute both fan-outs without a state-merge conflict."""
    executed: list[str] = []

    def tracking(name: str, node):
        async def run(state: dict) -> dict:
            executed.append(name)
            return await node(state)

        return run

    stubs = {name: tracking(name, node) for name, node in _stub_nodes().items()}

    with ExitStack() as stack:
        for name, replacement in stubs.items():
            stack.enter_context(patch(f"workflow.graph.{name}", new=replacement))
        graph = build_graph()
        result = await graph.ainvoke(
            {
                "task_id": "task-e2e",
                "keywords": "端到端冒烟",
                "status": "running",
                "config_snapshot": {"publish_policy": {"auto_publish_to_draft": True, "auto_publish": False}},
            },
            {"recursion_limit": 60},
        )

    # Both fan-out legs ran, meaning the reducers handled the concurrent writes.
    assert "design_viral_strategy_node" in executed
    assert "outline_planner_base_node" in executed
    assert "parallel_review_node" in executed
    assert "plan_visual_assets_node" in executed

    # The fan-in joins ran exactly once each.
    assert executed.count("merge_outline_strategy_node") == 1
    assert executed.count("quality_gate_node") == 1

    # And the run reached the end of the pipeline.
    assert result.get("status") == "done"
    assert "ui_feedback_node" in executed


@pytest.mark.asyncio
async def test_concurrent_failure_still_reaches_the_error_handler() -> None:
    """A failing fan-out leg must not be masked by a healthy sibling leg.

    This is why ``merge_status`` ranks terminal states above ``running`` instead of
    simply taking the last write.
    """
    executed: list[str] = []
    stubs = _stub_nodes()
    # One planning leg fails while the other reports success.
    stubs["outline_planner_base_node"] = _node("outline_planner", {"status": "failed", "error": "planner blew up"})

    def tracking(name: str, node):
        async def run(state: dict) -> dict:
            executed.append(name)
            return await node(state)

        return run

    tracked = {name: tracking(name, node) for name, node in stubs.items()}

    with ExitStack() as stack:
        for name, replacement in tracked.items():
            stack.enter_context(patch(f"workflow.graph.{name}", new=replacement))
        graph = build_graph()
        result = await graph.ainvoke(
            {"task_id": "task-fail", "keywords": "失败冒烟", "status": "running"},
            {"recursion_limit": 60},
        )

    assert result.get("status") == "failed"
    assert "error_handler_node" in executed or result.get("current_skill") == "error_handler"
    # The pipeline must not continue past the failure.
    assert "compose_draft_node" not in executed


@pytest.mark.asyncio
async def test_cancellation_mid_pipeline_finishes_as_cancelled() -> None:
    """Cancellation detected at a node boundary must finalize as ``cancelled``."""
    from api import task_control

    task_control.reset_state()
    executed: list[str] = []

    def tracking(name: str, node):
        async def run(state: dict) -> dict:
            executed.append(name)
            # Cancel once the pipeline is partway through.
            if name == "merge_outline_strategy_node":
                task_control.mark_cancelled("task-cancel-e2e")
            return await node(state)

        return run

    stubs = {name: tracking(name, node) for name, node in _stub_nodes().items()}

    try:
        with ExitStack() as stack:
            for name, replacement in stubs.items():
                stack.enter_context(patch(f"workflow.graph.{name}", new=replacement))
            graph = build_graph()
            result = await graph.ainvoke(
                {"task_id": "task-cancel-e2e", "keywords": "取消冒烟", "status": "running"},
                {"recursion_limit": 60},
            )
    finally:
        task_control.reset_state()

    assert result.get("status") == "cancelled"
    # The cancelled run must not push a draft.
    assert "push_to_draft_node" not in executed
