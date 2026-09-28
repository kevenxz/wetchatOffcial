from __future__ import annotations

import pytest

from workflow.nodes.quality_gate import quality_gate_node


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


@pytest.mark.asyncio
async def test_quality_gate_builds_unified_quality_report() -> None:
    state = {
        "writing_state": {"article_review": {"passed": False, "score": 72}},
        "visual_state": {"visual_review": {"passed": True, "score": 82, "findings": []}},
        "research_state": {
            "evidence_pack": {
                "research_gaps": ["missing_high_confidence_fact"],
                "quality_summary": {"high_confidence_items": 0},
            }
        },
        "planning_state": {"quality_thresholds": {"article": 80, "visual": 75, "evidence": 80, "hotspot": 70}},
    }

    result = await quality_gate_node(state)
    report = result["quality_state"]["quality_report"]

    assert report["article_score"] == 72
    assert report["visual_score"] == 82
    assert report["ready_to_publish"] is False
    assert "missing_high_confidence_fact" in report["blocking_reasons"]


@pytest.mark.asyncio
async def test_quality_gate_routes_low_viral_score_to_writing_revision() -> None:
    state = {
        "writing_state": {"article_review": {"passed": True, "score": 88}},
        "visual_state": {"visual_review": {"passed": True, "score": 84, "findings": []}},
        "viral_state": {
            "review": {
                "passed": False,
                "score": 69,
                "threshold": 78,
                "dimensions": {"hook": 55, "shareability": 62},
            }
        },
        "research_state": {"evidence_pack": {"research_gaps": [], "quality_summary": {}}},
        "planning_state": {"quality_thresholds": {"article": 80, "visual": 75, "viral": 78}},
        "config_snapshot": {"review_policy": {"auto_rewrite": True, "max_revision_rounds": 1}},
    }

    result = await quality_gate_node(state)

    assert result["quality_state"]["next_action"] == "revise_writing"
    assert "viral_score_below_threshold" in result["quality_state"]["quality_report"]["blocking_reasons"]
    assert result["quality_state"]["quality_report"]["viral_score"] == 69


@pytest.mark.asyncio
async def test_quality_gate_requires_review_for_fallback_draft() -> None:
    state = {
        "writing_state": {
            "article_review": {"passed": True, "score": 90},
            "draft_generation_mode": "fallback",
            "draft_quality_violations": [],
        },
        "visual_state": {"visual_review": {"passed": True, "score": 86, "findings": []}},
        "planning_state": {"quality_thresholds": {"article": 80, "visual": 75}},
    }

    result = await quality_gate_node(state)

    assert result["quality_state"]["next_action"] == "human_review"
    assert "fallback_draft_requires_review" in result["quality_state"]["quality_report"]["blocking_reasons"]
