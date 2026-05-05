"""Plan structured research queries from planner state."""
from __future__ import annotations

from typing import Any

from workflow.state import WorkflowState
from workflow.utils.research_queries import build_research_queries


async def plan_research_node(state: WorkflowState) -> dict[str, Any]:
    """Generate research queries from Search Contract, with legacy angle fallback."""
    planning_state = dict(state.get("planning_state") or {})
    search_plan = dict(planning_state.get("search_plan") or {})
    search_contract = dict(planning_state.get("search_contract") or {})
    selected_topic = dict(state.get("selected_topic") or {})
    topic = str(selected_topic.get("title") or state.get("task_brief", {}).get("topic", ""))
    query_plan = list(search_contract.get("query_plan") or search_plan.get("query_plan") or [])

    if query_plan:
        queries = [
            {
                "query": str(item.get("query") or "").strip(),
                "angle": str(item.get("source_type") or item.get("angle") or "fact").strip() or "fact",
                "intent": str(item.get("purpose") or item.get("intent") or "").strip(),
                "purpose": str(item.get("purpose") or "").strip(),
                "source_type": str(item.get("source_type") or "unknown").strip(),
                "priority": int(item.get("priority") or index + 1),
                "freshness_window_days": int(search_contract.get("freshness_window_days") or 7),
            }
            for index, item in enumerate(query_plan)
            if isinstance(item, dict) and str(item.get("query") or "").strip()
        ]
    else:
        queries = build_research_queries(topic, list(search_plan.get("angles") or []))

    if selected_topic.get("category"):
        queries.append(
            {
                "query": f"{topic} {selected_topic['category']} background impact",
                "angle": "hotspot_context",
                "purpose": "supplement hotspot context and impact",
                "source_type": "media",
                "priority": len(queries) + 1,
            }
        )

    search_plan["queries"] = sorted(queries, key=lambda item: int(item.get("priority") or 99))
    planning_state["search_plan"] = search_plan
    return {
        "status": "running",
        "current_skill": "plan_research",
        "progress": 24,
        "planning_state": planning_state,
    }
