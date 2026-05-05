"""Build structured evidence artifacts from research outputs."""
from __future__ import annotations

from typing import Any

from workflow.state import WorkflowState
from workflow.utils.evidence_pack import build_evidence_pack


async def build_evidence_pack_node(state: WorkflowState) -> dict[str, Any]:
    """Convert evidence items into grouped evidence pack fields."""
    research_state = dict(state.get("research_state") or {})
    evidence_pack = build_evidence_pack(list(research_state.get("evidence_items") or []))
    search_evaluation = dict(research_state.get("search_evaluation") or {})
    if search_evaluation:
        evidence_pack["search_evaluation"] = search_evaluation
        merged_gaps = list(evidence_pack.get("research_gaps") or [])
        for gap in list(search_evaluation.get("missing_questions") or []):
            if gap not in merged_gaps:
                merged_gaps.append(gap)
        evidence_pack["research_gaps"] = merged_gaps
    research_state["evidence_pack"] = evidence_pack
    return {
        "status": "running",
        "current_skill": "build_evidence_pack",
        "progress": 34,
        "research_state": research_state,
    }
