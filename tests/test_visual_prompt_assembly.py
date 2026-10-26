"""Contract tests for image prompt assembly and the visual description stage.

These guard the three things the user actually reported:

* pictures did not match the article — because the prompt's subject was the internal role
  token (``cover for ...`` / ``infographic for ...``) and the article only appeared as a
  wall of scraped prose;
* pictures were all text — because the prompt asked for ``infographic``, said ``clear
  diagrams first``, said ``Use these article/data signals: <raw text>`` and named
  ``text``/``watermark``/``UI screenshots``;
* the style was wrong — because a self-contradicting English blurb was appended last.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from workflow.agents.visual_describer import describe_visual_assets_node, resolve_specs
from workflow.nodes.visual_plan import plan_visual_assets_node
from workflow.utils.image_styles import TEXT_EXCLUSION_CLAUSE, build_style_clause
from workflow.utils.visual_spec import (
    HISTORICAL_TRIGGER_PHRASES,
    VisualSpec,
    assemble_image_prompt,
    build_fallback_spec,
    prompt_violations,
)

# The exact prose that reached the image model in a real run.
REAL_RAW_SIGNAL = (
    "以下文章来源于科创板日报 ，作者史正丞 专注科创板和科技创新，上海报业集团主管主办，界面财联社出品。"
    " OpenAI周四宣布，随着热门AI应用ChatGPT的最新更新，免费用户与聊天机器人的文字互动将不再受到限制。"
)

SPEC = VisualSpec(
    asset_index=1,
    role="cover",
    subject="An open laptop on a desk beside a paper notebook",
    setting="Dim room, warm lamp light from the left, blurred server rack behind",
    composition="Subject off-centre, empty space across the top third",
    section_link="Free access removes the paywall",
)


# --------------------------------------------------------------------------- #
# prompt assembly
# --------------------------------------------------------------------------- #


def test_prompt_never_uses_the_role_token_as_the_subject() -> None:
    prompt = assemble_image_prompt(spec=SPEC, style_id=None, role="cover")

    assert not prompt.lower().startswith("cover for")
    assert "cover for" not in prompt.lower()
    assert "infographic for" not in prompt.lower()


def test_prompt_never_contains_raw_scraped_prose() -> None:
    prompt = assemble_image_prompt(spec=SPEC, style_id=None, role="cover")

    for fragment in ("以下文章来源于", "主管主办", "界面财联社", "可用证据"):
        assert fragment not in prompt


def test_prompt_has_exactly_one_text_exclusion_and_no_historical_triggers() -> None:
    prompt = assemble_image_prompt(spec=SPEC, style_id=None, role="data_scene")

    assert prompt.count(TEXT_EXCLUSION_CLAUSE) == 1
    lowered = prompt.lower()
    for phrase in HISTORICAL_TRIGGER_PHRASES:
        assert phrase not in lowered, f"historical trigger phrase leaked back: {phrase}"


def test_prompt_violations_are_empty_for_a_normal_prompt() -> None:
    assert prompt_violations(assemble_image_prompt(spec=SPEC, style_id=None, role="cover")) == []


def test_allow_text_opt_in_removes_the_ban() -> None:
    """The `image_allow_text` switch must actually change the prompt, not just be stored."""
    blocked = assemble_image_prompt(spec=SPEC, style_id=None, role="cover", allow_text=False)
    allowed = assemble_image_prompt(spec=SPEC, style_id=None, role="cover", allow_text=True)

    assert TEXT_EXCLUSION_CLAUSE in blocked
    assert TEXT_EXCLUSION_CLAUSE not in allowed
    # The subject must survive either way.
    assert "laptop" in allowed
    assert prompt_violations(allowed, allow_text=True) == []


def test_allow_text_still_keeps_the_subject_under_a_tight_budget() -> None:
    allowed = assemble_image_prompt(
        spec=SPEC, style_id=None, role="cover", allow_text=True, max_chars=140
    )

    assert "laptop" in allowed
    assert TEXT_EXCLUSION_CLAUSE not in allowed


def test_prompt_violations_catch_a_regression() -> None:
    assert "missing_text_exclusion" in prompt_violations("cover for a topic, no watermark")
    assert any(
        violation.startswith("historical_trigger_phrase")
        for violation in prompt_violations(f"a scene. no fake UI screenshots. {TEXT_EXCLUSION_CLAUSE}")
    )


def test_prompt_stays_within_the_configured_length() -> None:
    prompt = assemble_image_prompt(spec=SPEC, style_id=None, role="cover", max_chars=220)

    assert len(prompt) <= 220


def test_subject_survives_even_an_extreme_budget() -> None:
    """The subject carries the content; it must never be the segment that is dropped."""
    for budget in (150, 200, 300, 400):
        prompt = assemble_image_prompt(spec=SPEC, style_id=None, role="cover", max_chars=budget)
        assert "laptop" in prompt, f"subject lost at budget {budget}"
        assert TEXT_EXCLUSION_CLAUSE in prompt


def test_style_clause_is_editorial_photography_not_diagrams() -> None:
    clause = build_style_clause(None, "data_scene").lower()

    assert "photograph" in clause
    assert "diagram" not in clause and "chart" not in clause and "infographic" not in clause


def test_fallback_spec_is_text_free_and_content_neutral() -> None:
    spec = build_fallback_spec("data_scene")
    prompt = assemble_image_prompt(spec=spec, style_id=None, role="data_scene")

    assert spec.is_usable()
    assert prompt_violations(prompt) == []
    # A fallback spec cannot know the article, so it must say so for audit purposes.
    assert "no article-aware description" in spec.section_link


# --------------------------------------------------------------------------- #
# spec resolution / rejection
# --------------------------------------------------------------------------- #


def test_forbidden_spec_requesting_a_chart_is_rejected() -> None:
    briefs = [{"role": "data_scene"}, {"role": "cover"}]
    chart_spec = VisualSpec(asset_index=1, subject="A bar chart of quarterly growth")
    good_spec = VisualSpec(asset_index=2, subject="A desk lamp over a closed notebook")

    specs, reasons = resolve_specs([chart_spec, good_spec], briefs)

    assert specs[0].subject != chart_spec.subject  # replaced by the safe fallback
    assert any(reason.startswith("data_scene:forbidden_concept") for reason in reasons)
    assert "chart" in " ".join(reasons)
    # The valid sibling is untouched.
    assert specs[1].subject == good_spec.subject


def test_missing_specs_fall_back_per_asset() -> None:
    specs, reasons = resolve_specs([], [{"role": "cover"}, {"role": "data_scene"}])

    assert len(specs) == 2
    assert all(spec.is_usable() for spec in specs)
    assert reasons == ["cover:no_spec_returned", "data_scene:no_spec_returned"]


# --------------------------------------------------------------------------- #
# the describe stage
# --------------------------------------------------------------------------- #


def _state() -> dict:
    return {
        "task_id": "task-visual",
        "keywords": "GPT-6 免费开放",
        "task_brief": {"topic": "GPT-6 免费开放"},
        "planning_state": {"article_blueprint": {"thesis": "免费开放改变了竞争格局"}},
        "writing_state": {"draft": {"title": "GPT-6 免费开放", "summary": "摘要"}},
        "config_snapshot": {"image_policy": {"style_preset": "editorial_photo", "prompt_max_chars": 400}},
        "visual_state": {
            "image_briefs": [
                {"role": "cover", "section": "封面", "purpose": "用文章核心判断吸引点击", "target_aspect_ratio": "2.35:1"},
                {
                    "role": "data_scene",
                    "section": "先确认发生了什么",
                    "purpose": f"说明变化。可用证据：{REAL_RAW_SIGNAL}",
                    "key_points": [REAL_RAW_SIGNAL],
                },
            ]
        },
    }


@pytest.mark.asyncio
async def test_describe_stage_writes_a_spec_and_a_clean_prompt_for_every_brief() -> None:
    from workflow.utils.visual_spec import VisualSpecBatch

    batch = VisualSpecBatch(
        items=[
            VisualSpec(asset_index=1, role="cover", subject="A laptop and notebook on a desk", setting="Dim room", composition="Off-centre"),
            VisualSpec(asset_index=2, role="data_scene", subject="Rows of status lights on a rack", setting="Cold blue glow", composition="Lower third"),
        ]
    )
    chain = MagicMock()
    chain.ainvoke = AsyncMock(return_value=batch)

    with patch("workflow.agents.visual_describer.structured_chain", return_value=(chain, None)):
        result = await describe_visual_assets_node(_state())

    visual_state = result["visual_state"]
    briefs = visual_state["image_briefs"]

    assert visual_state["style_id"] == "editorial_photo"
    assert len(visual_state["visual_specs"]) == 2
    for brief in briefs:
        prompt = brief["compressed_prompt"]
        assert prompt
        assert prompt_violations(prompt) == []
        # The scraped boilerplate must not survive into any prompt.
        assert "以下文章来源于" not in prompt
        assert "主管主办" not in prompt
        assert brief["visual_spec"]["section_link"] is not None


@pytest.mark.asyncio
async def test_describe_stage_degrades_safely_without_a_model() -> None:
    with patch("workflow.agents.visual_describer.structured_chain", return_value=(None, None)):
        result = await describe_visual_assets_node(_state())

    visual_state = result["visual_state"]

    assert visual_state["describe_degraded_reason"] == "no_model_configured"
    for brief in visual_state["image_briefs"]:
        assert prompt_violations(brief["compressed_prompt"]) == []
        assert "以下文章来源于" not in brief["compressed_prompt"]


@pytest.mark.asyncio
async def test_describe_stage_records_a_degraded_reason_when_the_call_fails() -> None:
    chain = MagicMock()
    chain.ainvoke = AsyncMock(side_effect=RuntimeError("provider down"))

    with patch("workflow.agents.visual_describer.structured_chain", return_value=(chain, None)):
        result = await describe_visual_assets_node(_state())

    assert result["visual_state"]["describe_degraded_reason"] == "other"


# --------------------------------------------------------------------------- #
# planning no longer builds prompts
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_plan_visual_assets_does_not_build_a_prompt_any_more() -> None:
    state = {
        "task_brief": {"topic": "GPT-6 免费开放"},
        "config_snapshot": {"image_policy": {"enabled": True, "inline_count": 1}},
        "planning_state": {"visual_plan": {"style": "", "asset_roles": ["cover"]}},
        "writing_state": {"draft": {"title": "标题"}},
        "outline_result": {
            "thesis": "免费开放改变格局",
            "image_plan_seed": {"cover_needed": True, "inline_count": 1},
            "outline": [
                {
                    "section": "先确认发生了什么",
                    "shape": "evidence",
                    "goal": f"说明变化已出现。可用证据：{REAL_RAW_SIGNAL}",
                    "image_hint": "inline",
                }
            ],
        },
    }

    result = await plan_visual_assets_node(state)
    briefs = result["visual_state"]["image_briefs"]

    assert briefs
    for brief in briefs:
        # The prompt is authored later by the describe stage.
        assert "compressed_prompt" not in brief

    inline = next(brief for brief in briefs if brief["role"] == "data_scene")
    # The evidence hint is split out of `purpose` and cleaned into `key_points`.
    assert "可用证据" not in inline["purpose"]
    assert "以下文章来源于" not in inline["purpose"]
    assert all("以下文章来源于" not in point for point in inline["key_points"])
