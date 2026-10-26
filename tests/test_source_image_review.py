"""Reviewer behaviour for harvested photographs.

`review_visual_assets` is deliberately structural-only — it has no vision model and says so.
Adding harvested photos must not weaken it:

* a photo from a real file is accepted, but a failed generation is still rejected;
* a photo is **not** counted as a generated image (it was not produced by us);
* provenance and a heavy cover crop are surfaced as findings for the human who has to decide.
"""
from __future__ import annotations

import pytest

from workflow.agents.visual_reviewer import (
    has_real_image,
    is_generated_asset,
    is_source_asset,
    review_visual_assets_node,
)


def _source_asset(**overrides) -> dict:
    asset = {
        "provider": "source",
        "role": "cover",
        "path": "artifacts/source_images/t/a.jpg",
        "attribution": {
            "source_title": "示例新闻",
            "source_domain": "news.example.com",
            "source_url": "https://news.example.com/a",
            "image_url": "https://img.example.com/a.jpg",
        },
    }
    asset.update(overrides)
    return asset


def _state(assets: list[dict], *, briefs: int = 2) -> dict:
    return {
        "task_id": "t",
        "visual_state": {
            "assets": assets,
            "image_briefs": [{"role": "cover"}] * briefs,
        },
        "research_state": {"evidence_pack": {}},
    }


@pytest.mark.asyncio
async def test_harvested_photo_passes_review() -> None:
    result = await review_visual_assets_node(_state([_source_asset()], briefs=0))

    review = result["visual_state"]["visual_review"]
    assert review["passed"] is True
    assert review["source_photos"] == 1
    assert review["missing"] == []


@pytest.mark.asyncio
async def test_photo_is_not_counted_as_generated() -> None:
    result = await review_visual_assets_node(_state([_source_asset()], briefs=0))

    review = result["visual_state"]["visual_review"]
    assert review["generated"] == 0
    assert review["source_photos"] == 1


@pytest.mark.asyncio
async def test_placeholder_is_still_rejected() -> None:
    """The bug that let failed generations pass must stay fixed."""
    placeholder = {"role": "cover", "path": "generated://cover", "url": ""}

    result = await review_visual_assets_node(_state([placeholder], briefs=1))

    review = result["visual_state"]["visual_review"]
    assert review["passed"] is False
    assert "cover" in review["missing"]
    assert result["visual_state"]["visual_degraded_reason"].startswith("visual_assets_missing")


@pytest.mark.asyncio
async def test_heavy_cover_crop_is_surfaced() -> None:
    """A 40% crop might have removed the subject; only a human can tell."""
    asset = _source_asset(crop_discarded_ratio=0.4)

    result = await review_visual_assets_node(_state([asset], briefs=0))

    findings = result["visual_state"]["visual_review"]["findings"]
    crop_findings = [item for item in findings if item["type"] == "source_crop"]
    assert crop_findings
    assert "40%" in crop_findings[0]["message"]


@pytest.mark.asyncio
async def test_small_crop_is_not_flagged(monkeypatch) -> None:
    monkeypatch.setenv("COVER_CROP_DISCARD_WARN", "0.25")
    asset = _source_asset(crop_discarded_ratio=0.05)

    result = await review_visual_assets_node(_state([asset], briefs=0))

    findings = result["visual_state"]["visual_review"]["findings"]
    assert not [item for item in findings if item["type"] == "source_crop"]


@pytest.mark.asyncio
async def test_missing_attribution_is_reported() -> None:
    """The harvester refuses unattributable images, so this should not occur — reported, not assumed."""
    asset = _source_asset(attribution={})

    result = await review_visual_assets_node(_state([asset], briefs=0))

    findings = result["visual_state"]["visual_review"]["findings"]
    assert [item for item in findings if item["type"] == "source_attribution"]


@pytest.mark.asyncio
async def test_photos_do_not_create_a_false_count_finding() -> None:
    """`requested` counts model slots; extra photos are a bonus, not a shortfall.

    Mirrors what the node really produces: the generated/placeholder assets for every brief
    *plus* the harvested photos on top.
    """
    assets = [
        _source_asset(role="cover"),
        _source_asset(role="contextual_illustration", path="b.jpg"),
        # One placeholder per brief, as `generate_visual_assets_node` emits when no model runs.
        {"role": "cover", "path": "generated://cover"},
        {"role": "contextual_illustration", "path": "generated://contextual_illustration"},
    ]

    result = await review_visual_assets_node(_state(assets, briefs=2))

    review = result["visual_state"]["visual_review"]
    assert review["source_photos"] == 2
    assert review["generated"] == 0
    assert not [item for item in review["findings"] if item["type"] == "count"]


def test_helper_semantics() -> None:
    assert is_source_asset(_source_asset())
    assert not is_generated_asset(_source_asset())
    assert has_real_image(_source_asset())
    assert not has_real_image({"path": "generated://cover"})
    assert not has_real_image({})
