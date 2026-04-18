"""Aggregate review results into a publish or revision decision."""
from __future__ import annotations

from typing import Any

from workflow.state import WorkflowState
from workflow.utils.quality_scoring import decide_quality_action


async def quality_gate_node(state: WorkflowState) -> dict[str, Any]:
    """Combine article and visual reviews into one next action."""
    article_review = dict(state.get("writing_state", {}).get("article_review") or {})
    visual_review = dict(state.get("visual_state", {}).get("visual_review") or {})
    evidence_pack = dict(state.get("research_state", {}).get("evidence_pack") or {})
    thresholds = dict(state.get("planning_state", {}).get("quality_thresholds") or {})
    next_action = decide_quality_action(article_review, visual_review, thresholds)
    evidence_gaps = list(evidence_pack.get("research_gaps") or [])
    quality_summary = dict(evidence_pack.get("quality_summary") or {})
    blocking_reasons: list[str] = []
    if article_review.get("score", 0) < thresholds.get("article", 80):
        blocking_reasons.append("article_score_below_threshold")
    if visual_review.get("score", 0) < thresholds.get("visual", 75):
        blocking_reasons.append("visual_score_below_threshold")
    blocking_reasons.extend(evidence_gaps)
    return {
        "status": "running",
        "current_skill": "quality_gate",
        "progress": 88,
        "quality_state": {
            "article_review": article_review,
            "visual_review": visual_review,
            "evidence_gaps": evidence_gaps,
            "evidence_quality_summary": quality_summary,
            "quality_report": {
                "article_score": int(article_review.get("score", 0) or 0),
                "visual_score": int(visual_review.get("score", 0) or 0),
                "ready_to_publish": next_action == "pass",
                "blocking_reasons": blocking_reasons,
            },
            "next_action": next_action,
            "ready_to_publish": next_action == "pass",
        },
    }
