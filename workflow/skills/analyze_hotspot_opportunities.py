"""Analyze hotspot opportunities for planner-driven workflow."""
from __future__ import annotations

from typing import Any

from workflow.state import WorkflowState
from workflow.utils.hotspot_scoring import score_hotspot_candidate
from workflow.utils.hotspot_sources import collect_hotspot_candidates


async def analyze_hotspot_opportunities_node(state: WorkflowState) -> dict[str, Any]:
    """Collect and rank hotspot candidates into research state."""
    brief = dict(state.get("task_brief") or {})
    config = dict(brief.get("hotspot_policy") or {})
    candidates = collect_hotspot_candidates(brief, config)
    ranked = sorted(
        [{**item, "selection_score": score_hotspot_candidate(item)} for item in candidates],
        key=lambda item: item["selection_score"],
        reverse=True,
    )
    return {
        "status": "running",
        "current_skill": "analyze_hotspot_opportunities",
        "progress": 18,
        "research_state": {
            **dict(state.get("research_state") or {}),
            "hotspot_candidates": ranked,
            "selected_hotspot": ranked[0] if ranked else None,
        },
    }
