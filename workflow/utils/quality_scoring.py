"""Quality decision helpers for the redesigned workflow."""
from __future__ import annotations

from typing import Any


def decide_quality_action(
    article_review: dict[str, Any],
    visual_review: dict[str, Any],
    thresholds: dict[str, int],
) -> str:
    """Choose the next revision action from article and visual review scores."""
    if article_review.get("score", 0) < thresholds.get("article", 80):
        return "revise_writing"
    if visual_review.get("score", 0) < thresholds.get("visual", 75):
        return "revise_visuals"
    return "pass"
