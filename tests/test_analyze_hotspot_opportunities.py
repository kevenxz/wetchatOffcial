from __future__ import annotations

import pytest

from workflow.skills.analyze_hotspot_opportunities import analyze_hotspot_opportunities_node
from workflow.utils.hotspot_scoring import score_hotspot_candidate


def test_score_hotspot_candidate_prefers_relevant_and_expandable_items() -> None:
    candidate = {
        "title": "人形机器人融资潮",
        "heat": 90,
        "relevance": 85,
        "timeliness": 80,
        "evidence_density": 75,
        "expandability": 88,
        "account_fit": 82,
        "risk": 20,
    }

    score = score_hotspot_candidate(candidate)

    assert score > 75


@pytest.mark.asyncio
async def test_analyze_hotspot_opportunities_stores_ranked_candidates() -> None:
    state = {
        "task_brief": {
            "topic": "人形机器人融资潮",
            "hotspot_policy": {},
        },
        "research_state": {},
    }

    result = await analyze_hotspot_opportunities_node(state)

    assert result["research_state"]["hotspot_candidates"]
    assert result["research_state"]["selected_hotspot"]["selection_score"] >= 0
