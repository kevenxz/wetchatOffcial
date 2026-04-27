from __future__ import annotations

import pytest

from workflow.nodes.research_plan import plan_research_node


@pytest.mark.asyncio
async def test_plan_research_creates_queries_for_all_research_angles() -> None:
    state = {
        "task_brief": {"topic": "AI 智能体创业"},
        "planning_state": {"search_plan": {"angles": ["fact", "news", "opinion", "case", "data"]}},
    }

    result = await plan_research_node(state)
    queries = result["planning_state"]["search_plan"]["queries"]

    assert len(queries) == 5
    assert {item["angle"] for item in queries} == {"fact", "news", "opinion", "case", "data"}
