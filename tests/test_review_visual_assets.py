from __future__ import annotations

import pytest

from workflow.agents.visual_reviewer import review_visual_assets_node


@pytest.mark.asyncio
async def test_review_visual_assets_flags_infographic_when_data_evidence_is_missing() -> None:
    state = {
        "visual_state": {
            "assets": [
                {"role": "cover", "url": "https://img.example.com/cover.png", "path": ""},
                {"role": "infographic", "url": "https://img.example.com/info.png", "path": ""},
            ]
        },
        "research_state": {
            "evidence_pack": {
                "research_gaps": ["missing_data_evidence"],
                "quality_summary": {"high_confidence_items": 1},
            }
        },
    }

    result = await review_visual_assets_node(state)
    review = result["visual_state"]["visual_review"]

    assert review["passed"] is False
    assert any(item["role"] == "infographic" for item in review["findings"])
    assert any("data evidence" in item["message"] for item in review["findings"])
