"""Image generation agent node.

Three steps run inside this single node — describe the visuals, generate them, then
review them. That ordering matters: the pipeline previously skipped straight to
generation with no description of the picture at all, which is why the images came back
as walls of text unrelated to the article.

All three steps stay in ONE node on purpose. LangGraph joins a fan-in when the incoming
edges fire in the same step, so a branch that is *longer* than its sibling causes the join
node to run early with an incomplete state — and then run again when the longer branch
finally arrives. Keeping this branch one step deep makes the join at ``quality_gate`` a
real barrier instead of a race.
"""
from __future__ import annotations

from typing import Any

from workflow.agents.visual_describer import describe_visual_assets_node
from workflow.agents.visual_reviewer import review_visual_assets_node
from workflow.state import WorkflowState
from workflow.tools.image_generation import generate_visual_assets_node


async def image_agent_node(state: WorkflowState) -> dict[str, Any]:
    """Describe each picture, generate it, then review the resulting assets."""
    described = await describe_visual_assets_node(state)
    generated = await generate_visual_assets_node({**state, **described})

    # The review must see the assets that were just produced.
    reviewed = await review_visual_assets_node({**state, **generated})

    visual_state = dict(generated.get("visual_state") or {})
    visual_state.update(dict(reviewed.get("visual_state") or {}))
    visual_state["agent"] = {
        "name": "image_agent",
        "model_source": "ModelConfig.image",
        "brief_count": len(list(visual_state.get("image_briefs") or [])),
        "spec_count": len(list(visual_state.get("visual_specs") or [])),
        "asset_count": len(list(visual_state.get("assets") or [])),
        "describe_degraded_reason": visual_state.get("describe_degraded_reason"),
        "review_included": True,
    }

    return {
        **generated,
        "current_skill": "image_agent",
        "progress": reviewed.get("progress", generated.get("progress")),
        "visual_state": visual_state,
    }
