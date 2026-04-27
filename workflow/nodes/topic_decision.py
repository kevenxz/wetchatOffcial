"""Analyze hotspot opportunities for planner-driven workflow."""
from __future__ import annotations

from typing import Any

from workflow.state import WorkflowState
from workflow.utils.hotspot_scoring import score_hotspot_candidate


def _topic_from_candidate(candidate: dict[str, Any] | None, brief: dict[str, Any]) -> dict[str, Any] | None:
    if not candidate:
        return None
    topic_title = str(candidate.get("title") or brief.get("topic") or "").strip()
    if not topic_title:
        return None
    config = dict(brief.get("hotspot_policy") or {})
    filters = dict(config.get("filters") or {})
    return {
        "topic_id": str(candidate.get("topic_id") or candidate.get("url") or topic_title),
        "title": topic_title,
        "source": candidate.get("source") or "manual",
        "category": candidate.get("category") or "",
        "angle": "热点解读型" if config.get("enabled") else "手动主题型",
        "source_cluster": [candidate.get("url")] if candidate.get("url") else [],
        "hot_score": float(candidate.get("selection_score") or candidate.get("heat") or 0),
        "account_fit_score": float(candidate.get("account_fit") or candidate.get("account_fit_score") or 0),
        "risk_score": float(candidate.get("risk") or candidate.get("risk_score") or 0),
        "min_score": float(filters.get("min_selection_score") or 0),
        "recommended": True,
    }


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
            "selected_topic": _topic_from_candidate(selected, brief),
        },
        "selected_topic": _topic_from_candidate(selected, brief),
    }
