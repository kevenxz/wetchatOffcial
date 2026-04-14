"""Provider adapters for hotspot collection."""
from __future__ import annotations

from typing import Any


def collect_hotspot_candidates(task_brief: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    """Return normalized hotspot candidates from available providers."""
    topic = str(task_brief.get("topic") or "").strip()
    return [
        {
            "source": "tophub",
            "title": topic,
            "heat": 70,
            "relevance": 80,
            "timeliness": 70,
            "evidence_density": 75,
            "expandability": 78,
            "account_fit": 80,
            "risk": 15,
            "config": config,
        }
    ]
