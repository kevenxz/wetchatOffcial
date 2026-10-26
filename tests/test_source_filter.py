"""Tests for deterministic source filtering.

Before this module, everything the search stage returned reached the evidence pack:
the only gate was "extracted text is at least 50 characters" plus exact-URL de-dupe.
"""
from __future__ import annotations

from workflow.utils.source_filter import (
    filter_sources,
    relevance_score,
    similarity,
    topic_tokens,
)


def _body(marker: str = "", repeats: int = 30) -> str:
    """Topic-relevant body comfortably above the length and sentence floors."""
    return f"{marker}量子计算芯片的工程指标出现变化值得关注。" * repeats


def _off_topic_body() -> str:
    """Long enough to clear the quality gate, so it fails on relevance instead."""
    return "今天天气晴朗，适合出门散步和晒太阳。" * 40


def _item(url: str, *, domain: str, title: str, text: str, source_type: str = "news") -> dict:
    return {"url": url, "domain": domain, "title": title, "text": text, "source_type": source_type}


def test_on_topic_source_survives() -> None:
    result = filter_sources(
        "量子计算芯片",
        [_item("https://a.com/1", domain="a.com", title="量子计算芯片进展", text=_body())],
        min_survivors=1,
    )

    assert result.kept_count == 1
    assert result.dropped == []
    assert result.kept[0]["filtered"] is True
    assert result.kept[0]["relevance"] > 0.5


def test_off_topic_source_is_dropped() -> None:
    result = filter_sources(
        "量子计算芯片",
        [_item("https://b.com/1", domain="b.com", title="今日天气预报", text=_off_topic_body())],
        min_survivors=1,
    )

    assert result.kept == []
    assert [item["reason"] for item in result.dropped] == ["off_topic"]


def test_short_source_is_dropped() -> None:
    result = filter_sources(
        "量子计算芯片",
        [_item("https://c.com/1", domain="c.com", title="量子计算芯片", text="量子计算芯片太短。")],
        min_survivors=1,
    )

    assert result.kept == []
    assert result.dropped[0]["reason"] == "too_short"


def test_official_source_may_be_brief() -> None:
    """An official announcement can be terse but is still authoritative evidence."""
    brief = "量子计算芯片新版本现已发布。" * 12  # ~150 chars: under the general floor
    result = filter_sources(
        "量子计算芯片",
        [_item("https://d.com/1", domain="d.com", title="官方公告", text=brief, source_type="official")],
        min_survivors=1,
    )

    assert result.kept_count == 1


def test_navigation_capture_is_rejected_as_not_prose() -> None:
    # Long enough, on topic, but a single run-on string with no sentences.
    text = "量子计算芯片" * 100
    result = filter_sources(
        "量子计算芯片",
        [_item("https://e.com/1", domain="e.com", title="量子计算芯片", text=text)],
        min_survivors=1,
    )

    assert result.kept == []
    assert result.dropped[0]["reason"] == "not_prose"


def test_near_duplicate_syndication_is_dropped() -> None:
    body = _body()
    result = filter_sources(
        "量子计算芯片",
        [
            _item("https://f.com/1", domain="f.com", title="量子计算芯片", text=body),
            _item("https://g.com/1", domain="g.com", title="量子计算芯片", text=body),
        ],
        min_survivors=1,
    )

    assert result.kept_count == 1
    assert result.dropped[0]["reason"] == "near_duplicate"


def test_per_domain_cap_forces_diversity() -> None:
    result = filter_sources(
        "量子计算芯片",
        [
            _item("https://h.com/1", domain="h.com", title="量子计算芯片一", text=_body("一")),
            _item("https://h.com/2", domain="h.com", title="量子计算芯片二", text=_body("二")),
            _item("https://h.com/3", domain="h.com", title="量子计算芯片三", text=_body("三")),
        ],
        min_survivors=1,
        max_per_domain=2,
    )

    assert result.kept_count == 2
    assert result.dropped[0]["reason"] == "domain_cap"


def test_low_authority_source_is_marked_for_caution() -> None:
    result = filter_sources(
        "量子计算芯片",
        [_item("https://i.com/1", domain="i.com", title="量子计算芯片讨论", text=_body(), source_type="community")],
        min_survivors=1,
    )

    assert result.kept_count == 1
    # Usable as a clue, never as the sole basis for a core fact.
    assert result.kept[0]["needs_caution"] is True


def test_insufficient_survivors_is_flagged_not_fatal() -> None:
    """Per product decision: warn and require review, do not drop everything."""
    result = filter_sources(
        "量子计算芯片",
        [_item("https://j.com/1", domain="j.com", title="量子计算芯片", text=_body())],
        min_survivors=3,
    )

    assert result.kept_count == 1
    assert result.insufficient is True


def test_summary_records_why_each_source_was_dropped() -> None:
    result = filter_sources(
        "量子计算芯片",
        [
            _item("https://k.com/1", domain="k.com", title="天气预报", text=_off_topic_body()),
            _item("https://l.com/1", domain="l.com", title="短", text="量子计算芯片短。"),
        ],
        min_survivors=1,
    )
    summary = result.summary()

    assert summary["reasons"] == {"off_topic": 1, "too_short": 1}
    assert len(summary["dropped_items"]) == 2
    assert all("url" in item and "reason" in item for item in summary["dropped_items"])


def test_relevance_scoring_and_tokens() -> None:
    tokens = topic_tokens("量子计算芯片")
    assert "量子" in tokens
    assert relevance_score("量子计算芯片", {"title": "量子计算芯片", "text": _body()}) >= 0.9
    assert relevance_score("量子计算芯片", {"title": "天气预报", "text": "今天适合出门散步。" * 30}) < 0.12


def test_similarity_detects_identical_text() -> None:
    assert similarity(_body(), _body()) > 0.99
    assert similarity(_body("甲"), _body("乙")) < 0.9
