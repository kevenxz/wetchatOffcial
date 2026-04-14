"""Route localized revision work after quality review."""
from __future__ import annotations

from typing import Any

from workflow.state import WorkflowState


async def targeted_revision_node(state: WorkflowState) -> dict[str, Any]:
    """Store the selected revision route for downstream handling."""
    action = state.get("quality_state", {}).get("next_action")
    return {
        "status": "running",
        "current_skill": "targeted_revision",
        "progress": 92,
        "quality_state": {
            **dict(state.get("quality_state") or {}),
            "revision_route": action,
        },
    }
