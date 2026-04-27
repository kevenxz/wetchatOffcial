from __future__ import annotations

import pytest

from workflow.nodes.targeted_revision import targeted_revision_node


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


@pytest.mark.asyncio
async def test_targeted_revision_builds_visual_revision_brief_from_visual_review() -> None:
    state = {
        "quality_state": {"next_action": "revise_visuals"},
        "visual_state": {
            "visual_review": {
                "passed": False,
                "score": 60,
                "findings": [
                    {"role": "cover", "message": "主体不明确"},
                    {"role": "infographic", "message": "信息图太像海报"},
                ],
            }
        },
    }

    result = await targeted_revision_node(state)

    assert result["quality_state"]["revision_route"] == "revise_visuals"
    assert result["visual_state"]["revision_brief"]["mode"] == "targeted_revision"
    assert result["visual_state"]["revision_brief"]["guidance"] == ["主体不明确", "信息图太像海报"]
    assert result["visual_state"]["revision_brief"]["target_fields"] == ["assets"]


@pytest.mark.asyncio
async def test_targeted_revision_adds_evidence_gap_guidance_to_writing_brief() -> None:
    state = {
        "quality_state": {
            "next_action": "revise_writing",
            "evidence_gaps": ["missing_data_evidence", "missing_high_confidence_fact"],
        },
        "writing_state": {
            "review_findings": [{"type": "evidence", "message": "证据覆盖不足"}],
            "revision_guidance": ["补充证据支撑"],
        },
    }

    result = await targeted_revision_node(state)
    revision_brief = result["writing_state"]["revision_brief"]

    assert revision_brief["evidence_gaps"] == ["missing_data_evidence", "missing_high_confidence_fact"]
    assert any("missing_data_evidence" in item for item in revision_brief["guidance"])
