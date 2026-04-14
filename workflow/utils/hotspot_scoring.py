"""Shared scoring logic for hotspot opportunities."""
from __future__ import annotations

from typing import Any


def score_hotspot_candidate(candidate: dict[str, Any]) -> float:
    """Score a hotspot candidate with weighted relevance and risk penalty."""
    positive = (
        candidate.get("heat", 0) * 0.18
        + candidate.get("relevance", 0) * 0.24
        + candidate.get("timeliness", 0) * 0.14
        + candidate.get("evidence_density", 0) * 0.14
        + candidate.get("expandability", 0) * 0.16
        + candidate.get("account_fit", 0) * 0.14
    )
    risk_penalty = candidate.get("risk", 0) * 0.15
    return round(max(0.0, positive - risk_penalty), 2)
