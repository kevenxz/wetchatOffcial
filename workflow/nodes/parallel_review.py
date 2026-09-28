"""Review the draft for editorial quality and distribution potential.

Both reviews only depend on the finished draft, so they are independent. The
article review still runs alongside the virality review, but a hard structural
failure cancels the in-flight virality call: a draft that leaks planning language
or uses raw source titles as headings must be rewritten before its distribution
score carries any meaning.
"""
from __future__ import annotations

import asyncio
from typing import Any

import structlog

from workflow.agents.reviewer import review_article_draft_node
from workflow.agents.virality import review_viral_potential_node
from workflow.state import WorkflowState

logger = structlog.get_logger(__name__)

# Findings that force a rewrite regardless of how the draft would score on reach.
HARD_STRUCTURAL_FINDINGS = frozenset(
    {
        "planning_language",
        "source_heading",
        "fragmented_structure",
    }
)


def _has_hard_structural_failure(writing_state: dict[str, Any]) -> bool:
    """Return True when the draft must be rewritten before distribution review."""
    review = dict(writing_state.get("article_review") or {})
    if review.get("passed", True):
        return False
    findings = list(writing_state.get("review_findings") or [])
    return any(
        str(item.get("type") or "") in HARD_STRUCTURAL_FINDINGS
        for item in findings
        if isinstance(item, dict)
    )


async def parallel_review_node(state: WorkflowState) -> dict[str, Any]:
    """Score editorial quality and distribution potential concurrently."""
    viral_task = asyncio.create_task(review_viral_potential_node(state))

    try:
        article_result = await review_article_draft_node(state)
    except BaseException:
        viral_task.cancel()
        raise

    writing_state = dict(article_result.get("writing_state") or {})

    if _has_hard_structural_failure(writing_state):
        # Cancel the wasted virality call; the draft is going back for a rewrite.
        viral_task.cancel()
        try:
            await viral_task
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001
            pass
        logger.info(
            "parallel_review_short_circuit",
            task_id=str(state.get("task_id") or ""),
            reason="hard_structural_failure",
        )
        return {
            "status": "running",
            "current_skill": "parallel_review",
            "progress": 66,
            "writing_state": writing_state,
            "viral_state": dict(state.get("viral_state") or {}),
        }

    try:
        viral_result = await viral_task
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "parallel_review_viral_failed",
            task_id=str(state.get("task_id") or ""),
            error=str(exc),
        )
        viral_result = {}

    return {
        "status": "running",
        "current_skill": "parallel_review",
        "progress": 66,
        "writing_state": writing_state,
        "viral_state": dict(viral_result.get("viral_state") or state.get("viral_state") or {}),
    }
