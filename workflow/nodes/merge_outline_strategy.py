"""Join the concurrently produced distribution strategy and article blueprint."""
from __future__ import annotations

from typing import Any

from workflow.agents.outline import merge_viral_into_outline
from workflow.state import WorkflowState


async def merge_outline_strategy_node(state: WorkflowState) -> dict[str, Any]:
    """Fold the viral strategy into the outline result.

    Runs after the ``design_viral_strategy`` and ``outline_planner`` fan-out legs
    have both settled, so the writer still receives one coherent outline contract.
    """
    planning_state = dict(state.get("planning_state") or {})
    outline_result = dict(state.get("outline_result") or planning_state.get("outline_result") or {})
    viral_strategy = dict(state.get("viral_state", {}).get("strategy") or {})

    if not outline_result:
        from workflow.agents.outline import _normalize_outline

        outline_result = _normalize_outline(
            dict(planning_state.get("article_blueprint") or {}),
            dict(state.get("research_state") or {}),
        )

    outline_result = merge_viral_into_outline(outline_result, viral_strategy)
    if planning_state.get("selected_skill"):
        outline_result["selected_skill"] = dict(planning_state.get("selected_skill") or {})
    planning_state["outline_result"] = outline_result

    return {
        "status": "running",
        "current_skill": "merge_outline_strategy",
        "progress": 52,
        "outline_result": outline_result,
        "planning_state": planning_state,
    }
