"""Review generated visual assets for basic completeness."""
from __future__ import annotations

from typing import Any

from workflow.state import WorkflowState


async def review_visual_assets_node(state: WorkflowState) -> dict[str, Any]:
    """Run a lightweight completeness review on visual assets."""
    visual_state = dict(state.get("visual_state") or {})
    assets = list(visual_state.get("assets") or [])
    evidence_pack = dict(state.get("research_state", {}).get("evidence_pack") or {})
    research_gaps = list(evidence_pack.get("research_gaps") or [])
    findings = []
    for asset in assets:
        if not asset.get("url") and not asset.get("path"):
            findings.append({"role": asset.get("role"), "message": "missing generated asset"})
        if asset.get("role") == "infographic" and "missing_data_evidence" in research_gaps:
            findings.append({"role": asset.get("role"), "message": "infographic lacks supporting data evidence"})
    visual_state["visual_review"] = {"passed": not findings, "score": 82 if not findings else 60, "findings": findings}
    return {
        "status": "running",
        "current_skill": "review_visual_assets",
        "progress": 78,
        "visual_state": visual_state,
    }
