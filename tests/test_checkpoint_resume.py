"""Tests for resuming a workflow from the failed node."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from workflow.graph import _compiled_graph, build_graph


@pytest.mark.asyncio
async def test_completed_nodes_are_skipped_on_resume() -> None:
    """A resumed run must not re-execute nodes that already succeeded."""
    executed: list[str] = []

    def make_node(name: str, output: dict):
        async def node(state: dict) -> dict:
            executed.append(name)
            return output

        return node

    state = {
        "task_id": "task-resume",
        "keywords": "机器人商业化",
        "status": "running",
        # These two already finished before the failure.
        "completed_nodes": ["capture_hot_topics", "intake_task_brief"],
    }

    # The stubbed planner fails so the graph terminates at error_handler instead of
    # walking the whole pipeline.
    with patch(
        "workflow.graph.capture_hot_topics_node",
        new=make_node("capture_hot_topics", {"status": "running"}),
    ):
        with patch(
            "workflow.graph.intake_task_brief_node",
            new=make_node("intake_task_brief", {"status": "running"}),
        ):
            with patch(
                "workflow.graph.planner_agent_node",
                new=make_node("planner_agent", {"status": "failed", "error": "boom"}),
            ):
                graph = build_graph()
                await graph.ainvoke(state, {"recursion_limit": 25})

    assert "capture_hot_topics" not in executed, "a completed node was re-executed"
    assert "intake_task_brief" not in executed, "a completed node was re-executed"
    assert "planner_agent" in executed


@pytest.mark.asyncio
async def test_planning_fanout_runs_both_branches() -> None:
    """The real graph must execute both concurrent planning legs.

    This guards a deliberately subtle LangGraph behaviour: fan-out is expressed by
    returning a *list* of node names from the conditional-edge path function. If a
    future LangGraph version stopped honouring that, the pipeline would silently
    run only one leg and produce an incomplete outline.
    """
    executed: list[str] = []

    def passthrough(name: str, output: dict):
        async def node(state: dict) -> dict:
            executed.append(name)
            return output

        return node

    running = {"status": "running"}
    branches = {
        "workflow.graph.capture_hot_topics_node": passthrough("capture_hot_topics", running),
        "workflow.graph.intake_task_brief_node": passthrough("intake_task_brief", running),
        "workflow.graph.planner_agent_node": passthrough("planner_agent", running),
        "workflow.graph.analyze_hotspot_opportunities_node": passthrough("analyze_hotspot", running),
        "workflow.graph.plan_research_node": passthrough("plan_research", running),
        "workflow.graph.run_research_node": passthrough("run_research", running),
        "workflow.graph.build_evidence_pack_node": passthrough("build_evidence_pack", running),
        "workflow.graph.resolve_article_type_node": passthrough("resolve_article_type", running),
        # The two fan-out legs under test.
        "workflow.graph.design_viral_strategy_node": passthrough("design_viral_strategy", running),
        "workflow.graph.outline_planner_base_node": passthrough("outline_planner", running),
        # Stop the run right after the join so the rest of the pipeline is not walked.
        "workflow.graph.merge_outline_strategy_node": passthrough(
            "merge_outline_strategy", {"status": "failed", "error": "stop after join"}
        ),
    }

    from contextlib import ExitStack

    with ExitStack() as stack:
        for target, replacement in branches.items():
            stack.enter_context(patch(target, new=replacement))
        graph = build_graph()
        await graph.ainvoke({"task_id": "task-fanout", "keywords": "x", "status": "running"}, {"recursion_limit": 25})

    assert "design_viral_strategy" in executed, "the viral-strategy leg did not run"
    assert "outline_planner" in executed, "the outline leg did not run"
    assert "merge_outline_strategy" in executed, "the fan-in join did not run"


@pytest.mark.asyncio
async def test_graph_compiles_with_guards() -> None:
    graph = build_graph()
    nodes = set(graph.get_graph().nodes)
    for expected in ("normalize_draft", "parallel_review", "merge_outline_strategy", "ui_feedback", "error_handler"):
        assert expected in nodes


@pytest.mark.asyncio
async def test_cancelled_task_short_circuits_at_the_node_boundary() -> None:
    from api import task_control

    task_control.reset_state()
    task_control.mark_cancelled("task-cancelled")

    planner = AsyncMock(return_value={"status": "running"})
    with patch("workflow.graph.planner_agent_node", new=planner):
        graph = build_graph()
        result = await graph.ainvoke(
            {
                "task_id": "task-cancelled",
                "keywords": "x",
                "status": "running",
                "completed_nodes": ["capture_hot_topics", "intake_task_brief"],
            },
            {"recursion_limit": 5},
        )

    # The guarded entry node reports cancellation instead of running the pipeline.
    assert result.get("status") == "cancelled"
    planner.assert_not_awaited()
    task_control.reset_state()


def test_compiled_graph_module_level_instance_exists() -> None:
    assert _compiled_graph is not None
