"""Plan multi-angle research queries from planner state."""
from __future__ import annotations

from typing import Any

from workflow.state import WorkflowState
from workflow.utils.research_queries import build_research_queries


async def plan_research_node(state: WorkflowState) -> dict[str, Any]:
    """Generate research queries for each configured evidence angle."""
    planning_state = dict(state.get("planning_state") or {})
    search_plan = dict(planning_state.get("search_plan") or {})
    selected_topic = dict(state.get("selected_topic") or {})
    topic = str(selected_topic.get("title") or state.get("task_brief", {}).get("topic", ""))
    queries = build_research_queries(
        topic,
        list(search_plan.get("angles") or []),
    )
    if selected_topic.get("category"):
        queries.append(
            {
                "query": f"{topic} {selected_topic['category']} 背景 影响",
                "angle": "hotspot_context",
            }
        )
    search_plan["queries"] = queries
    planning_state["search_plan"] = search_plan
    return {
        "status": "running",
        "current_skill": "plan_research",
        "progress": 24,
        "planning_state": planning_state,
    }
