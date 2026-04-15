"""Route localized revision work after quality review."""
from __future__ import annotations

from typing import Any

from workflow.state import WorkflowState


async def targeted_revision_node(state: WorkflowState) -> dict[str, Any]:
    """Build a localized revision brief for downstream handling."""
    action = state.get("quality_state", {}).get("next_action")
    writing_state = dict(state.get("writing_state") or {})
    visual_state = dict(state.get("visual_state") or {})

    if action == "revise_writing":
        writing_state["revision_brief"] = {
            "mode": "targeted_revision",
            "guidance": list(writing_state.get("revision_guidance") or []),
            "findings": list(writing_state.get("review_findings") or []),
            "target_fields": ["title", "content", "summary"],
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
            **dict(state.get("quality_state") or {}),
            "revision_route": action,
        },
    }
