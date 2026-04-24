"""Analyze hotspot opportunities for planner-driven workflow."""
from __future__ import annotations

from typing import Any

from workflow.state import WorkflowState
from workflow.utils.hotspot_scoring import score_hotspot_candidate


async def analyze_hotspot_opportunities_node(state: WorkflowState) -> dict[str, Any]:
    """Collect and rank hotspot candidates into research state."""
    brief = dict(state.get("task_brief") or {})
    config = dict(brief.get("hotspot_policy") or {})
    captured_candidates = list(state.get("hotspot_candidates") or [])
    selected_hotspot = state.get("selected_hotspot")

    if captured_candidates:
        ranked = sorted(
            captured_candidates,
            key=lambda item: float(item.get("selection_score") or item.get("hot_score") or 0),
            reverse=True,
        )
        selected = selected_hotspot or ranked[0]
    elif config.get("enabled"):
        ranked = []
        selected = None
    else:
        topic = str(brief.get("topic") or "").strip()
        candidates = [
            {
                "source": "manual",
                "title": topic,
                "heat": 60,
                "relevance": 80,
                "timeliness": 60,
                "evidence_density": 70,
                "expandability": 75,
                "account_fit": 80,
                "risk": 15,
                "config": config,
            }
        ] if topic else []
        ranked = sorted(
            [{**item, "selection_score": score_hotspot_candidate(item)} for item in candidates],
            key=lambda item: item["selection_score"],
            reverse=True,
        )
        selected = ranked[0] if ranked else None
    return {
        "status": "running",
        "current_skill": "analyze_hotspot_opportunities",
        "progress": 18,
        "research_state": {
            **dict(state.get("research_state") or {}),
            "hotspot_candidates": ranked,
            "selected_hotspot": selected,
            "hotspot_capture_error": state.get("hotspot_capture_error"),
        },
    }
