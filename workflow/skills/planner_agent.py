"""Planner stage for the redesigned workflow."""
from __future__ import annotations

from typing import Any

from workflow.state import WorkflowState
from workflow.utils.article_type_registry import get_article_type_registry


async def planner_agent_node(state: WorkflowState) -> dict[str, Any]:
    """Create the initial article, search, and visual plan."""
    brief = dict(state.get("task_brief") or {})
    registry = get_article_type_registry()
    article_goal = str(brief.get("article_goal") or "")
    article_type = registry["trend_analysis"] if "趋势" in article_goal else registry["hotspot_interpretation"]
    planning_state = {
        "article_type": article_type,
        "search_plan": {
            "angles": ["fact", "news", "opinion", "case", "data"],
            "queries": [],
        },
        "visual_plan": {
            "asset_roles": article_type["visual_preferences"],
            "quality_threshold": 75,
        },
        "quality_thresholds": {
            "article": 80,
            "visual": 75,
            "evidence": 80,
            "hotspot": 70,
        },
    }
    return {
        "status": "running",
        "current_skill": "planner_agent",
        "progress": 12,
        "planning_state": planning_state,
    }
