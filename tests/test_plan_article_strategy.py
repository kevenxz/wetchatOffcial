"""Tests for article strategy planning skill."""
import pytest

from workflow.skills.plan_article_strategy import plan_article_strategy_node
from workflow.state import WorkflowState


@pytest.mark.asyncio
async def test_plan_article_strategy_node_with_investor_role():
    state = WorkflowState(
        task_id="task_1",
        keywords="AI Agent 投资机会",
        generation_config={"audience_roles": ["投资者", "开发者"], "article_strategy": "auto"},
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

    result = await plan_article_strategy_node(state)

    assert result["status"] == "running"
    assert result["current_skill"] == "plan_article_strategy"
    assert result["article_plan"]["primary_role"] == "投资者"
    assert result["article_plan"]["resolved_strategy"] == "trend_outlook"
    assert result["article_plan"]["resolved_strategy_label"] == "趋势展望式"
    assert "## 局限与风险" in result["article_plan"]["section_outline"]
