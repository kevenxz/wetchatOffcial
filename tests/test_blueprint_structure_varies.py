"""Regression tests for content-driven article structure.

The bug being locked down: the deterministic blueprint path emitted the *same four*
section headings for every article, and because every structured LLM call was
truncating, that path was the only one that ever ran. Two different stories must now
produce different outlines.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from workflow.nodes.plan_article_angle import plan_article_angle_node
from workflow.nodes.research_plan import plan_research_node

# The fixed headings the old implementation always produced.
OLD_PLACEHOLDERS = {
    "先确认发生了什么",
    "变化为什么会在此时出现",
    "把变化放进真实场景",
    "仍需验证的关键变量",
}


def _state(topic: str, claims: list[tuple[str, str, str]]) -> dict:
    return {
        "task_id": "task-structure",
        "keywords": topic,
        "task_brief": {"topic": topic},
        "planning_state": {"article_type": {"type_id": "trend_analysis"}},
        "research_state": {
            "evidence_items": [
                {
                    "angle": angle,
                    "title": title,
                    "claim": claim,
                    "source_type": "news",
                    "domain": f"d{index}.com",
                    "url": f"https://d{index}.com/{index}",
                }
                for index, (angle, title, claim) in enumerate(claims)
            ],
            "evidence_pack": {},
        },
    }


async def _blueprint(state: dict) -> dict:
    """Force the deterministic path, which is what regressed in production."""
    with patch("workflow.nodes.plan_article_angle.structured_chain", return_value=(None, None)):
        result = await plan_article_angle_node(state)
    return result["planning_state"]["article_blueprint"]


@pytest.mark.asyncio
async def test_two_stories_produce_different_heading_sets() -> None:
    first = await _blueprint(
        _state(
            "机器人融资潮",
            [
                ("fact", "融资", "国内机器人公司的单轮融资规模在最近一个季度翻倍"),
                ("analysis", "交付", "头部厂商的交付周期从九个月缩短到四个月"),
            ],
        )
    )
    second = await _blueprint(
        _state(
            "光伏补贴调整",
            [
                ("fact", "补贴", "分布式光伏的补贴额度在新政策中被大幅下调"),
                ("analysis", "产能", "中小厂商的产能开始向头部企业集中"),
            ],
        )
    )

    first_headings = {section["heading"] for section in first["sections"]}
    second_headings = {section["heading"] for section in second["sections"]}

    assert first_headings, "the deterministic path must still produce narrative beats"
    assert second_headings
    assert first_headings != second_headings


@pytest.mark.asyncio
async def test_fixed_placeholder_headings_are_gone() -> None:
    blueprint = await _blueprint(
        _state(
            "机器人融资潮",
            [
                ("fact", "融资", "国内机器人公司的单轮融资规模在最近一个季度翻倍"),
                ("risk", "风险", "部分项目的估值与实际交付能力之间存在明显缺口"),
            ],
        )
    )
    headings = {section["heading"] for section in blueprint["sections"]}

    assert not (headings & OLD_PLACEHOLDERS)


@pytest.mark.asyncio
async def test_headings_never_echo_raw_source_titles_or_urls() -> None:
    blueprint = await _blueprint(
        _state(
            "机器人融资潮",
            [
                ("fact", "https://example.com/raw-title", "国内机器人公司的单轮融资规模翻倍"),
            ],
        )
    )

    for section in blueprint["sections"]:
        assert "http" not in section["heading"]
        assert "https://example.com/raw-title" not in section["heading"]


@pytest.mark.asyncio
async def test_hotspot_article_changes_the_resulting_structure() -> None:
    """The whole point of reading the hotspot article first: it shapes the outline."""
    base = _state("量子芯片量产", [("fact", "行业综述", "行业综述提到量子芯片的产能与良率问题")])

    without_source = await _blueprint(base)

    with_source = _state("量子芯片量产", [("fact", "行业综述", "行业综述提到量子芯片的产能与良率问题")])
    with_source["research_state"]["hotspot_sources"] = [
        {
            "url": "https://a.com/1",
            "title": "量子芯片公司宣布量产",
            "text": (
                "量子芯片公司宣布新一代产品正式进入量产阶段，良率提升与产能扩张成为市场关注的焦点。\n"
                "新工艺把单比特错误率降低到千分之一以下，官方称这是本轮迭代最关键的工程指标。\n"
                "公司预计明年把产能扩大三倍，但尚未披露具体客户名单与明确的交付时间表。\n"
            ),
        }
    ]
    with_source_blueprint = await _blueprint(with_source)

    plain_headings = {section["heading"] for section in without_source["sections"]}
    source_headings = {section["heading"] for section in with_source_blueprint["sections"]}

    assert source_headings
    assert source_headings != plain_headings
    # The primary source drives the opening beat, from its body rather than its title.
    assert "量子芯片公司宣布量产" not in source_headings
    assert any("量产阶段" in heading for heading in source_headings)


@pytest.mark.asyncio
async def test_source_title_never_becomes_a_heading() -> None:
    """A raw source title must not be reused as an H2.

    ``_material_claim`` falls back to the item title when no claim is present, which
    previously turned a hotspot article's title into a section heading.
    """
    state = _state("量子芯片量产", [])
    state["research_state"]["evidence_items"] = []
    state["research_state"]["hotspot_sources"] = [
        {"url": "https://a.com/1", "title": "量子芯片公司宣布量产", "text": ""}
    ]

    blueprint = await _blueprint(state)
    headings = {section["heading"] for section in blueprint["sections"]}

    assert "量子芯片公司宣布量产" not in headings


@pytest.mark.asyncio
async def test_blueprint_records_that_it_came_from_the_fallback_path() -> None:
    """A degraded run must be visible instead of silently shipping a template."""
    with patch("workflow.nodes.plan_article_angle.structured_chain", return_value=(None, None)):
        result = await plan_article_angle_node(
            _state("机器人融资潮", [("fact", "融资", "国内机器人公司的单轮融资规模翻倍")])
        )

    planning_state = result["planning_state"]
    assert planning_state["blueprint_source"] == "fallback"
    assert planning_state["blueprint_degraded_reason"] == "no_model_configured"
    assert result["planning_state"]["article_blueprint"]["blueprint_source"] == "fallback"


@pytest.mark.asyncio
async def test_plan_research_puts_source_derived_queries_first() -> None:
    state = {
        "selected_topic": {"title": "量子芯片量产"},
        "planning_state": {
            "search_contract": {
                "query_plan": [
                    {"query": "量子芯片量产 官方 公告 原文", "source_type": "official", "priority": 1},
                ]
            }
        },
        "hotspot_source_queries": [
            {
                "query": '"量子芯片公司宣布量产"',
                "angle": "hotspot_source",
                "purpose": "按原文标题定位一手报道",
                "source_type": "media",
            }
        ],
    }

    result = await plan_research_node(state)
    queries = result["planning_state"]["search_plan"]["queries"]

    assert queries[0]["query"] == '"量子芯片公司宣布量产"'
    # The generic template plan is demoted behind the source-derived queries.
    templated = next(item for item in queries if item["query"] == "量子芯片量产 官方 公告 原文")
    assert queries[0]["priority"] < templated["priority"]
