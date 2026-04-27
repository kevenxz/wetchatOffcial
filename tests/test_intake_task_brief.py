from __future__ import annotations

import pytest

from workflow.nodes.intake import intake_task_brief_node


@pytest.mark.asyncio
async def test_intake_task_brief_normalizes_generation_inputs() -> None:
    state = {
        "task_id": "task-1",
        "keywords": "机器人创业",
        "original_keywords": "机器人创业",
        "generation_config": {"audience_roles": ["科技创业者"]},
    }

    result = await intake_task_brief_node(state)

    assert result["task_brief"]["topic"] == "机器人创业"
    assert result["task_brief"]["audience_roles"] == ["科技创业者"]
    assert result["task_brief"]["runtime_profile"] == "quality_first"
    assert result["task_brief"]["image_policy"] == {}
    assert result["current_skill"] == "intake_task_brief"
