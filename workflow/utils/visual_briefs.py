"""Helpers for role-aware visual brief generation."""
from __future__ import annotations

from typing import Any


def build_visual_brief(role: str, draft: dict[str, Any], topic: str) -> dict[str, Any]:
    """Create a concise visual brief for a target asset role."""
    aspect_ratio = {
        "cover": "2.35:1",
        "contextual_illustration": "16:9",
        "infographic": "4:5",
        "comparison_graphic": "1:1",
    }.get(role, "16:9")
    return {
        "role": role,
        "topic": topic,
        "title": draft.get("title", ""),
        "compressed_prompt": f"{role} for {topic}, clean composition, mobile readable, no watermark",
        "target_aspect_ratio": aspect_ratio,
        "provider_size": "1536x1024" if aspect_ratio == "2.35:1" else "1024x1024",
    }
