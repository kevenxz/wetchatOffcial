"""Run planned research tasks."""
from __future__ import annotations

from typing import Any

from workflow.state import WorkflowState


async def run_research_node(state: WorkflowState) -> dict[str, Any]:
    """Placeholder research runner that exposes query items as evidence items."""
    planning_state = dict(state.get("planning_state") or {})
    queries = list(planning_state.get("search_plan", {}).get("queries") or [])
    evidence_items = [
        {
            "angle": query.get("angle"),
            "query": query.get("query"),
            "claim": f"derived from {query.get('angle')}",
        }
        for query in queries
    ]
    return {
        "status": "running",
        "current_skill": "run_research",
        "progress": 30,
        "research_state": {
            **dict(state.get("research_state") or {}),
            "evidence_items": evidence_items,
        },
    }
