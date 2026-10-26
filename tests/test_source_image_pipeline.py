"""Integration: harvested photographs flow into the article, and force human review.

Covers the wiring between three places:

* ``generate_visual_assets_node`` pulls photographs out of the reference pages and adds them to
  ``visual_state["assets"]`` alongside the generated ones;
* ``assemble_article`` crops the cover to WeChat's 2.35:1 and carries attribution;
* ``_build_publish_decision`` sends any article using a harvested photo to a human, per the
  approved policy (we cannot clear third-party rights automatically).

The no-photo path must stay exactly as it was — that is asserted too, because forcing review on
every article would be a regression in the opposite direction.
"""
from __future__ import annotations

import io

import pytest
from PIL import Image

import workflow.tools.image_generation as image_generation
import workflow.utils.source_images as source_images
from workflow.nodes.assemble_article import (
    _build_publish_decision,
    assemble_article_node,
    source_image_attributions,
)


def _photo_bytes(width: int = 1200, height: int = 800) -> bytes:
    image = Image.new("RGB", (width, height))
    rows = bytearray()
    for y in range(height):
        rows.extend(
            b
            for x in range(width)
            for b in ((x * 7 + y * 13) % 256, (x * 3 + y * 29) % 256, (x * 17 + y * 5) % 256)
        )
    image.frombytes(bytes(rows))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class _Response:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(source_images, "SOURCE_IMAGES_DIR", tmp_path / "source_images")
    yield


def _client(payload: dict[str, bytes]):
    class _Client:
        def __init__(self, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, headers=None):
            return _Response(payload[url])

    return _Client


def _state_with_sources(*, cited: bool = True) -> dict:
    page_url = "https://news.example.com/article-1"
    evidence_pack = {"citations": [{"title": "示例新闻", "url": page_url, "domain": "news.example.com"}]}
    return {
        "task_id": "task-src",
        "keywords": "Anthropic 上市",
        "visual_state": {
            "image_briefs": [
                {"role": "cover", "section": "封面", "purpose": "吸引点击", "target_aspect_ratio": "2.35:1"},
                {"role": "contextual_illustration", "section": "竞争", "purpose": "说明格局"},
            ]
        },
        "research_state": {
            "evidence_pack": evidence_pack if cited else {},
            "extracted_contents": [
                {
                    "url": page_url,
                    "title": "示例新闻：某公司上市",
                    "domain": "news.example.com",
                    "images": ["https://img.example.com/photo-1.jpg"],
                }
            ],
        },
        "generated_article": {"title": "测试文章", "content": "正文\n\n## 第一部分\n内容"},
        "config_snapshot": {"image_policy": {}},
    }


# --------------------------------------------------------------------------- #
# harvesting through the node
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_harvested_photo_becomes_the_cover_and_an_illustration(monkeypatch) -> None:
    monkeypatch.setattr(
        source_images.httpx,
        "AsyncClient",
        _client(
            {
                "https://img.example.com/photo-1.jpg": _photo_bytes(1200, 800),
                "https://img.example.com/photo-2.jpg": _photo_bytes(1100, 900),
            }
        ),
    )
    state = _state_with_sources()
    state["research_state"]["extracted_contents"][0]["images"] = [
        "https://img.example.com/photo-1.jpg",
        "https://img.example.com/photo-2.jpg",
    ]
    # No image model configured -> the generated slots would be placeholders.
    monkeypatch.setattr(
        image_generation,
        "get_model_config",
        lambda: type("C", (), {"image": type("M", (), {"enabled": False, "api_key": ""})()})(),
    )

    result = await image_generation.generate_visual_assets_node(state)

    assets = result["visual_state"]["assets"]
    sourced = [asset for asset in assets if asset.get("provider") == "source"]
    assert len(sourced) == 2
    assert sourced[0]["role"] == "cover"
    assert sourced[0]["path"].endswith(".jpg"), "the cover is cropped and re-encoded as JPEG"
    assert result["visual_state"]["source_image_count"] == 2
    assert result["visual_state"]["source_image_report"]["cover_from_source"] is True


@pytest.mark.asyncio
async def test_cover_is_cropped_to_the_wechat_ratio(monkeypatch) -> None:
    monkeypatch.setattr(
        source_images.httpx, "AsyncClient", _client({"https://img.example.com/p.jpg": _photo_bytes(1200, 800)})
    )
    state = _state_with_sources()
    state["research_state"]["extracted_contents"][0]["images"] = ["https://img.example.com/p.jpg"]
    monkeypatch.setattr(
        image_generation,
        "get_model_config",
        lambda: type("C", (), {"image": type("M", (), {"enabled": False, "api_key": ""})()})(),
    )

    result = await image_generation.generate_visual_assets_node(state)
    cover = next(a for a in result["visual_state"]["assets"] if a["role"] == "cover")

    with Image.open(cover["path"]) as cropped:
        assert abs(cropped.width / cropped.height - 2.35) < 0.02


@pytest.mark.asyncio
async def test_heavy_crop_is_flagged_for_review(monkeypatch) -> None:
    """This code cannot see what it cropped, so a big discard must be surfaced."""
    monkeypatch.setattr(
        source_images.httpx, "AsyncClient", _client({"https://img.example.com/p.jpg": _photo_bytes(1000, 1000)})
    )
    state = _state_with_sources()
    state["research_state"]["extracted_contents"][0]["images"] = ["https://img.example.com/p.jpg"]
    monkeypatch.setattr(
        image_generation,
        "get_model_config",
        lambda: type("C", (), {"image": type("M", (), {"enabled": False, "api_key": ""})()})(),
    )

    result = await image_generation.generate_visual_assets_node(state)
    cover = next(a for a in result["visual_state"]["assets"] if a["role"] == "cover")

    assert cover["crop_discarded_ratio"] > 0.25
    assert any("裁切" in note for note in cover["notes"])
    assert result["visual_state"]["source_image_report"].get("cover_crop_warning")


@pytest.mark.asyncio
async def test_cover_can_stay_generated(monkeypatch) -> None:
    """`COVER_SOURCE_PREFERRED=false` keeps the model cover and uses photos inline only."""
    monkeypatch.setenv("COVER_SOURCE_PREFERRED", "false")
    monkeypatch.setattr(
        source_images.httpx, "AsyncClient", _client({"https://img.example.com/p.jpg": _photo_bytes(1200, 800)})
    )
    state = _state_with_sources()
    state["research_state"]["extracted_contents"][0]["images"] = ["https://img.example.com/p.jpg"]
    monkeypatch.setattr(
        image_generation,
        "get_model_config",
        lambda: type("C", (), {"image": type("M", (), {"enabled": False, "api_key": ""})()})(),
    )

    result = await image_generation.generate_visual_assets_node(state)
    sourced = [a for a in result["visual_state"]["assets"] if a.get("provider") == "source"]

    assert sourced and all(a["role"] != "cover" for a in sourced)
    assert result["visual_state"]["source_image_report"]["cover_from_source"] is False


@pytest.mark.asyncio
async def test_harvest_failure_leaves_generation_intact(monkeypatch) -> None:
    """A hotlink-protected CDN must not break the task or lose the generated assets."""
    monkeypatch.setattr(source_images.httpx, "AsyncClient", _client({}))
    state = _state_with_sources()
    monkeypatch.setattr(
        image_generation,
        "get_model_config",
        lambda: type("C", (), {"image": type("M", (), {"enabled": False, "api_key": ""})()})(),
    )

    result = await image_generation.generate_visual_assets_node(state)

    assert result["visual_state"]["source_image_count"] == 0
    assert result["visual_state"]["assets"], "the placeholder assets must survive"
    assert result["generated_article"]["illustrations"] or result["generated_article"]["cover_image"]


@pytest.mark.asyncio
async def test_harvesting_disabled_changes_nothing(monkeypatch) -> None:
    monkeypatch.setenv("SOURCE_IMAGE_ENABLED", "false")
    state = _state_with_sources()
    monkeypatch.setattr(
        image_generation,
        "get_model_config",
        lambda: type("C", (), {"image": type("M", (), {"enabled": False, "api_key": ""})()})(),
    )

    result = await image_generation.generate_visual_assets_node(state)

    assert result["visual_state"]["source_image_count"] == 0
    assert all(a.get("provider") != "source" for a in result["visual_state"]["assets"])


@pytest.mark.asyncio
async def test_uncited_page_yields_no_photo_when_citations_exist(monkeypatch) -> None:
    """Harvesting is scoped to pages the article actually cites."""
    monkeypatch.setattr(
        source_images.httpx, "AsyncClient", _client({"https://img.example.com/p.jpg": _photo_bytes()})
    )
    state = _state_with_sources()
    # The only extracted page is *not* the cited one.
    state["research_state"]["extracted_contents"][0]["url"] = "https://news.example.com/other-page"
    state["research_state"]["extracted_contents"][0]["images"] = ["https://img.example.com/p.jpg"]
    monkeypatch.setattr(
        image_generation,
        "get_model_config",
        lambda: type("C", (), {"image": type("M", (), {"enabled": False, "api_key": ""})()})(),
    )

    result = await image_generation.generate_visual_assets_node(state)

    assert result["visual_state"]["source_image_count"] == 0
    assert result["visual_state"]["source_image_report"]["rejected"].get("not_cited") == 1


# --------------------------------------------------------------------------- #
# forced human review
# --------------------------------------------------------------------------- #


def _source_asset() -> dict:
    return {
        "provider": "source",
        "role": "cover",
        "path": "artifacts/source_images/t/a.jpg",
        "attribution": {
            "source_title": "示例新闻：某公司上市",
            "source_domain": "news.example.com",
            "source_url": "https://news.example.com/article-1",
            "image_url": "https://img.example.com/a.jpg",
        },
    }


def test_using_a_harvested_photo_forces_human_review() -> None:
    decision = _build_publish_decision(
        {"quality_report": {}},
        {"review_policy": {}, "publish_policy": {"auto_publish_to_draft": True}},
        False,
        source_attributions=source_image_attributions([_source_asset()]),
    )

    assert decision["human_review_required"] is True
    assert decision["ready_to_publish"] is False
    assert decision["next_step"] == "human_review"
    assert any("图片来源需人工确认" in reason for reason in decision["blocking_reasons"])
    assert decision["source_image_attributions"][0]["source_domain"] == "news.example.com"


def test_forced_review_survives_an_explicit_auto_publish_policy() -> None:
    """The operator's own policy cannot wave this through."""
    decision = _build_publish_decision(
        {"quality_report": {}},
        {"review_policy": {"require_human_review": False}, "publish_policy": {"auto_publish_to_draft": True}},
        False,
        source_attributions=source_image_attributions([_source_asset()]),
    )
    assert decision["human_review_required"] is True


def test_generated_images_alone_do_not_force_review() -> None:
    decision = _build_publish_decision(
        {"quality_report": {}},
        {"review_policy": {}, "publish_policy": {"auto_publish_to_draft": True}},
        False,
        source_attributions=source_image_attributions(
            [{"provider": "model", "role": "cover", "path": "artifacts/generated_images/a.png"}]
        ),
    )

    assert decision["human_review_required"] is False
    assert decision["next_step"] == "push_to_draft"


def test_attribution_records_skip_assets_without_provenance() -> None:
    records = source_image_attributions(
        [
            {"provider": "source", "role": "cover", "path": "a.png"},
            {"provider": "source", "role": "cover", "path": "b.png", "attribution": {"source_url": "https://x/1"}},
            {"provider": "model", "role": "cover", "path": "c.png"},
        ]
    )

    assert len(records) == 1
    assert records[0]["source_url"] == "https://x/1"


@pytest.mark.asyncio
async def test_assemble_article_forces_review_for_a_source_cover(monkeypatch) -> None:
    """End to end through the assemble node, not just the decision helper."""
    state = {
        "task_id": "t",
        "generated_article": {"title": "标题", "content": "正文\n\n## 一\n内容", "cover_image": "", "illustrations": []},
        "visual_state": {"assets": [_source_asset()]},
        "quality_state": {},
        "config_snapshot": {"review_policy": {}, "publish_policy": {"auto_publish_to_draft": True}},
    }

    result = await assemble_article_node(state)

    assert result["human_review_required"] is True
    assert result["final_article"]["publish_decision"]["human_review_required"] is True
    assert result["final_article"]["publish_decision"]["source_image_attributions"]
