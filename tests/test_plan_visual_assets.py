from __future__ import annotations

import pytest

from workflow.skills.plan_visual_assets import plan_visual_assets_node


@pytest.mark.asyncio
async def test_plan_visual_assets_creates_role_aware_image_briefs() -> None:
    state = {
        "task_brief": {"topic": "AI 智能体创业"},
        "planning_state": {"visual_plan": {"asset_roles": ["cover", "infographic"]}},
        "writing_state": {"draft": {"title": "AI 智能体创业进入第二阶段", "content": "## 趋势判断\n内容"}},
    }

    result = await plan_visual_assets_node(state)
    briefs = result["visual_state"]["image_briefs"]

    assert briefs[0]["role"] == "cover"
    assert briefs[1]["target_aspect_ratio"]
