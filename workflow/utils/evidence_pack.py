"""Evidence normalization helpers for planner-led workflow."""
from __future__ import annotations

from typing import Any


def _count_by_key(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key) or "unknown").strip() or "unknown"
        counts[value] = counts.get(value, 0) + 1
    return counts


def build_evidence_pack(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group evidence items by downstream usage."""
    high_confidence_items = [
        item for item in items if float(item.get("evidence_score") or 0) >= 0.75 and not item.get("needs_caution")
    ]
    caution_items = [item for item in items if item.get("needs_caution")]
    research_gaps: list[str] = []
    if not any(item.get("angle") == "data" for item in items):
        research_gaps.append("missing_data_evidence")
    if not any(item.get("angle") == "fact" and float(item.get("evidence_score") or 0) >= 0.75 for item in items):
        research_gaps.append("missing_high_confidence_fact")

    return {
        "confirmed_facts": [item for item in items if item.get("angle") == "fact"],
        "caution_items": caution_items,
        "usable_data_points": [item for item in items if item.get("angle") == "data"],
        "usable_cases": [item for item in items if item.get("angle") == "case"],
        "risk_points": [item for item in items if item.get("angle") == "opinion"],
        "actionable_takeaways": [],
        "research_gaps": research_gaps,
        "quality_summary": {
            "total_items": len(items),
            "high_confidence_items": len(high_confidence_items),
            "caution_items": len(caution_items),
            "source_coverage": _count_by_key(items, "source_type"),
            "angle_coverage": _count_by_key(items, "angle"),
        },
    }
