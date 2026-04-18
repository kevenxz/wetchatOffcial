"""Route localized revision work after quality review."""
from __future__ import annotations

from typing import Any

from workflow.state import WorkflowState


async def targeted_revision_node(state: WorkflowState) -> dict[str, Any]:
    """Build a localized revision brief for downstream handling."""
    quality_state = dict(state.get("quality_state") or {})
    action = quality_state.get("next_action")
    writing_state = dict(state.get("writing_state") or {})
    visual_state = dict(state.get("visual_state") or {})
    evidence_gaps = list(quality_state.get("evidence_gaps") or [])

    if action == "revise_writing":
        guidance = list(writing_state.get("revision_guidance") or [])
        if evidence_gaps:
            guidance.extend([f"Address evidence gap: {gap}" for gap in evidence_gaps])
        writing_state["revision_brief"] = {
            "mode": "targeted_revision",
            "guidance": guidance,
            "findings": list(writing_state.get("review_findings") or []),
            "target_fields": ["title", "content", "summary"],
            "evidence_gaps": evidence_gaps,
        }
    elif action == "revise_visuals":
        visual_review = dict(visual_state.get("visual_review") or {})
        visual_state["revision_brief"] = {
            "mode": "targeted_revision",
            "guidance": [item.get("message", "") for item in visual_review.get("findings", []) if item.get("message")],
            "findings": list(visual_review.get("findings") or []),
            "target_fields": ["assets"],
        }

    return {
        "status": "running",
        "current_skill": "targeted_revision",
        "progress": 92,
        "writing_state": writing_state,
        "visual_state": visual_state,
        "quality_state": {
            **quality_state,
            "revision_route": action,
        },
    }
