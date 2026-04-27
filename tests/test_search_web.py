"""Tests for search_web skill."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from workflow.tools.search_web import _dedupe_results, search_web_node
from workflow.state import WorkflowState


@pytest.fixture
def mock_state() -> WorkflowState:
    return WorkflowState(
        task_id="test_task_123",
        keywords="OpenAI GPT-4o",
        generation_config={"audience_roles": ["泛科技读者"], "article_strategy": "auto", "style_hint": ""},
        user_intent={"topic": "OpenAI GPT-4o", "resolved_strategy": "trend_outlook", "primary_role": "泛科技读者"},
        style_profile={},
        article_blueprint={},
        search_queries=[
            {"query": "OpenAI GPT-4o official announcement", "intent": "official_fact", "priority": 1},
            {"query": "OpenAI GPT-4o latest news analysis", "intent": "reputable_news", "priority": 2},
        ],
        search_results=[],
        extracted_contents=[],
        article_plan={},
        generated_article={},
        draft_info=None,
        retry_count=0,
        error=None,
        status="running",
        current_skill="",
        progress=0,
        skip_auto_push=False,
    )


def test_dedupe_results() -> None:
    results = [
        {"url": "https://openai.com/blog/gpt-4o", "title": "a"},
        {"url": "https://openai.com/blog/gpt-4o", "title": "duplicate"},
        {"url": "https://platform.openai.com/docs", "title": "b"},
    ]
    deduped = _dedupe_results(results)
    assert [item["url"] for item in deduped] == [
        "https://openai.com/blog/gpt-4o",
        "https://platform.openai.com/docs",
    ]


@pytest.mark.asyncio
async def test_search_web_node_collects_structured_results(mock_state: WorkflowState) -> None:
    with patch.dict("os.environ", {"SERPAPI_API_KEY": "fake-key"}, clear=True):
        with patch("workflow.tools.search_web._search_google", new=AsyncMock(return_value=[
            {
                "url": "https://openai.com/index/hello-gpt-4o",
                "title": "Introducing GPT-4o",
                "snippet": "Official announcement from OpenAI",
            }
        ])):
            with patch("workflow.tools.search_web._search_duckduckgo", new=AsyncMock(return_value=[
                {
                    "url": "https://www.theverge.com/ai/123",
                    "title": "The Verge on GPT-4o",
                    "snippet": "Coverage and analysis",
                }
            ])):
                result = await search_web_node(mock_state)

    assert result["status"] == "running"
    assert result["current_skill"] == "search_web"
    assert len(result["search_results"]) >= 2
    first = result["search_results"][0]
    assert {"url", "title", "domain", "provider", "source_type", "relevance_score"} <= set(first.keys())


@pytest.mark.asyncio
async def test_search_web_node_uses_duckduckgo_without_api_keys(mock_state: WorkflowState) -> None:
    with patch.dict("os.environ", {}, clear=True):
        with patch("workflow.tools.search_web._search_duckduckgo", new=AsyncMock(return_value=[
            {
                "url": "https://openai.com/blog/gpt-4o",
                "title": "Introducing GPT-4o",
                "snippet": "Official announcement",
            }
        ])):
            result = await search_web_node(mock_state)

    assert result["status"] == "running"
    assert result["search_results"][0]["provider"] == "duckduckgo"


@pytest.mark.asyncio
async def test_search_web_node_failed_when_all_providers_empty(mock_state: WorkflowState) -> None:
    with patch.dict("os.environ", {}, clear=True):
        with patch("workflow.tools.search_web._search_duckduckgo", new=AsyncMock(return_value=[])):
            result = await search_web_node(mock_state)

    assert result["status"] == "failed"
    assert "未能搜索到有效结果" in result["error"]


@pytest.mark.asyncio
async def test_search_web_node_retries_provider_calls(mock_state: WorkflowState) -> None:
    mock_state["search_queries"] = [mock_state["search_queries"][0]]
    ddg_mock = AsyncMock(side_effect=[Exception("network-1"), Exception("network-2"), [{
        "url": "https://openai.com/blog/gpt-4o",
        "title": "Introducing GPT-4o",
        "snippet": "Official announcement",
    }]])
    with patch.dict("os.environ", {}, clear=True):
        with patch("workflow.tools.search_web.asyncio.sleep", new=AsyncMock()):
            with patch("workflow.tools.search_web._search_duckduckgo", new=ddg_mock):
                result = await search_web_node(mock_state)

    assert result["status"] == "running"
    assert ddg_mock.await_count == 3
