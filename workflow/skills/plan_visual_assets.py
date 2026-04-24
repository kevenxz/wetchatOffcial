"""Plan role-aware visual assets from article output."""
from __future__ import annotations

from typing import Any

from workflow.state import WorkflowState
from workflow.utils.visual_briefs import build_visual_brief


async def plan_visual_assets_node(state: WorkflowState) -> dict[str, Any]:
    """Generate image briefs for each requested visual role."""
    roles = list(state.get("planning_state", {}).get("visual_plan", {}).get("asset_roles") or [])
    visual_plan = dict(state.get("planning_state", {}).get("visual_plan") or {})
    topic = str(state.get("task_brief", {}).get("topic", ""))
    draft = dict(state.get("writing_state", {}).get("draft") or {})
    briefs = []
    for role in roles:
        brief = build_visual_brief(role, draft, topic)
        style = str(visual_plan.get("style") or "").strip()
        brand_colors = list(visual_plan.get("brand_colors") or [])
        if style or brand_colors:
            brief["compressed_prompt"] = (
                f"{brief.get('compressed_prompt', '')}, style preference: {style or 'brand consistent'}, "
                f"brand colors: {', '.join(str(item) for item in brand_colors) or 'not specified'}"
            )
        brief.update(
            {
                "style": style,
                "brand_colors": brand_colors,
                "title_safe_area": bool(visual_plan.get("title_safe_area", True)),
            }
        )
        briefs.append(brief)
    return {
        "status": "running",
        "current_skill": "plan_visual_assets",
        "progress": 68,
        "visual_state": {
            "image_briefs": briefs,
            "assets": [],
        },
    }
