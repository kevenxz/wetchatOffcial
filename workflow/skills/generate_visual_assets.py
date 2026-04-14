"""Generate visual assets from planned briefs."""
from __future__ import annotations

from typing import Any

from workflow.state import WorkflowState


async def generate_visual_assets_node(state: WorkflowState) -> dict[str, Any]:
    """Convert visual briefs into placeholder asset records."""
    visual_state = dict(state.get("visual_state") or {})
    briefs = list(visual_state.get("image_briefs") or [])
    visual_state["assets"] = [
        {
            "role": brief.get("role"),
            "prompt": brief.get("compressed_prompt"),
            "path": f"generated://{brief.get('role')}",
            "url": "",
        }
        for brief in briefs
    ]
    return {
        "status": "running",
        "current_skill": "generate_visual_assets",
        "progress": 74,
        "visual_state": visual_state,
    }
