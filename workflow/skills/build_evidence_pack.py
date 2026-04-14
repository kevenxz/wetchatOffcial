"""Build structured evidence artifacts from research outputs."""
from __future__ import annotations

from typing import Any

from workflow.state import WorkflowState
from workflow.utils.evidence_pack import build_evidence_pack


async def build_evidence_pack_node(state: WorkflowState) -> dict[str, Any]:
    """Convert evidence items into grouped evidence pack fields."""
    research_state = dict(state.get("research_state") or {})
    research_state["evidence_pack"] = build_evidence_pack(list(research_state.get("evidence_items") or []))
    return {
        "status": "running",
        "current_skill": "build_evidence_pack",
        "progress": 34,
        "research_state": research_state,
    }
