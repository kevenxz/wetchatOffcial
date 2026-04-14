from __future__ import annotations

import pytest

from workflow.skills.planner_agent import planner_agent_node


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
