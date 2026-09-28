from types import SimpleNamespace
from unittest.mock import patch

import pytest

from workflow.agents.virality import design_viral_strategy_node, review_viral_potential_node


def _model_config_without_key() -> SimpleNamespace:
    return SimpleNamespace(text=SimpleNamespace(api_key="", model="test-model", base_url=None))


@pytest.mark.asyncio
async def test_design_viral_strategy_builds_an_editorial_goal_contract() -> None:
    state = {
        "task_id": "task-1",
        "keywords": "AI Agent",
        "task_brief": {"topic": "AI Agent", "primary_audience": "产品经理"},
        "research_state": {"evidence_pack": {"quality_summary": {"high_confidence_items": 2}}},
    }

    with patch("workflow.model_factory.get_model_config", return_value=_model_config_without_key()):
        result = await design_viral_strategy_node(state)

    strategy = result["viral_state"]["strategy"]
    assert result["current_skill"] == "design_viral_strategy"
    assert "AI Agent" in strategy["core_promise"]
    assert len(strategy["title_hypotheses"]) == 3
    assert strategy["share_trigger"]


@pytest.mark.asyncio
async def test_review_viral_potential_returns_weighted_dimensions_and_revision_guidance() -> None:
    state = {
        "task_id": "task-2",
        "viral_state": {
            "strategy": {
                "audience_tension": "读者不知道变化与自己有什么关系",
                "core_promise": "给出可执行判断",
                "novelty_angle": "从利益变化而不是新闻经过切入",
                "share_trigger": "一句可复述的结论",
            }
        },
        "writing_state": {
            "draft": {
                "title": "AI Agent 真正改变的，不只是工作效率",
                "content": "变化已经发生，但真正的问题不是工具多了。\n\n## 变化信号\n\n这意味着团队需要重新判断下一步。",
            }
        },
        "research_state": {
            "evidence_pack": {
                "quality_summary": {"high_confidence_items": 1},
                "citations": [{"url": "https://example.com"}],
            }
        },
        "config_snapshot": {"review_policy": {"viral_threshold": 78}},
    }

    with patch("workflow.model_factory.get_model_config", return_value=_model_config_without_key()):
        result = await review_viral_potential_node(state)

    review = result["viral_state"]["review"]
    assert set(review["dimensions"]) == {
        "headline",
        "hook",
        "novelty",
        "resonance",
        "shareability",
        "credibility",
        "readability",
    }
    assert review["score"] > 0
    # The virality review publishes through viral_state only: writing_state belongs to
    # the concurrent article review, and both writing the same key would conflict.
    assert "writing_state" not in result
    assert result["viral_state"]["review"] == review

