"""Tests for the visual asset review.

The review deliberately cannot see the image — there is no vision model. These tests
pin down what it *does* guarantee, and the two ways the old implementation lied:

1. it reported a hard-coded ``score: 82`` and ``passed: true`` regardless of the picture;
2. a failed generation degrades to a ``generated://<role>`` placeholder whose truthy
   ``path`` made the old presence check treat it as a valid asset, so failures passed.
"""
from __future__ import annotations

import pytest

from workflow.agents.visual_reviewer import (
    CHECK_NOTE,
    is_generated_asset,
    review_visual_assets_node,
)


def _state(assets: list[dict], gaps: list[str] | None = None, briefs: int = 0) -> dict:
    return {
        "visual_state": {
            "assets": assets,
            "image_briefs": [{"role": f"r{index}"} for index in range(briefs)],
        },
        "research_state": {
            "evidence_pack": {
                "research_gaps": gaps or [],
                "quality_summary": {"high_confidence_items": 1},
            }
        },
    }


@pytest.mark.asyncio
async def test_flags_data_scene_when_data_evidence_is_missing() -> None:
    state = _state(
        [
            {"role": "cover", "url": "https://img.example.com/cover.png", "path": ""},
            {"role": "data_scene", "url": "https://img.example.com/data.png", "path": ""},
        ],
        gaps=["missing_data_evidence"],
    )

    review = (await review_visual_assets_node(state))["visual_state"]["visual_review"]

    assert review["passed"] is False
    # Assert on the stable machine-readable type, not the localised message.
    assert any(item.get("type") == "evidence" and item.get("role") == "data_scene" for item in review["findings"])


@pytest.mark.asyncio
async def test_still_recognises_the_legacy_infographic_role() -> None:
    state = _state(
        [{"role": "infographic", "url": "https://img.example.com/info.png", "path": ""}],
        gaps=["missing_data_evidence"],
    )

    review = (await review_visual_assets_node(state))["visual_state"]["visual_review"]

    assert any(item.get("role") == "infographic" for item in review["findings"])


@pytest.mark.asyncio
async def test_reports_that_it_only_did_a_structural_check() -> None:
    review = (
        await review_visual_assets_node(
            _state([{"role": "cover", "url": "https://img.example.com/cover.png", "path": ""}])
        )
    )["visual_state"]["visual_review"]

    assert review["check"] == "structural_only"
    assert review["note"] == CHECK_NOTE
    # The note must tell the operator it cannot judge content, and that they must look.
    assert "没有视觉模型" in review["note"]
    assert "人工确认" in review["note"]
    # The old implementation asserted a score it had no basis for.
    assert "score" not in review


@pytest.mark.asyncio
async def test_placeholder_asset_counts_as_missing() -> None:
    """A failed generation must not pass review.

    ``generated://infographic`` has a truthy ``path`` and used to satisfy the presence
    check, which is how broken images shipped as "reviewed".
    """
    review = (
        await review_visual_assets_node(
            # Two briefs planned, only one real asset produced.
            _state(
                [
                    {"role": "cover", "url": "https://img.example.com/cover.png", "path": ""},
                    {"role": "data_scene", "path": "generated://data_scene", "url": ""},
                ],
                briefs=2,
            )
        )
    )["visual_state"]["visual_review"]

    assert review["passed"] is False
    assert review["missing"] == ["data_scene"]
    assert review["generated"] == 1
    assert any(item.get("type") == "placeholder" for item in review["findings"])


@pytest.mark.asyncio
async def test_marks_the_run_degraded_when_assets_are_missing() -> None:
    state = _state([{"role": "cover", "path": "generated://cover", "url": ""}], briefs=1)

    visual_state = (await review_visual_assets_node(state))["visual_state"]

    assert visual_state["visual_degraded_reason"] == "visual_assets_missing:cover"


@pytest.mark.asyncio
async def test_reports_a_shortfall_in_generated_count() -> None:
    review = (
        await review_visual_assets_node(
            _state([{"role": "cover", "url": "https://img.example.com/c.png", "path": ""}], briefs=3)
        )
    )["visual_state"]["visual_review"]

    assert any(item.get("type") == "count" for item in review["findings"])
    assert review["requested"] == 3


@pytest.mark.asyncio
async def test_clean_run_passes_without_a_score() -> None:
    review = (
        await review_visual_assets_node(
            _state(
                [{"role": "cover", "url": "https://img.example.com/c.png", "path": ""}],
                briefs=1,
            )
        )
    )["visual_state"]["visual_review"]

    assert review["passed"] is True
    assert review["findings"] == []
    assert review["missing"] == []


def test_is_generated_asset_distinguishes_placeholders() -> None:
    assert is_generated_asset({"url": "https://x/y.png", "path": ""}) is True
    assert is_generated_asset({"url": "", "path": "/artifacts/generated_images/a.png"}) is True
    assert is_generated_asset({"url": "", "path": "generated://cover"}) is False
    assert is_generated_asset({"url": "", "path": ""}) is False
    assert is_generated_asset({"url": "generated://cover", "path": ""}) is False
