from __future__ import annotations

import pytest

from workflow.agents.planner import planner_agent_node


@pytest.mark.asyncio
async def test_planner_agent_creates_type_search_and_visual_plan() -> None:
    state = {
        "task_id": "task-1",
        "task_brief": {
            "topic": "国产人形机器人融资潮",
            "audience_roles": ["科技投资人"],
            "article_goal": "解释趋势",
        },
        "research_state": {},
    }

    result = await planner_agent_node(state)

    assert result["planning_state"]["article_type"]["type_id"]
    assert result["planning_state"]["search_plan"]["angles"]
    assert result["planning_state"]["visual_plan"]["asset_roles"]


@pytest.mark.asyncio
async def test_planner_agent_prioritizes_angles_from_research_gaps() -> None:
    state = {
        "task_id": "task-2",
        "task_brief": {
            "topic": "机器人商业化",
            "audience_roles": ["投资人"],
            "article_goal": "解释趋势",
        },
        "research_state": {
            "evidence_pack": {
                "research_gaps": ["missing_data_evidence", "missing_high_confidence_fact"],
                "quality_summary": {
                    "source_coverage": {"community": 2},
                    "angle_coverage": {"opinion": 2},
                },
            }
        },
    }

    result = await planner_agent_node(state)
    search_plan = result["planning_state"]["search_plan"]

    assert search_plan["angles"][:2] == ["fact", "data"]
    assert "official" in search_plan["coverage_targets"]
    assert "dataset" in search_plan["coverage_targets"]
