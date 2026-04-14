"""Plan role-aware visual assets from article output."""
from __future__ import annotations

from typing import Any

from workflow.state import WorkflowState
from workflow.utils.visual_briefs import build_visual_brief


async def plan_visual_assets_node(state: WorkflowState) -> dict[str, Any]:
    """Generate image briefs for each requested visual role."""
    roles = list(state.get("planning_state", {}).get("visual_plan", {}).get("asset_roles") or [])
    topic = str(state.get("task_brief", {}).get("topic", ""))
    draft = dict(state.get("writing_state", {}).get("draft") or {})
    briefs = [build_visual_brief(role, draft, topic) for role in roles]
    return {
        "status": "running",
        "current_skill": "plan_visual_assets",
        "progress": 68,
        "visual_state": {
            "image_briefs": briefs,
            "assets": [],
        },
    }
