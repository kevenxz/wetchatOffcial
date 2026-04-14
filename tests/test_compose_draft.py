from __future__ import annotations

import pytest

from workflow.skills.compose_draft import compose_draft_node


@pytest.mark.asyncio
async def test_compose_draft_generates_article_from_blueprint_and_evidence() -> None:
    state = {
        "task_brief": {"topic": "AI 智能体创业"},
        "planning_state": {
            "article_type": {"type_id": "trend_analysis", "title_style": "insight_first"},
            "article_blueprint": {"sections": [{"heading": "趋势判断", "goal": "解释驱动因素"}]},
        },
        "research_state": {"evidence_pack": {"confirmed_facts": [{"claim": "融资升温"}]}},
    }

    result = await compose_draft_node(state)

    assert result["writing_state"]["draft"]["title"]
    assert "趋势判断" in result["writing_state"]["draft"]["content"]
