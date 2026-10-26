"""End-to-end checks that the new hotspot-source node integrates with the graph.

The graph is walked with stubbed LLM/network nodes, so this verifies wiring, state
merging and node ordering rather than model output.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from workflow import state as state_module
from workflow.graph import build_graph
from workflow.nodes.fetch_hotspot_source import fetch_hotspot_source_node


def _long_text(marker: str) -> str:
    return f"{marker}量子芯片的工程指标与产能变化值得持续关注。" * 30


def test_new_state_channels_are_declared() -> None:
    """LangGraph only accepts updates for declared channels."""
    annotations = state_module.WorkflowState.__annotations__
    for field in (
        "hotspot_sources",
        "hotspot_source_status",
        "hotspot_source_error",
        "hotspot_source_queries",
    ):
        assert field in annotations, f"{field} must be a declared workflow state channel"


def test_fetch_hotspot_source_sits_between_selection_and_research_planning() -> None:
    graph = build_graph()
    edges = {(edge.source, edge.target) for edge in graph.get_graph().edges}
    # The node must run after the hotspot is chosen and before queries are planned.
    assert ("analyze_hotspot_opportunities", "fetch_hotspot_source") in edges
    assert ("fetch_hotspot_source", "plan_research") in edges


@pytest.mark.asyncio
async def test_state_update_only_touches_declared_channels() -> None:
    """A node returning an undeclared key would break the graph at runtime."""
    state = {
        "task_id": "task-graph",
        "selected_topic": {"title": "量子芯片量产", "source_cluster": ["https://a.com/1"]},
        "research_state": {},
    }
    extracted = {
        "url": "https://a.com/1",
        "title": "量子芯片量产",
        "text": _long_text(""),
        "images": [],
        "source_meta": {},
    }

    with patch(
        "workflow.nodes.fetch_hotspot_source._fetch_and_extract_single",
        new=AsyncMock(return_value=extracted),
    ):
        update = await fetch_hotspot_source_node(state)

    declared = set(state_module.WorkflowState.__annotations__)
    undeclared = {key for key in update if key not in declared}
    assert undeclared == set(), f"undeclared state channels: {sorted(undeclared)}"


@pytest.mark.asyncio
async def test_hotspot_source_queries_reach_the_research_plan() -> None:
    from workflow.nodes.research_plan import plan_research_node

    state = {
        "task_id": "task-plan",
        "selected_topic": {"title": "量子芯片量产"},
        "planning_state": {"search_contract": {"query_plan": []}},
        "hotspot_source_queries": [
            {"query": '"量子芯片公司宣布量产"', "angle": "hotspot_source", "source_type": "media"}
        ],
    }

    result = await plan_research_node(state)
    queries = result["planning_state"]["search_plan"]["queries"]

    assert queries
    assert queries[0]["query"] == '"量子芯片公司宣布量产"'
    assert queries[0]["angle"] == "hotspot_source"
