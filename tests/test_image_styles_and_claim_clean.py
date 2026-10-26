"""Tests for image style presets and claim cleaning.

Both modules replace a string-concatenation approach that produced prompts like:

    infographic for <topic>, clean composition, mobile readable, no watermark. ...
    Use these article/data signals: 以下文章来源于科创板日报 ，作者史正丞 ...

which is why the generated pictures were text, and were unrelated to the article.
"""
from __future__ import annotations

from workflow.utils.claim_clean import (
    clean_claim,
    clean_claims,
    drop_boilerplate_sentences,
    has_boilerplate,
    strip_ellipsis_tail,
)
from workflow.utils.image_styles import (
    FORBIDDEN_SUBJECT_CONCEPTS,
    TEXT_EXCLUSION_CLAUSE,
    build_style_clause,
    forbidden_concepts_in,
    get_preset,
    list_image_styles,
    resolve_style_id,
)

# The exact string that reached the image model in a real run.
REAL_BOILERPLATE = (
    "以下文章来源于科创板日报 ，作者史正丞 专注科创板和科技创新，上海报业集团主管主办，界面财联社出品。"
    " OpenAI周四宣布，随着热门AI应用ChatGPT的最新更新，免费用户与聊天机器人的文字互动将不再受到限制。"
)


# --------------------------------------------------------------------------- #
# claim cleaning
# --------------------------------------------------------------------------- #


def test_detects_the_real_syndication_boilerplate() -> None:
    assert has_boilerplate(REAL_BOILERPLATE) is True
    assert has_boilerplate("OpenAI 宣布免费用户不再受到文字互动限制。") is False


def test_removes_boilerplate_but_keeps_the_real_claim() -> None:
    cleaned = clean_claim(REAL_BOILERPLATE)

    assert cleaned
    assert "以下文章来源于" not in cleaned
    assert "主管主办" not in cleaned
    assert "出品" not in cleaned
    assert "作者史正丞" not in cleaned
    # The actual news content survives.
    assert "ChatGPT" in cleaned


def test_drops_boilerplate_sentences_individually() -> None:
    kept = drop_boilerplate_sentences(REAL_BOILERPLATE)

    assert "科创板日报" not in kept
    assert "OpenAI周四宣布" in kept


def test_strips_urls_and_truncation_tails() -> None:
    assert "http" not in clean_claim("参考 https://example.com/a?id=1 的报道。")
    assert strip_ellipsis_tail("与此同...") == "与此同"
    assert strip_ellipsis_tail("继续推进…") == "继续推进"
    assert strip_ellipsis_tail("完整句子。") == "完整句子。"


def test_truncates_on_a_sentence_boundary() -> None:
    text = "第一句说明变化已经出现。" * 8
    cleaned = clean_claim(text, limit=40)

    assert len(cleaned) <= 41
    assert cleaned.endswith("。")


def test_returns_empty_when_only_chrome_remains() -> None:
    assert clean_claim("以下文章来源于某报，作者某某，界面财联社出品。") == ""


def test_clean_claims_dedupes_and_caps() -> None:
    cleaned = clean_claims(
        ["OpenAI 宣布免费开放。", "OpenAI 宣布免费开放。", "第二件事发生了。", "第三件事发生了。"],
        max_items=2,
    )

    assert cleaned == ["OpenAI 宣布免费开放。", "第二件事发生了。"]


# --------------------------------------------------------------------------- #
# style presets
# --------------------------------------------------------------------------- #


def test_default_style_is_editorial_photography() -> None:
    assert resolve_style_id(None, "cover") == "editorial_photo"
    assert resolve_style_id("", "contextual_illustration") == "editorial_photo"
    # Unknown ids fall back rather than leaking into the prompt.
    assert resolve_style_id("nonsense", "cover") == "editorial_photo"


def test_every_role_including_legacy_infographic_maps_to_a_photo_style() -> None:
    for role in ("cover", "contextual_illustration", "infographic", "comparison_graphic"):
        assert resolve_style_id(None, role) == "editorial_photo"


def test_style_clause_describes_a_photograph_and_never_asks_for_diagrams() -> None:
    clause = build_style_clause(None, "cover")

    assert "photograph" in clause.lower()
    # The old default said "clear diagrams first", which is a request for text.
    assert "diagram" not in clause.lower()
    assert "chart" not in clause.lower()
    assert "infographic" not in clause.lower()


def test_style_clause_folds_in_brand_colours() -> None:
    clause = build_style_clause("editorial_photo", "cover", brand_colors=["#123456"])

    assert "#123456" in clause


def test_preset_avoid_list_is_metadata_only_but_complete() -> None:
    preset = get_preset("editorial_photo")

    # `avoid` must never be pasted into a prompt, but it must list the concepts we
    # validate against.
    for concept in ("text", "logo", "watermark", "chart", "diagram", "screenshot"):
        assert concept in preset["avoid"]


def test_forbidden_concept_detection_rejects_chart_requests() -> None:
    assert forbidden_concepts_in("a bar chart showing growth") == ["chart"]
    assert "infographic" in forbidden_concepts_in("clean infographic layout")
    assert forbidden_concepts_in("a desk with a laptop at night") == []


def test_forbidden_concept_detection_does_not_match_inside_ordinary_words() -> None:
    """Regression guard: substring matching rejected nearly every valid spec.

    "photograph" contains "graph", "quiet"/"equipment" contain "ui", and "texture"
    contains "text".
    """
    assert forbidden_concepts_in("Editorial photograph of a workstation") == []
    assert forbidden_concepts_in("A quiet room with blurred equipment") == []
    assert forbidden_concepts_in("Close-up of a rough paper texture") == []
    assert forbidden_concepts_in("An entitled manager's empty chair") == []


def test_forbidden_concept_detection_still_matches_plural_and_uppercase() -> None:
    assert "chart" in forbidden_concepts_in("Charts and graphs on the wall")
    assert "ui" in forbidden_concepts_in("A UI panel glowing in the dark")
    assert "logo" in forbidden_concepts_in("logos on the wall")


def test_text_exclusion_clause_is_a_single_short_sentence() -> None:
    assert TEXT_EXCLUSION_CLAUSE.endswith(".")
    assert TEXT_EXCLUSION_CLAUSE.count(".") == 1
    assert len(TEXT_EXCLUSION_CLAUSE) < 90


def test_catalogue_exposes_every_preset_for_the_ui() -> None:
    catalogue = list_image_styles()

    assert {item["style_id"] for item in catalogue} == {"editorial_photo", "concept_illustration", "minimal_geometric"}
    assert all(item["name"] and item["description"] for item in catalogue)


def test_forbidden_concepts_cover_the_historical_trigger_words() -> None:
    # These are the phrases the old prompt appended, which invited text back.
    for concept in ("text", "watermark", "screenshot", "ui"):
        assert concept in FORBIDDEN_SUBJECT_CONCEPTS
