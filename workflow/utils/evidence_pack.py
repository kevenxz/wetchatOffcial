"""Evidence normalization helpers for planner-led workflow."""
from __future__ import annotations

from typing import Any


def build_evidence_pack(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group evidence items by downstream usage."""
    return {
        "confirmed_facts": [item for item in items if item.get("angle") == "fact"],
        "caution_items": [item for item in items if item.get("needs_caution")],
        "usable_data_points": [item for item in items if item.get("angle") == "data"],
        "usable_cases": [item for item in items if item.get("angle") == "case"],
        "risk_points": [item for item in items if item.get("angle") == "opinion"],
        "actionable_takeaways": [],
        "research_gaps": [],
    }
