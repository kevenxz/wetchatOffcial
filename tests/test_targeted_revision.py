from __future__ import annotations

import pytest

from workflow.skills.targeted_revision import targeted_revision_node


@pytest.mark.asyncio
async def test_targeted_revision_builds_writing_revision_brief_from_review_feedback() -> None:
    state = {
        "quality_state": {"next_action": "revise_writing"},
        "writing_state": {
            "draft": {
                "title": "机器人融资潮进入第二阶段",
                "content": "## 趋势判断\n融资热度明显上升。",
            },
            "review_findings": [{"type": "evidence", "message": "结论支撑不足"}],
            "revision_guidance": ["补充数据依据", "收紧结论表述"],
        },
    }

    result = await targeted_revision_node(state)

    assert result["quality_state"]["revision_route"] == "revise_writing"
    assert result["writing_state"]["revision_brief"]["mode"] == "targeted_revision"
    assert result["writing_state"]["revision_brief"]["guidance"] == ["补充数据依据", "收紧结论表述"]
    assert result["writing_state"]["revision_brief"]["findings"][0]["message"] == "结论支撑不足"
