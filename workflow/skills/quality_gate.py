"""Aggregate review results into a publish or revision decision."""
from __future__ import annotations

from typing import Any

from workflow.state import WorkflowState
from workflow.utils.quality_scoring import decide_quality_action


async def quality_gate_node(state: WorkflowState) -> dict[str, Any]:
    """Combine article and visual reviews into one next action."""
    article_review = dict(state.get("writing_state", {}).get("article_review") or {})
    visual_review = dict(state.get("visual_state", {}).get("visual_review") or {})
    thresholds = dict(state.get("planning_state", {}).get("quality_thresholds") or {})
    next_action = decide_quality_action(article_review, visual_review, thresholds)
    return {
        "status": "running",
        "current_skill": "quality_gate",
        "progress": 88,
        "quality_state": {
            "article_review": article_review,
            "visual_review": visual_review,
            "next_action": next_action,
            "ready_to_publish": next_action == "pass",
        },
    }
