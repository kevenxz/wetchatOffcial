"""Review the generated article draft for structural quality."""
from __future__ import annotations

from typing import Any

from workflow.state import WorkflowState


async def review_article_draft_node(state: WorkflowState) -> dict[str, Any]:
    """Run a lightweight structural review over the generated draft."""
    writing_state = dict(state.get("writing_state") or {})
    draft = dict(writing_state.get("draft") or {})
    findings = []
    if "## 风险边界" not in draft.get("content", ""):
        findings.append({"type": "structure", "message": "missing risk boundary section"})
    writing_state["review_findings"] = findings
    writing_state["article_review"] = {"passed": not findings, "score": 85 if not findings else 68}
    return {
        "status": "running",
        "current_skill": "review_article_draft",
        "progress": 60,
        "writing_state": writing_state,
    }
