from __future__ import annotations

import pytest

from workflow.skills.run_research import run_research_node


@pytest.mark.asyncio
async def test_run_research_builds_evidence_items_from_search_and_extract(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_search_web_node(state: dict) -> dict:
        assert state["search_queries"][0]["intent"] == "fact"
        return {
            "status": "running",
            "search_results": [
                {
                    "url": "https://example.com/report",
                    "title": "Example Report",
                    "snippet": "Robotics funding accelerated in 2026.",
                    "query": state["search_queries"][0]["query"],
                    "query_intent": "fact",
                    "domain": "example.com",
                    "source_type": "official",
                    "provider": "duckduckgo",
                    "authority_score": 0.95,
                    "final_score": 0.91,
                }
            ],
        }

    async def fake_fetch_extract_node(state: dict) -> dict:
        assert state["search_results"][0]["url"] == "https://example.com/report"
        return {
            "status": "running",
            "extracted_contents": [
                {
                    "url": "https://example.com/report",
                    "title": "Example Report",
                    "text": "Robotics funding accelerated in 2026. Investors are paying close attention to embodied AI.",
                    "source_meta": {
                        "query": state["search_results"][0]["query"],
                        "query_intent": "fact",
                        "domain": "example.com",
                        "source_type": "official",
                        "provider": "duckduckgo",
                        "final_score": 0.91,
                    },
                }
            ],
        }

    monkeypatch.setattr("workflow.skills.run_research.search_web_node", fake_search_web_node)
    monkeypatch.setattr("workflow.skills.run_research.fetch_extract_node", fake_fetch_extract_node)

    state = {
        "task_id": "task-1",
        "task_brief": {"topic": "机器人融资潮"},
        "planning_state": {
            "search_plan": {
                "queries": [
                    {"angle": "fact", "query": "机器人融资潮 official announcement"},
                ]
            }
        },
        "research_state": {},
    }

    result = await run_research_node(state)
    evidence_items = result["research_state"]["evidence_items"]

    assert result["current_skill"] == "run_research"
    assert result["research_state"]["search_results"]
    assert result["research_state"]["extracted_contents"]
    assert evidence_items[0]["angle"] == "fact"
    assert evidence_items[0]["source_type"] == "official"
    assert evidence_items[0]["claim"]


@pytest.mark.asyncio
async def test_run_research_marks_low_authority_sources_for_caution(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_search_web_node(state: dict) -> dict:
        return {
            "status": "running",
            "search_results": [
                {
                    "url": "https://community.example.com/post",
                    "title": "Forum Post",
                    "snippet": "People are debating the robotics market.",
                    "query": state["search_queries"][0]["query"],
                    "query_intent": "opinion",
                    "domain": "community.example.com",
                    "source_type": "community",
                    "provider": "duckduckgo",
                    "authority_score": 0.41,
                    "final_score": 0.46,
                }
            ],
        }

    async def fake_fetch_extract_node(state: dict) -> dict:
        return {
            "status": "running",
            "extracted_contents": [
                {
                    "url": "https://community.example.com/post",
                    "title": "Forum Post",
                    "text": "People are debating the robotics market and disagree on commercial timing.",
                    "source_meta": {
                        "query": state["search_results"][0]["query"],
                        "query_intent": "opinion",
                        "domain": "community.example.com",
                        "source_type": "community",
                        "provider": "duckduckgo",
                        "authority_score": 0.41,
                        "final_score": 0.46,
                    },
                }
            ],
        }

    monkeypatch.setattr("workflow.skills.run_research.search_web_node", fake_search_web_node)
    monkeypatch.setattr("workflow.skills.run_research.fetch_extract_node", fake_fetch_extract_node)

    state = {
        "task_id": "task-2",
        "task_brief": {"topic": "机器人商业化"},
        "planning_state": {"search_plan": {"queries": [{"angle": "opinion", "query": "机器人商业化 expert opinion"}]}},
        "research_state": {},
    }

    result = await run_research_node(state)
    evidence_item = result["research_state"]["evidence_items"][0]

    assert evidence_item["needs_caution"] is True
    assert evidence_item["evidence_score"] < 0.6
