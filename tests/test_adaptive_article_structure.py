"""Tests for adaptive (agent-decided) article structure.

The complaint was "文章结构还是有问题，不能固定化，应该让 agent 自己决定文章的结构". Two
separate defects produced the fixed structure:

1. **The agent's answer was discarded.** ``BlueprintOutput`` declared
   ``sections: list[dict[str, str]]``, but the planner naturally writes ``key_evidence``
   as a *list* of evidence lines and ``supporting_sources`` as a list of source ids. A
   real run failed with nine type errors, the whole adaptive blueprint was thrown away,
   and the deterministic fallback took over. The logs record exactly this::

       plan_article_angle_fallback ... error=9 validation errors for BlueprintOutput
       sections.0.key_evidence
         Input should be a valid string [input_value=['高铁约100分钟', ...], input_type=list]

2. **The fallback was one fixed skeleton**, and its headings were truncated scraped
   text plus a fixed suffix (``#法国骚乱商店餐馆被砸汽车被烧#】法国数十万人1为何在此时发生``).

These tests pin the replacement contract.
"""
from __future__ import annotations

import pytest

from workflow.nodes.plan_article_angle import (
    BlueprintOutput,
    _apply_type_override,
    _build_fallback_blueprint,
    _clamp_heading,
    _derive_article_type,
    _detect_opener,
    _heading_quality,
    _normalize_sections,
    _order_shapes,
    _requested_type_override,
    clamp_type_label,
    plan_article_angle_node,
)

# --------------------------------------------------------------------------- #
# 1. the schema must not discard a good blueprint
# --------------------------------------------------------------------------- #


def test_schema_accepts_the_payload_that_used_to_fail_with_nine_errors() -> None:
    """Exactly the shape from the production log: list-valued evidence and sources."""
    blueprint = BlueprintOutput(
        **{
            "sections": [
                {
                    "heading": "140年市政厅一夜被烧",
                    "goal": "交代发生了什么",
                    "key_evidence": ["高铁约100分钟", "国家级算力枢纽之一"],
                }
            ],
            "evidence_map": [
                {"section": "140年市政厅一夜被烧", "supporting_sources": ["source_1", "source_3"]}
            ],
            "central_question": "这场骚乱为什么在此时爆发？",
        }
    )

    # No ValidationError, and the model's own structured data survives intact.
    assert blueprint.sections[0]["key_evidence"] == ["高铁约100分钟", "国家级算力枢纽之一"]
    assert blueprint.evidence_map[0]["supporting_sources"] == ["source_1", "source_3"]


def test_missing_thesis_is_recovered_instead_of_discarding_the_blueprint() -> None:
    """`thesis` used to be the one required field, so a single omission voided everything."""
    blueprint = BlueprintOutput(**{"central_question": "它到底改变了什么？"})

    assert blueprint.thesis == "它到底改变了什么？"


def test_a_fully_empty_payload_still_parses() -> None:
    """All-or-nothing validation was the failure mode; an empty blueprint must not raise."""
    blueprint = BlueprintOutput(**{})

    assert blueprint.thesis == ""
    assert blueprint.sections == []


def test_string_fields_tolerate_a_bare_string_instead_of_a_list() -> None:
    blueprint = BlueprintOutput(**{"must_cover_points": "只看一件事", "title_candidates": "标题"})

    assert blueprint.must_cover_points == ["只看一件事"]
    assert blueprint.title_candidates == ["标题"]


# --------------------------------------------------------------------------- #
# 2. headings must be publication-worthy
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "heading",
    [
        # Real heading from data/tasks.json: a broken Weibo hashtag plus scraped text.
        "#法国骚乱商店餐馆被砸汽车被烧#】法国数十万人1为何在此时发生",
        # Real heading from data/tasks.json: an opening quote with no closing quote.
        "从“腾笼换鸟仍待验证的部分",
    ],
)
def test_scraped_headings_are_rejected(heading: str) -> None:
    assert _heading_quality(heading) <= 0


@pytest.mark.parametrize(
    "heading",
    ["为什么要等10年才动手", "140年历史的市政厅被烧毁", "楠泰尔的一声枪响"],
)
def test_readable_story_specific_headings_are_kept(heading: str) -> None:
    assert _heading_quality(heading) > 0


def test_an_unusable_heading_is_rebuilt_from_the_sections_own_evidence() -> None:
    """Never emit a placeholder when the section itself says what it is about."""
    sections = _normalize_sections(
        [
            {
                "heading": "#法国骚乱商店餐馆被砸汽车被烧#】法国数十万人1为何在此时发生",
                "key_evidence": ["法国数十万人上街抗议", "商店餐馆被砸"],
                "shape": "event",
            }
        ],
        topic="法国骚乱百年市政厅被烧毁",
    )

    heading = sections[0]["heading"]
    assert heading not in {"法国骚乱百年市政厅被烧毁相关进展", ""}
    assert "#" not in heading and "】" not in heading
    # It is derived from this story's own evidence, not a fixed template string.
    assert "法国" in heading or "抗议" in heading


def test_sections_preserve_the_planners_extra_fields() -> None:
    sections = _normalize_sections(
        [{"heading": "楠泰尔的一声枪响", "purpose": "重建事件原点", "key_evidence": ["a", "b"]}],
        topic="法国骚乱",
    )

    assert sections[0]["key_evidence"] == ["a", "b"]
    # `purpose` is the model's word for the same thing as `goal`.
    assert sections[0]["goal"] == "重建事件原点"


def test_clamp_heading_reduces_a_recovered_sentence_to_a_phrase() -> None:
    clamped = _clamp_heading("复盘政府、内政部门与地方警力的应对方式以及短期效果评估")

    assert len(clamped) <= 24
    assert "、" not in clamped or clamped.count("、") <= 1


# --------------------------------------------------------------------------- #
# 3. the fallback must not be one fixed skeleton
# --------------------------------------------------------------------------- #


def _fallback(topic: str, materials: list[dict], primary: dict | None = None) -> BlueprintOutput:
    return _build_fallback_blueprint(
        topic,
        {"article_type": "hotspot_interpretation"},
        {"usable_data_points": [], "usable_cases": [], "research_gaps": [], "quality_summary": {}},
        materials,
        {"skill_id": "", "name": ""},
        primary or {},
    )


def test_beat_order_follows_the_story_not_a_fixed_table() -> None:
    assert _order_shapes(["tension", "drivers", "evidence"], opener="event") == [
        "event",
        "evidence",
        "drivers",
        "tension",
    ]
    # With an evidence-led opener the event beat is absent, so it is not invented.
    assert _order_shapes(["drivers", "evidence"], opener="evidence") == ["evidence", "drivers"]


def test_opener_is_detected_from_the_material() -> None:
    assert _detect_opener([], {"text": "热点原文"}) == "event"
    assert _detect_opener([{"angle": "data"}], {}) == "evidence"
    assert _detect_opener([{"source_type": "official"}], {}) == "evidence"
    assert _detect_opener([{"angle": "news"}], {}) is None


def test_two_different_stories_get_different_types_spines_and_headings() -> None:
    """The core complaint: unrelated stories must not share one skeleton."""
    riot = _fallback(
        "法国骚乱百年市政厅被烧毁",
        [
            {"angle": "hotspot_source", "claim": "140年历史的市政厅在骚乱中被烧毁", "title": "法国骚乱"},
            {"angle": "analysis", "claim": "法国数十万人上街抗议养老金改革", "title": "抗议"},
            {"angle": "risk", "claim": "仍有部分地区局势不明朗", "title": "局势"},
        ],
        {"text": "法国多地爆发骚乱。"},
    )
    policy = _fallback(
        "感悟统筹区域发展之道",
        [
            {"angle": "official", "claim": "国资委印发央企十五五规划", "title": "规划"},
            {"angle": "data", "claim": "区域GDP差距缩小了两个百分点", "title": "数据"},
        ],
    )

    spans = lambda bp: [s.get("shape") for s in bp.sections]  # noqa: E731
    headings = lambda bp: [s.get("heading") for s in bp.sections]  # noqa: E731

    assert riot.article_type != policy.article_type
    assert spans(riot) != spans(policy)
    assert headings(riot) != headings(policy)


def test_fallback_always_names_a_type_and_explains_the_structure() -> None:
    """`article_type` was None on every stored task — the field was never populated."""
    blueprint = _fallback("法国骚乱", [{"angle": "news", "claim": "发生了什么"}])

    assert blueprint.article_type
    assert blueprint.structure_rationale
    assert blueprint.article_type_reason


def test_derive_article_type_responds_to_the_material() -> None:
    assert _derive_article_type([{"shape": "case"}], {}, {}) == "案例分析"
    assert _derive_article_type([{"shape": "evidence"}], {}, {"usable_data_points": ["42%"]}) == "数据解读"
    assert _derive_article_type([{"shape": "event"}], {"text": "原文"}, {}) == "热点解读"


def test_skill_specific_sections_are_not_injected_for_unrelated_topics() -> None:
    """A quantum-explainer heading must not appear on a riot story."""
    blueprint = _fallback(
        "法国骚乱百年市政厅被烧毁",
        [{"angle": "hotspot_source", "claim": "市政厅被烧毁", "title": "法国骚乱"}],
        {"text": "法国多地爆发骚乱。"},
    )

    headings = " ".join(str(s.get("heading") or "") for s in blueprint.sections)
    assert "工程指标" not in headings
    assert "量子" not in headings


# --------------------------------------------------------------------------- #
# 4. operator override
# --------------------------------------------------------------------------- #


def test_operator_override_wins_over_the_agent_choice() -> None:
    agent_choice = BlueprintOutput(**{"article_type": "深度分析"})

    overridden = _apply_type_override(agent_choice, "事件复盘")

    assert overridden.article_type == "事件复盘"
    assert overridden.article_type_reason


def test_no_override_leaves_the_agent_choice_untouched() -> None:
    agent_choice = BlueprintOutput(**{"article_type": "工具评测"})

    assert _apply_type_override(agent_choice, "").article_type == "工具评测"


def test_article_type_is_clamped_to_a_label_not_a_headline() -> None:
    """Asked to name its own type, a model sometimes answers with a whole title."""
    blueprint = BlueprintOutput(
        **{"article_type": "事件复盘：从一座百年市政厅被烧看法国骚乱的象征冲突与秩序风险"}
    )

    assert blueprint.article_type == "事件复盘"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("事件复盘", "事件复盘"),
        ("政策解读：面向政策研究者的深度拆解", "政策解读"),
        ("案例分析", "案例分析"),
    ],
)
def test_clamp_type_label_keeps_the_models_own_words(raw: str, expected: str) -> None:
    """No preset enum: the label stays whatever the agent called it, just short."""
    assert clamp_type_label(raw) == expected


def test_the_override_survives_generation_config_normalization() -> None:
    """Normalization drops unknown keys, which silently discarded the override."""
    from workflow.article_generation import normalize_generation_config

    assert (
        normalize_generation_config({"requested_article_type": "事件复盘"})["requested_article_type"]
        == "事件复盘"
    )
    # "auto" is the UI's way of saying "let the agent decide".
    assert normalize_generation_config({"requested_article_type": "auto"})["requested_article_type"] == ""


def test_override_is_read_from_either_config_key() -> None:
    """`intake` stores the config under "generation"; older states use "generation_config"."""
    for snapshot in (
        {"generation": {"requested_article_type": "人物故事"}},
        {"generation_config": {"requested_article_type": "人物故事"}},
    ):
        state = {"config_snapshot": snapshot, "task_brief": {}}
        assert _requested_type_override(state) == "人物故事"


@pytest.mark.asyncio
async def test_override_reaches_the_planner_through_real_workflow_state() -> None:
    """End-to-end: request -> normalize -> intake -> task_brief -> planner."""
    from workflow.nodes.intake import intake_task_brief_node

    state = {
        "task_id": "task-override",
        "keywords": "法国骚乱百年市政厅被烧毁",
        "mode": "manual",
        "config_snapshot": {"mode": "manual"},
        "generation_config": {"requested_article_type": "事件复盘"},
    }
    intake = await intake_task_brief_node(state)

    assert intake["task_brief"]["requested_article_type"] == "事件复盘"

    merged = {
        **state,
        **intake,
        "planning_state": {"article_type": {}, "selected_skill": {}},
        "research_state": {},
    }
    blueprint = (await plan_article_angle_node(merged))["article_blueprint"]

    assert blueprint["article_type"] == "事件复盘"


@pytest.mark.asyncio
async def test_node_reports_the_type_and_structure_rationale() -> None:
    state = {
        "task_id": "task-adaptive",
        "keywords": "法国骚乱",
        "task_brief": {"topic": "法国骚乱", "requested_article_type": "事件复盘"},
        "config_snapshot": {},
        "planning_state": {"article_type": {}, "selected_skill": {}},
        "research_state": {},
    }

    result = await plan_article_angle_node(state)
    blueprint = result["article_blueprint"]

    assert blueprint["article_type"] == "事件复盘"
    assert blueprint["structure_rationale"]
    # planning_state must expose it for the UI, not only the top-level payload.
    assert result["planning_state"]["blueprint_source"] in {"llm", "fallback"}
