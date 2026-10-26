"""Tests for reading the hotspot's own article before deciding the structure.

The pipeline used to go straight from "which hotspot" to a generic query template,
so every hotspot produced near-identical material and therefore near-identical
article structure.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from workflow.nodes.fetch_hotspot_source import (
    collect_source_urls,
    derive_source_queries,
    fetch_hotspot_source_node,
    resolve_source_url,
)


def _long_text(marker: str) -> str:
    return f"{marker}量子计算芯片的工程指标出现变化值得关注。" * 30


def test_resolve_tophub_redirect_to_original_url() -> None:
    redirect = "https://tophub.today/link?url=https%3A%2F%2Fexample.com%2Farticle%3Fid%3D7"
    assert resolve_source_url(redirect) == "https://example.com/article?id=7"


def test_resolve_leaves_direct_url_untouched() -> None:
    direct = "https://example.com/article"
    assert resolve_source_url(direct) == direct


def test_resolve_keeps_redirect_when_no_usable_target() -> None:
    redirect = "https://tophub.today/n/abc"
    assert resolve_source_url(redirect) == redirect


def test_collect_source_urls_resolves_and_dedupes() -> None:
    state = {
        "selected_hotspot": {"url": "https://tophub.today/link?url=https%3A%2F%2Fa.com%2F1"},
        "selected_topic": {"source_cluster": ["https://a.com/1", "https://b.com/2"]},
        "hotspot_candidates": [{"url": "https://c.com/3"}],
    }

    urls = collect_source_urls(state)

    # The resolved redirect collapses onto the already-present direct URL.
    assert urls == ["https://a.com/1", "https://b.com/2", "https://c.com/3"]


def test_collect_source_urls_drops_unresolvable_ranking_links() -> None:
    state = {"selected_hotspot": {"url": "https://tophub.today/n/only-navigation"}}
    assert collect_source_urls(state) == []


def test_derive_source_queries_uses_title_and_concrete_numbers() -> None:
    text = "该公司宣布投入120亿元，较去年增长35%，预计2026年量产。" + _long_text("")
    queries = derive_source_queries("量子计算芯片", "某公司发布量子芯片", text)

    assert queries
    # An exact-title lookup anchors research on the actual story.
    assert queries[0]["query"] == '"某公司发布量子芯片"'
    joined = " ".join(item["query"] for item in queries)
    assert "120亿元" in joined
    assert all(item["source_type"] for item in queries)


def test_derive_source_queries_is_deduplicated_and_capped() -> None:
    text = "投入120亿元，增长35%，2026年量产，投入120亿元。" + _long_text("")
    queries = derive_source_queries("量子计算芯片", "标题", text, limit=3)
    assert len(queries) <= 3
    assert len({item["query"] for item in queries}) == len(queries)


@pytest.mark.asyncio
async def test_node_reports_unavailable_without_a_source_url() -> None:
    state = {"task_id": "task-1", "selected_topic": {"title": "量子计算芯片"}, "research_state": {}}

    result = await fetch_hotspot_source_node(state)

    assert result["status"] == "running"
    assert result["hotspot_source_status"] == "unavailable"
    assert result["hotspot_sources"] == []
    # The workflow must continue to the search stage regardless.
    assert result["research_state"]["hotspot_source_status"] == "unavailable"


@pytest.mark.asyncio
async def test_node_fetches_and_keeps_the_primary_source() -> None:
    extracted = {
        "url": "https://a.com/1",
        "title": "量子计算芯片取得进展",
        "text": _long_text(""),
        "images": [],
        "source_meta": {},
    }
    state = {
        "task_id": "task-2",
        "selected_topic": {"title": "量子计算芯片", "source_cluster": ["https://a.com/1"]},
        "research_state": {},
    }

    with patch(
        "workflow.nodes.fetch_hotspot_source._fetch_and_extract_single",
        new=AsyncMock(return_value=extracted),
    ):
        result = await fetch_hotspot_source_node(state)

    assert result["hotspot_source_status"] == "resolved"
    assert len(result["hotspot_sources"]) == 1
    assert result["hotspot_sources"][0]["url"] == "https://a.com/1"
    assert result["hotspot_source_queries"]
    # The blueprint reads the article from research_state.
    assert result["research_state"]["hotspot_sources"]


@pytest.mark.asyncio
async def test_node_reports_filtered_out_when_the_article_is_unusable() -> None:
    extracted = {
        "url": "https://a.com/1",
        "title": "太短",
        "text": "太短了。",
        "images": [],
        "source_meta": {},
    }
    state = {
        "task_id": "task-3",
        "selected_topic": {"title": "量子计算芯片", "source_cluster": ["https://a.com/1"]},
        "research_state": {},
    }

    with patch(
        "workflow.nodes.fetch_hotspot_source._fetch_and_extract_single",
        new=AsyncMock(return_value=extracted),
    ):
        result = await fetch_hotspot_source_node(state)

    assert result["hotspot_source_status"] == "filtered_out"
    assert result["hotspot_sources"] == []


@pytest.mark.asyncio
async def test_node_survives_a_fetch_error() -> None:
    state = {
        "task_id": "task-4",
        "selected_topic": {"title": "量子计算芯片", "source_cluster": ["https://a.com/1"]},
        "research_state": {},
    }

    with patch(
        "workflow.nodes.fetch_hotspot_source._fetch_and_extract_single",
        new=AsyncMock(side_effect=RuntimeError("network down")),
    ):
        result = await fetch_hotspot_source_node(state)

    assert result["status"] == "running"
    assert result["hotspot_source_status"] == "unavailable"
    assert result["hotspot_source_error"]


@pytest.mark.asyncio
async def test_node_can_be_disabled_by_configuration() -> None:
    state = {
        "task_id": "task-5",
        "selected_topic": {"title": "量子计算芯片", "source_cluster": ["https://a.com/1"]},
        "research_state": {},
    }

    with patch("workflow.nodes.fetch_hotspot_source.runtime_settings.hotspot_source_enabled", return_value=False):
        result = await fetch_hotspot_source_node(state)

    assert result["hotspot_source_status"] == "disabled"
