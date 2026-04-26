"""Image generation agent node."""
from __future__ import annotations

from typing import Any

from workflow.skills.generate_visual_assets import generate_visual_assets_node
from workflow.state import WorkflowState


async def image_agent_node(state: WorkflowState) -> dict[str, Any]:
    """Generate images from planned visual briefs using the configured image model."""
    result = await generate_visual_assets_node(state)
    visual_state = dict(result.get("visual_state") or {})
    visual_state["agent"] = {
        "name": "image_agent",
        "model_source": "ModelConfig.image",
        "brief_count": len(list(visual_state.get("image_briefs") or [])),
        "asset_count": len(list(visual_state.get("assets") or [])),
    }
    return {
        **result,
        "current_skill": "image_agent",
        "visual_state": visual_state,
    }
