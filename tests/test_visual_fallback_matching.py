"""Regression pin for "the image does not match the article".

The measured defect: ``build_fallback_spec`` took **only the role**. Its subject was a single
hardcoded scene, so every article in the system received the same picture. Two unrelated real
tasks prove it — one about an Anthropic IPO and one about 微信/红果 — produced byte-identical
specs:

    subject: "A quiet workstation at night: an open laptop, a paper notebook and a cooling mug"
    section_link: "Fallback visual: no article-aware description was produced"
    degraded_reason: spec_rejected:cover:no_spec_returned,contextual_illustration:no_spec_returned

That happens whenever the structured model returns an empty ``items`` list (observed with
``text_fast`` unconfigured, routing to a reasoning model). The fallback cannot be removed — but
it must at least follow the subject matter and differ between articles.

These tests pin that. They are deliberately about *variation and relevance*, not about
photographic quality: without a vision model this code still cannot know whether a picture is
any good.
"""
from __future__ import annotations

import pytest

from workflow.utils.image_styles import TEXT_EXCLUSION_CLAUSE, forbidden_concepts_in
from workflow.utils.visual_spec import (
    VisualSpec,
    build_fallback_spec,
    resolve_prompt_settings,
)
from workflow.utils.visual_spec import assemble_image_prompt
from workflow.agents.visual_describer import resolve_specs

# The two real articles that exposed the bug.
ANTHROPIC = ("被叫“史上最大”又被叫“最荒谬”，Anthropic的IPO现在只能拆开看", "Anthropic 上市融资与估值争议")
WECHAT = ("微信亲自下场，红果劲敌“上桌”：先别把行业猜想当成事实", "短视频平台竞争与产品策略")


def _spectrum() -> list[tuple[str, str]]:
    return [
        ANTHROPIC,
        WECHAT,
        ("西藏那曲市7.0级地震", "地震救援与灾害应急"),
        ("国乒女团2比3日本女团", "体育比赛与球队表现"),
        ("多家车企下调新能源车型售价", "汽车价格战与电池成本"),
        ("监管出台平台数据合规新规", "政策监管与合规要求"),
        ("某芯片厂商发布新一代算力加速卡", "半导体与算力竞争"),
    ]


# --------------------------------------------------------------------------- #
# the defect itself
# --------------------------------------------------------------------------- #


def test_two_different_articles_no_longer_share_one_scene() -> None:
    """This is the exact bug: previously these were byte-identical."""
    first = build_fallback_spec("cover", topic=ANTHROPIC[0], section=ANTHROPIC[1])
    second = build_fallback_spec("cover", topic=WECHAT[0], section=WECHAT[1])

    assert first.subject != second.subject


def test_the_old_hardcoded_scene_is_gone() -> None:
    for topic, section in _spectrum():
        spec = build_fallback_spec("cover", topic=topic, section=section)
        assert "A quiet workstation at night" not in spec.subject
        assert "no article-aware description was produced" not in spec.section_link


def test_every_subject_area_gets_a_distinct_scene() -> None:
    subjects = {
        build_fallback_spec("cover", topic=topic, section=section).subject
        for topic, section in _spectrum()
    }
    assert len(subjects) == len(_spectrum())


@pytest.mark.parametrize(
    "topic,expected_fragment",
    [
        ("Anthropic的IPO现在只能拆开看", "financial"),
        ("西藏那曲市7.0级地震", "Rescue"),
        ("国乒女团2比3日本女团", "stadium"),
        ("某芯片厂商发布新一代算力加速卡", "server"),
        ("多家车企下调新能源车型售价", "electric car"),
    ],
)
def test_scene_follows_the_subject_matter(topic: str, expected_fragment: str) -> None:
    spec = build_fallback_spec("cover", topic=topic)
    assert expected_fragment.lower() in spec.subject.lower()


def test_unmatched_topics_still_differ_from_each_other() -> None:
    """No keyword match must not mean "same picture for everyone" again."""
    subjects = {
        build_fallback_spec("cover", topic=f"完全未知的主题编号{index}").subject
        for index in range(8)
    }
    assert len(subjects) > 1, "unmatched topics must not collapse onto a single scene"


def test_fallback_is_deterministic() -> None:
    """Same input, same output — a rerun must not silently reshuffle the artwork."""
    first = build_fallback_spec("cover", topic=ANTHROPIC[0], section=ANTHROPIC[1])
    second = build_fallback_spec("cover", topic=ANTHROPIC[0], section=ANTHROPIC[1])
    assert first.subject == second.subject


def test_cover_and_illustration_differ_in_composition() -> None:
    cover = build_fallback_spec("cover", topic=ANTHROPIC[0])
    illustration = build_fallback_spec("contextual_illustration", topic=ANTHROPIC[0])

    assert cover.composition != illustration.composition
    assert "top third" in cover.composition


# --------------------------------------------------------------------------- #
# the fallback must remain usable
# --------------------------------------------------------------------------- #


def test_every_fallback_spec_is_usable() -> None:
    """`is_usable` rejects forbidden concepts; a fallback that fails it would be discarded."""
    for role in ("cover", "contextual_illustration", "data_scene", ""):
        for topic, section in _spectrum():
            spec = build_fallback_spec(role, topic=topic, section=section)
            assert spec.is_usable(), f"{role}/{topic} -> {spec.subject}"
            assert not forbidden_concepts_in(f"{spec.subject} {spec.setting}")


def test_no_fallback_asks_for_text_or_charts() -> None:
    """The words that made the model draw posters full of garbled text.

    The single sanctioned exclusion clause is excluded from the check first: it legitimately
    names text/logos/watermarks, and `image_styles` documents why it must survive.
    """
    for topic, section in _spectrum():
        spec = build_fallback_spec("cover", topic=topic, section=section)
        prompt = assemble_image_prompt(spec=spec, style_id="editorial_photo", role="cover", max_chars=400)
        content = prompt.replace(TEXT_EXCLUSION_CLAUSE, "")
        for banned in ("chart", "diagram", "infographic", "screenshot", "watermark", "poster"):
            assert banned not in content.lower(), f"{banned!r} leaked into: {content}"


def test_fallback_prompt_still_bans_text() -> None:
    spec = build_fallback_spec("cover", topic=ANTHROPIC[0])
    _, max_chars = resolve_prompt_settings({})
    prompt = assemble_image_prompt(spec=spec, style_id="editorial_photo", role="cover", max_chars=max_chars)
    assert "No text, letters, numbers, logos, or watermarks" in prompt


def test_fallback_without_context_still_works() -> None:
    """Resumed runs and imported state may arrive with no topic at all."""
    spec = build_fallback_spec("cover")
    assert isinstance(spec, VisualSpec)
    assert spec.is_usable()


def test_section_link_is_honest_about_provenance() -> None:
    matched = build_fallback_spec("cover", topic="Anthropic的IPO", section="融资")
    unmatched = build_fallback_spec("cover", topic="完全未知的主题编号0")

    # A topic-matched scene says so; an unmatched one admits it had no article signal.
    assert "Fallback" in matched.section_link
    assert "no article-aware description" in unmatched.section_link


# --------------------------------------------------------------------------- #
# the wiring: degraded runs must pass context through
# --------------------------------------------------------------------------- #


def test_resolve_specs_uses_article_context_for_fallbacks() -> None:
    """An empty model response is exactly the observed production failure."""
    briefs = [
        {"role": "cover", "section": "融资", "purpose": "公司上市与估值争议"},
        {"role": "contextual_illustration", "section": "竞争", "purpose": "平台竞争格局"},
    ]

    specs, reasons = resolve_specs([], briefs, article_anchor="Anthropic的IPO现在只能拆开看")

    assert all(reason.endswith("no_spec_returned") for reason in reasons)
    assert len(specs) == 2
    assert "financial" in specs[0].subject.lower()


def test_empty_model_response_for_two_articles_differs() -> None:
    """End-to-end version of the pin: the two real articles must not collide."""
    briefs = [{"role": "cover", "section": "", "purpose": ""}]

    first, _ = resolve_specs([], briefs, article_anchor=ANTHROPIC[0])
    second, _ = resolve_specs([], briefs, article_anchor=WECHAT[0])

    assert first[0].subject != second[0].subject


def test_rejected_specs_also_get_context_aware_fallbacks() -> None:
    """A spec asking for a chart is rejected — its replacement must be article-aware too."""
    bad = VisualSpec(asset_index=1, role="cover", subject="A bar chart of growth", setting="", composition="")

    specs, reasons = resolve_specs([bad], [{"role": "cover", "section": "融资", "purpose": ""}], article_anchor="Anthropic的IPO")

    assert reasons and reasons[0].startswith("cover:forbidden_concept")
    assert "financial" in specs[0].subject.lower()
