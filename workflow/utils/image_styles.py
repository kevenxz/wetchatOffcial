"""Image style presets.

Replaces the English `visual_style` blurb that used to be concatenated onto the tail of
the image prompt. That string came from `article_skills.py` and contradicted itself
("clear diagrams first" while also "avoid exaggerated sci-fi posters"), landed after
600+ characters of noise, and — worst of all — asked the model to draw *diagrams*,
which is a request for text.

A preset supplies exactly one positive `style_clause` describing how the photograph
should look. Nothing else from here is concatenated into the prompt.

IMPORTANT — why `avoid` is never pasted into the prompt
-------------------------------------------------------
Image models are strongly primed by the concepts named in a prompt. The previous
implementation appended ``no unreadable small text``, ``no watermark`` and
``no fake UI screenshots`` to the *positive* prompt, which is a reliable way to get
text, watermarks and fake UI back. `avoid` therefore exists for:
  * local validation (rejecting a visual spec that asks for text or charts), and
  * a provider negative-prompt field, if one is ever available.

The only exclusion that reaches the prompt is the single short clause in
``TEXT_EXCLUSION_CLAUSE``, which empirical practice shows is worth keeping once.
"""
from __future__ import annotations

import re
from typing import Any

# The one and only text-exclusion sentence allowed in a prompt.
TEXT_EXCLUSION_CLAUSE = (
    "No text, letters, numbers, logos, or watermarks anywhere in the image."
)

# Concepts that must never be requested in a visual spec; used for validation only.
FORBIDDEN_SUBJECT_CONCEPTS = (
    "infographic",
    "chart",
    "diagram",
    "graph",
    "poster",
    "screenshot",
    "ui",
    "dashboard",
    "logo",
    "watermark",
    "text",
    "caption",
    "title",
)

DEFAULT_STYLE_ID = "editorial_photo"

PRESETS: dict[str, dict[str, Any]] = {
    "editorial_photo": {
        "style_id": "editorial_photo",
        "name": "编辑部摄影感",
        "description": "真实场景与物件、自然布光、浅景深、克制冷调，无人脸特写。",
        "style_clause": (
            "Editorial photograph, real physical scene, natural soft directional lighting, "
            "shallow depth of field, muted cool colour grading, restrained and understated, "
            "shot on a 35mm lens, no people's faces in close-up"
        ),
        "default_palette": ["#0f172a", "#334155", "#94a3b8", "#e2e8f0"],
        "avoid": list(FORBIDDEN_SUBJECT_CONCEPTS),
    },
    "concept_illustration": {
        "style_id": "concept_illustration",
        "name": "概念插画",
        "description": "扁平矢量插画，用隐喻表达概念，配色干净。",
        "style_clause": (
            "Flat vector conceptual illustration, single clear metaphor, limited clean palette, "
            "geometric shapes, generous negative space, editorial magazine illustration"
        ),
        "default_palette": ["#0f766e", "#14b8a6", "#0f172a", "#f4f4f5"],
        "avoid": list(FORBIDDEN_SUBJECT_CONCEPTS),
    },
    "minimal_geometric": {
        "style_id": "minimal_geometric",
        "name": "极简几何",
        "description": "抽象几何、大留白，与产品界面的瑞士视觉一致。",
        "style_clause": (
            "Minimal abstract geometric composition, large negative space, precise alignment, "
            "one accent colour, subtle paper texture, Swiss graphic design sensibility"
        ),
        "default_palette": ["#0a0a0a", "#a1a1aa", "#e4e4e7", "#0f766e"],
        "avoid": list(FORBIDDEN_SUBJECT_CONCEPTS),
    },
}

# Per-role default, so a cover and its inline illustrations stay coherent.
ROLE_DEFAULT_STYLE: dict[str, str] = {
    "cover": "editorial_photo",
    "contextual_illustration": "editorial_photo",
    "data_scene": "editorial_photo",
    "infographic": "editorial_photo",
    "comparison_graphic": "editorial_photo",
}

STYLE_IDS = tuple(PRESETS)


def list_image_styles() -> list[dict[str, Any]]:
    """Return the preset catalogue for API/UI consumers."""
    return [
        {
            "style_id": preset["style_id"],
            "name": preset["name"],
            "description": preset["description"],
            "default_palette": list(preset["default_palette"]),
        }
        for preset in PRESETS.values()
    ]


def resolve_style_id(style_id: str | None, role: str | None = None) -> str:
    """Resolve a preset id, falling back to the role default then the global default."""
    requested = str(style_id or "").strip()
    if requested in PRESETS:
        return requested
    return ROLE_DEFAULT_STYLE.get(str(role or "").strip(), DEFAULT_STYLE_ID)


def get_preset(style_id: str | None, role: str | None = None) -> dict[str, Any]:
    """Return the resolved preset as a copy."""
    return dict(PRESETS[resolve_style_id(style_id, role)])


def build_style_clause(style_id: str | None, role: str | None = None, brand_colors: list[str] | None = None) -> str:
    """Build the positive style sentence for a prompt.

    Brand colours are folded in as a palette hint only; they never add nouns that
    could be drawn as text.
    """
    preset = get_preset(style_id, role)
    colors = [str(color).strip() for color in (brand_colors or []) if str(color).strip()]
    palette = colors or list(preset.get("default_palette") or [])
    clause = str(preset.get("style_clause") or "").strip()
    if palette:
        clause = f"{clause}. Colour palette: {', '.join(palette[:4])}"
    return clause


def forbidden_concepts_in(text: str) -> list[str]:
    """Return the forbidden concepts mentioned in a piece of text.

    Used to reject a visual spec that asks for a chart, a poster, a UI screenshot or
    anything else that would come back full of text.

    Matched on word boundaries, not as substrings. Substring matching is a trap here:
    "photograph" contains "graph", "quiet" and "equipment" contain "ui", and "texture"
    contains "text" — a plain ``in`` check would reject nearly every valid spec.
    """
    lowered = str(text or "").lower()
    return [concept for concept in FORBIDDEN_SUBJECT_CONCEPTS if _CONCEPT_PATTERNS[concept].search(lowered)]


# Built once at import; `s?` allows the plural forms that appear in real prompts.
_CONCEPT_PATTERNS: dict[str, re.Pattern[str]] = {
    concept: re.compile(rf"\b{re.escape(concept)}s?\b") for concept in FORBIDDEN_SUBJECT_CONCEPTS
}
