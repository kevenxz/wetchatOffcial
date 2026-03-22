"""Tests for the new article intent/style/blueprint planning flow."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from api.models import ImageModelConfig, ModelConfig, TextModelConfig
from workflow.skills.build_article_blueprint import build_article_blueprint_node
from workflow.skills.infer_style_profile import infer_style_profile_node
from workflow.skills.interpret_user_intent import interpret_user_intent_node
from workflow.skills.plan_search_queries import plan_search_queries_node
from workflow.skills.rank_sources import rank_sources_node
from workflow.state import WorkflowState


def _empty_model_config() -> ModelConfig:
    return ModelConfig(
        text=TextModelConfig(api_key="", model="gpt-4o", base_url=None),
        image=ImageModelConfig(enabled=False, api_key="", model="dall-e-3", base_url=None),
    )


@pytest.fixture
def base_state() -> WorkflowState:
    return WorkflowState(
        task_id="task-1",
        keywords="AI Agent 商业化前景",
        generation_config={
            "audience_roles": ["投资者", "开发者"],
            "article_strategy": "auto",
            "style_hint": "",
        },
        user_intent={},
        style_profile={},
        article_blueprint={},
        search_queries=[],
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


@pytest.mark.asyncio
async def test_interpret_user_intent_node(base_state: WorkflowState) -> None:
    result = await interpret_user_intent_node(base_state)

    assert result["status"] == "running"
    assert result["user_intent"]["primary_role"] == "投资者"
    assert result["user_intent"]["resolved_strategy"] == "trend_outlook"


@pytest.mark.asyncio
async def test_infer_style_profile_node_falls_back_without_model(base_state: WorkflowState) -> None:
    state = dict(base_state)
    state.update(await interpret_user_intent_node(base_state))
    with patch("workflow.skills.infer_style_profile.get_model_config", return_value=_empty_model_config()):
        result = await infer_style_profile_node(state)

    assert result["style_profile"]["style_source"] == "auto_inferred"
    assert result["style_profile"]["style_archetype"] == "finance_rational"


@pytest.mark.asyncio
async def test_build_article_blueprint_node_builds_compatible_article_plan(base_state: WorkflowState) -> None:
    state = dict(base_state)
    state.update(await interpret_user_intent_node(base_state))
    with patch("workflow.skills.infer_style_profile.get_model_config", return_value=_empty_model_config()):
        state.update(await infer_style_profile_node(state))
    with patch("workflow.skills.build_article_blueprint.get_model_config", return_value=_empty_model_config()):
        result = await build_article_blueprint_node(state)

    assert result["article_blueprint"]["section_outline"]
    assert result["article_plan"]["resolved_strategy"] == "trend_outlook"
    assert "## 局限与风险" in result["article_plan"]["section_outline"]


@pytest.mark.asyncio
async def test_plan_search_queries_node_generates_official_and_market_queries(base_state: WorkflowState) -> None:
    state = dict(base_state)
    state.update(await interpret_user_intent_node(base_state))
    with patch("workflow.skills.infer_style_profile.get_model_config", return_value=_empty_model_config()):
        state.update(await infer_style_profile_node(state))
    with patch("workflow.skills.build_article_blueprint.get_model_config", return_value=_empty_model_config()):
        state.update(await build_article_blueprint_node(state))
    result = await plan_search_queries_node(state)

    queries = [item["query"] for item in result["search_queries"]]
    assert any("official announcement" in query for query in queries)
    assert any("market size" in query for query in queries)


@pytest.mark.asyncio
async def test_rank_sources_node_prefers_official_and_media_diversity(base_state: WorkflowState) -> None:
    state = dict(base_state)
    state["search_results"] = [
        {
            "url": "https://openai.com/blog/ai-agent",
            "domain": "openai.com",
            "provider": "duckduckgo",
            "source_type": "official",
            "authority_score": 0.96,
            "relevance_score": 0.92,
            "freshness_score": 0.08,
            "official_bonus": 0.12,
            "query_intent": "official_fact",
        },
        {
            "url": "https://www.reuters.com/technology/ai-agent",
            "domain": "reuters.com",
            "provider": "duckduckgo",
            "source_type": "media",
            "authority_score": 0.86,
            "relevance_score": 0.88,
            "freshness_score": 0.08,
            "official_bonus": 0.0,
            "query_intent": "reputable_news",
        },
        {
            "url": "https://openai.com/research/ai-agent",
            "domain": "openai.com",
            "provider": "duckduckgo",
            "source_type": "official",
            "authority_score": 0.95,
            "relevance_score": 0.8,
            "freshness_score": 0.05,
            "official_bonus": 0.12,
            "query_intent": "official_fact",
        },
        {
            "url": "https://openai.com/docs/agents",
            "domain": "openai.com",
            "provider": "duckduckgo",
            "source_type": "documentation",
            "authority_score": 0.94,
            "relevance_score": 0.85,
            "freshness_score": 0.05,
            "official_bonus": 0.08,
            "query_intent": "technical_depth",
        },
    ]

    result = await rank_sources_node(state)

    assert result["status"] == "running"
    assert len(result["search_results"]) == 3
    assert result["search_results"][0]["domain"] == "openai.com"
