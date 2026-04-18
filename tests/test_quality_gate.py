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


@pytest.mark.asyncio
async def test_quality_gate_surfaces_evidence_gaps_in_quality_state() -> None:
    state = {
        "writing_state": {"article_review": {"passed": False, "score": 72}},
        "visual_state": {"visual_review": {"passed": True, "score": 82, "findings": []}},
        "research_state": {
            "evidence_pack": {
                "research_gaps": ["missing_data_evidence", "missing_high_confidence_fact"],
                "quality_summary": {"high_confidence_items": 0},
            }
        },
        "planning_state": {"quality_thresholds": {"article": 80, "visual": 75, "evidence": 80, "hotspot": 70}},
    }

    result = await quality_gate_node(state)

    assert result["quality_state"]["next_action"] == "revise_writing"
    assert result["quality_state"]["evidence_gaps"] == ["missing_data_evidence", "missing_high_confidence_fact"]


@pytest.mark.asyncio
async def test_quality_gate_retains_evidence_quality_summary() -> None:
    state = {
        "writing_state": {"article_review": {"passed": True, "score": 84}},
        "visual_state": {"visual_review": {"passed": True, "score": 80, "findings": []}},
        "research_state": {
            "evidence_pack": {
                "research_gaps": [],
                "quality_summary": {
                    "high_confidence_items": 2,
                    "source_coverage": {"official": 1, "dataset": 1},
                },
            }
        },
        "planning_state": {"quality_thresholds": {"article": 80, "visual": 75, "evidence": 80, "hotspot": 70}},
    }

    result = await quality_gate_node(state)

    assert result["quality_state"]["ready_to_publish"] is True
    assert result["quality_state"]["evidence_quality_summary"]["high_confidence_items"] == 2
    assert result["quality_state"]["evidence_quality_summary"]["source_coverage"]["dataset"] == 1
