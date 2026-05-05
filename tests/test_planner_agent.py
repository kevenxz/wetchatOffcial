from __future__ import annotations

import pytest

from workflow.agents.planner import planner_agent_node


@pytest.mark.asyncio
async def test_planner_agent_creates_type_search_and_visual_plan() -> None:
    state = {
        "task_id": "task-1",
        "task_brief": {
            "topic": "国产人形机器人融资潮",
            "audience_roles": ["科技投资人"],
            "article_goal": "解释趋势",
        },
        "research_state": {},
    }

    result = await planner_agent_node(state)

    assert result["planning_state"]["article_type"]["type_id"]
    assert result["planning_state"]["available_skills"]
    assert result["planning_state"]["selected_skill"]["skill_id"]
    assert result["planning_state"]["search_plan"]["angles"]
    assert result["planning_state"]["visual_plan"]["asset_roles"]


@pytest.mark.asyncio
async def test_planner_agent_prioritizes_angles_from_research_gaps() -> None:
    state = {
        "task_id": "task-2",
        "task_brief": {
            "topic": "机器人商业化",
            "audience_roles": ["投资人"],
            "article_goal": "解释趋势",
        },
        "research_state": {
            "evidence_pack": {
                "research_gaps": ["missing_data_evidence", "missing_high_confidence_fact"],
                "quality_summary": {
                    "source_coverage": {"community": 2},
                    "angle_coverage": {"opinion": 2},
                },
            }
        },
    }

    result = await planner_agent_node(state)
    search_plan = result["planning_state"]["search_plan"]

    assert search_plan["angles"][:2] == ["fact", "data"]
    assert "official" in search_plan["coverage_targets"]
    assert "dataset" in search_plan["coverage_targets"]


@pytest.mark.asyncio
async def test_planner_agent_selects_quantum_tech_skill() -> None:
    state = {
        "task_id": "task-quantum",
        "keywords": "量子计算芯片突破",
        "generation_config": {"style_hint": "量子科技风格，解释 qubit 和纠错边界"},
        "task_brief": {
            "topic": "量子计算芯片突破",
            "audience_roles": ["科技读者"],
            "article_goal": "解释量子科技进展",
        },
        "research_state": {},
    }

    result = await planner_agent_node(state)

    selected_skill = result["planning_state"]["selected_skill"]
    assert selected_skill["skill_id"] == "quantum_tech_explainer"
    assert "量子" in selected_skill["name"]


@pytest.mark.asyncio
async def test_planner_agent_marks_wechat_article_without_creating_blueprint() -> None:
    state = {
        "task_id": "task-model-planner",
        "keywords": "36氪融资榜单",
        "generation_config": {"style_hint": "偏深度商业分析"},
        "task_brief": {
            "topic": "36氪融资榜单",
            "audience_roles": ["创业者"],
            "article_goal": "根据榜单生成文章",
        },
        "hotspot_candidates": [{"title": "某 AI 公司完成新融资", "platform_name": "36氪快讯"}],
        "selected_hotspot": {"title": "某 AI 公司完成新融资", "platform_name": "36氪快讯"},
        "research_state": {},
    }

    result = await planner_agent_node(state)

    planning_state = result["planning_state"]
    assert planning_state["selected_skill"]["skill_id"]
    assert planning_state["style_profile"]["content_type"] == "wechat_public_account_article"
    assert "initial_article_blueprint" not in planning_state
    assert "article_blueprint" not in result


@pytest.mark.asyncio
async def test_planner_agent_creates_search_contract_for_finance_topic() -> None:
    state = {
        "task_id": "task-finance",
        "keywords": "某公司 Q1 财报 营收 下滑",
        "generation_config": {
            "research_policy": {
                "search_mode": "standard",
                "auto_deepen_for_sensitive_categories": True,
                "min_sources": 6,
                "min_official_sources": 1,
                "min_cross_sources": 3,
                "require_opposing_view": True,
                "freshness_window_days": 7,
            }
        },
        "task_brief": {
            "topic": "某公司 Q1 财报 营收 下滑",
            "audience_roles": ["投资人"],
            "article_goal": "解释财报影响",
        },
        "research_state": {},
    }

    result = await planner_agent_node(state)
    contract = result["planning_state"]["search_contract"]

    assert contract["category"] == "finance"
    assert contract["search_depth"] == "strict"
    assert contract["query_plan"]
    assert contract["requires_manual_review"] is True
    assert result["planning_state"]["research_plan"]["query_plan"]
