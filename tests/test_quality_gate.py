from __future__ import annotations

import pytest

from workflow.skills.quality_gate import quality_gate_node


@pytest.mark.asyncio
async def test_quality_gate_routes_to_visual_revision_when_visual_review_fails() -> None:
    state = {
        "writing_state": {"article_review": {"passed": True, "score": 84}},
        "visual_state": {"visual_review": {"passed": False, "score": 60, "findings": [{"message": "missing asset"}]}},
        "planning_state": {"quality_thresholds": {"article": 80, "visual": 75, "evidence": 80, "hotspot": 70}},
    }

    result = await quality_gate_node(state)

    assert result["quality_state"]["next_action"] == "revise_visuals"
