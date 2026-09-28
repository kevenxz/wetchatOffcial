"""Repair mechanical draft violations before the review stage.

The writer already normalizes its own output, but a revision pass or a fallback
draft can still carry mechanical problems. Fixing them here keeps the review
honest and avoids paying for a full rewrite over a formatting defect.
"""
from __future__ import annotations

from typing import Any

from workflow.state import WorkflowState
from workflow.utils.draft_quality import (
    draft_quality_violations,
    normalize_draft_content,
)


async def normalize_draft_node(state: WorkflowState) -> dict[str, Any]:
    """Apply deterministic repairs to the current draft."""
    writing_state = dict(state.get("writing_state") or {})
    draft = dict(writing_state.get("draft") or {})
    content = str(draft.get("content") or "")
    article_length = str(
        (state.get("config_snapshot", {}).get("content_template") or {}).get("article_length") or "medium"
    )

    if not content.strip():
        return {
            "status": "running",
            "current_skill": "normalize_draft",
            "progress": 56,
            "writing_state": writing_state,
        }

    normalized_content, fixes = normalize_draft_content(content)
    if not fixes:
        return {
            "status": "running",
            "current_skill": "normalize_draft",
            "progress": 56,
            "writing_state": writing_state,
        }

    draft["content"] = normalized_content
    writing_state["draft"] = draft
    existing_fixes = list(writing_state.get("draft_normalization") or [])
    writing_state["draft_normalization"] = list(dict.fromkeys([*existing_fixes, *fixes]))
    writing_state["draft_quality_violations"] = draft_quality_violations(normalized_content, article_length)

    result: dict[str, Any] = {
        "status": "running",
        "current_skill": "normalize_draft",
        "progress": 56,
        "writing_state": writing_state,
    }
    generated_article = dict(state.get("generated_article") or {})
    if generated_article:
        generated_article["content"] = normalized_content
        result["generated_article"] = generated_article
    return result
