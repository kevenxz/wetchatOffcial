"""Finalize article type decision from evidence density."""
from __future__ import annotations

from typing import Any

from workflow.state import WorkflowState
from workflow.utils.article_type_registry import get_article_type_registry


async def resolve_article_type_node(state: WorkflowState) -> dict[str, Any]:
    """Resolve the working article type from planning and evidence state."""
    planning_state = dict(state.get("planning_state") or {})
    evidence_pack = dict(state.get("research_state", {}).get("evidence_pack") or {})
    if len(evidence_pack.get("usable_data_points", [])) >= 2:
        planning_state["article_type"] = get_article_type_registry()["trend_analysis"]
    return {
        "status": "running",
        "current_skill": "resolve_article_type",
        "progress": 38,
        "planning_state": planning_state,
    }
