"""Helpers for role-aware visual brief construction.

A brief is now purely **structural**: which asset, in which section, at which size, plus
the cleaned inputs the visual describer needs. It no longer carries a `compressed_prompt`
— the old one was ``f"{role} for {topic}, clean composition, mobile readable, no
watermark"``, i.e. an internal role token used as the subject of the sentence, which the
image model dutifully drew as an "infographic" full of text.

`workflow.agents.visual_describer` authors the real prompt from a model-written visual
spec. `generate_visual_assets_node` still guards against a brief that somehow arrives
without a prompt, so an empty prompt can never be sent to the provider.
"""
from __future__ import annotations

from typing import Any

# Aspect ratio per role. `provider_size` is what the image API is actually called with;
# only the cover uses a wide canvas, everything else stays square because that is what
# the configured provider accepts today.
_ROLE_ASPECT: dict[str, str] = {
    "cover": "2.35:1",
    "contextual_illustration": "16:9",
    "data_scene": "4:5",
    # Legacy role names, kept so already-persisted briefs keep rendering.
    "infographic": "4:5",
    "comparison_graphic": "1:1",
}

_DEFAULT_ASPECT = "16:9"


def build_visual_brief(role: str, draft: dict[str, Any], topic: str) -> dict[str, Any]:
    """Create a structural visual brief for a target asset role."""
    aspect_ratio = _ROLE_ASPECT.get(role, _DEFAULT_ASPECT)
    return {
        "role": role,
        "topic": topic,
        "title": draft.get("title", ""),
        "target_aspect_ratio": aspect_ratio,
        "provider_size": "1536x1024" if aspect_ratio == "2.35:1" else "1024x1024",
    }
