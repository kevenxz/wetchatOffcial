"""Tests for concurrent research execution."""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from workflow.nodes.run_research import run_research_node


def _state(query_count: int) -> dict:
    return {
        "task_id": "task-research",
        "keywords": "机器人融资",
        "task_brief": {"topic": "机器人融资"},
        "planning_state": {
            "search_contract": {
                "search_depth": "quick",
                "min_source_count": 1,
                "min_authoritative_source_count": 0,
                "min_cross_source_count": 1,
                "require_opposing_view": False,
            },
            "search_plan": {
                "queries": [
                    {"query": f"查询{i}", "angle": "fact", "priority": i + 1}
                    for i in range(query_count)
                ]
            },
        },
        "research_state": {},
    }


@pytest.mark.asyncio
async def test_research_queries_run_concurrently() -> None:
    """All queries in a round must overlap instead of running one after another."""
    active = 0
    max_active = 0

    async def fake_search(state: dict) -> dict:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.05)
        active -= 1
        query = state["search_queries"][0]["query"]
        return {
            "status": "running",
            "search_results": [{"url": f"https://example.com/{query}", "query": query}],
        }

    async def fake_extract(state: dict) -> dict:
        return {
            "status": "running",
            "extracted_contents": [
                {"url": item["url"], "title": "t", "text": "x" * 80, "source_meta": {"query": item["query"]}}
                for item in state["search_results"]
            ],
        }

    with patch("workflow.nodes.run_research.search_web_node", side_effect=fake_search):
        with patch("workflow.nodes.run_research.fetch_extract_node", side_effect=fake_extract):
            result = await run_research_node(_state(query_count=4))

    assert max_active > 1, "queries were executed serially"
    assert len(result["research_state"]["search_results"]) == 4
    assert result["research_state"]["search_runs"][0]["search_result_count"] == 4


@pytest.mark.asyncio
async def test_single_query_failure_records_gap_without_aborting_round() -> None:
    async def fake_search(state: dict) -> dict:
        query = state["search_queries"][0]["query"]
        if query == "查询1":
            return {"status": "failed", "error": "provider down"}
        return {
            "status": "running",
            "search_results": [{"url": f"https://example.com/{query}", "query": query}],
        }

    async def fake_extract(state: dict) -> dict:
        return {
            "status": "running",
            "extracted_contents": [
                {"url": item["url"], "title": "t", "text": "x" * 80, "source_meta": {"query": item["query"]}}
                for item in state["search_results"]
            ],
        }

    with patch("workflow.nodes.run_research.search_web_node", side_effect=fake_search):
        with patch("workflow.nodes.run_research.fetch_extract_node", side_effect=fake_extract):
            result = await run_research_node(_state(query_count=3))

    gaps = result["research_state"]["research_gaps"]
    assert any(gap.get("stage") == "search_web" and "查询1" in gap.get("queries", []) for gap in gaps)
    # The healthy queries still produced results.
    assert len(result["research_state"]["search_results"]) == 2
