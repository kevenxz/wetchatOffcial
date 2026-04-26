from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from workflow.skills.outline_planner import outline_planner_node


@pytest.mark.asyncio
async def test_outline_planner_outputs_structured_outline_from_evidence() -> None:
    state = {
        "task_id": "task-outline",
        "task_brief": {"topic": "AI sales workflow"},
        "planning_state": {"article_type": {"type_id": "trend_analysis"}},
        "research_state": {
            "evidence_items": [
                {
                    "angle": "data",
                    "title": "AI sales tools face longer payback cycles",
                    "claim": "Survey data shows payback cycles for AI sales tools are lengthening.",
                    "source_type": "dataset",
                    "url": "https://example.com/data",
                }
            ],
            "evidence_pack": {
                "confirmed_facts": [{"claim": "Enterprise buyers slow rollout."}],
                "usable_data_points": [{"claim": "Payback cycles are lengthening."}],
                "risk_points": [{"claim": "Single-source data should be treated carefully."}],
                "research_gaps": ["missing_high_confidence_fact"],
            },
        },
    }

    with patch("workflow.skills.plan_article_angle.get_model_config") as mock_get_model_config:
        model_config = MagicMock()
        model_config.text.api_key = ""
        mock_get_model_config.return_value = model_config

        result = await outline_planner_node(state)
    outline_result = result["outline_result"]

    assert result["current_skill"] == "outline_planner"
    assert outline_result["outline"]
    assert outline_result["must_use_facts"]
    assert outline_result["risk_boundaries"]
    assert outline_result["image_plan_seed"]["cover_needed"] is True
    assert result["planning_state"]["outline_result"] == outline_result


def test_outline_planner_handles_string_risk_items() -> None:
    from workflow.skills.outline_planner import _normalize_outline

    outline = _normalize_outline(
        {
            "sections": [{"heading": "证据边界", "goal": "说明限制", "shape": "validation"}],
            "evidence_map": [],
        },
        {
            "evidence_pack": {
                "risk_points": ["单一来源风险"],
                "research_gaps": ["missing_data_evidence"],
            }
        },
    )

    assert outline["risk_boundaries"] == ["单一来源风险", "missing_data_evidence"]
