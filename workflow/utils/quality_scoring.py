"""Quality decision helpers for the redesigned workflow."""
from __future__ import annotations

from typing import Any


def decide_quality_action(
    article_review: dict[str, Any],
    visual_review: dict[str, Any],
    thresholds: dict[str, int],
    viral_review: dict[str, Any] | None = None,
) -> str:
    """Choose the next revision action from independent review contracts."""
    if article_review.get("score", 0) < thresholds.get("article", 80):
        return "revise_writing"
    if viral_review and viral_review.get("score", 0) < viral_review.get("threshold", thresholds.get("viral", 78)):
        return "revise_writing"
    if visual_review.get("score", 0) < thresholds.get("visual", 75):
        return "revise_visuals"
    return "pass"
