"""Plan structured research queries from planner state."""
from __future__ import annotations

from typing import Any

from workflow.state import WorkflowState
from workflow.utils.research_queries import build_research_queries


def _priority_of(item: dict[str, Any], default: int = 99) -> int:
    """Read a query priority without treating a legitimate ``0`` as missing."""
    value = item.get("priority")
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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
                "priority": _priority_of(item, index + 1),
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

    # Queries derived from the hotspot's own article come first: the generic template
    # plan only fills the gaps the primary source leaves.
    source_queries = [item for item in list(state.get("hotspot_source_queries") or []) if isinstance(item, dict)]
    if source_queries:
        existing = {str(item.get("query") or "").strip() for item in queries}
        prioritized: list[dict[str, Any]] = []
        for index, item in enumerate(source_queries):
            query = str(item.get("query") or "").strip()
            if not query or query in existing:
                continue
            existing.add(query)
            prioritized.append(
                {
                    "query": query,
                    "angle": str(item.get("angle") or "hotspot_source").strip(),
                    "intent": str(item.get("purpose") or "").strip(),
                    "purpose": str(item.get("purpose") or "").strip(),
                    "source_type": str(item.get("source_type") or "media").strip(),
                    "priority": index + 1,
                    "freshness_window_days": int(search_contract.get("freshness_window_days") or 7),
                }
            )
        if prioritized:
            # Shift the template plan behind the source-derived queries.
            offset = len(prioritized)
            for item in queries:
                item["priority"] = _priority_of(item, 99) + offset
            queries = [*prioritized, *queries]

    search_plan["queries"] = sorted(queries, key=_priority_of)
    planning_state["search_plan"] = search_plan
    return {
        "status": "running",
        "current_skill": "plan_research",
        "progress": 24,
        "planning_state": planning_state,
    }
