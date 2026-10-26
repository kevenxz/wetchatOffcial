"""Visual spec model and image-prompt assembly.

The previous pipeline never described a picture. It concatenated an internal role
token, the topic, a wall of scraped prose and English boilerplate:

    cover for <topic>, clean composition, mobile readable, no watermark. Article
    section: 封面. Purpose: ... Use these article/data signals: <中文原文> ...

This module holds the replacement contract: a model-authored, concrete *visual*
description that is assembled into a short single-language prompt.

Pure functions only — the model call lives in `workflow.agents.visual_describer`.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from workflow.utils.image_styles import (
    TEXT_EXCLUSION_CLAUSE,
    build_style_clause,
    forbidden_concepts_in,
    get_preset,
    resolve_style_id,
)

# Phrases from the old implementation that are known to invite text, watermarks and
# fake UI back into the picture. They must never reappear in an assembled prompt.
HISTORICAL_TRIGGER_PHRASES: tuple[str, ...] = (
    "no watermark",
    "no fake ui screenshots",
    "unreadable small text",
    "mobile readable",
    "clean composition",
    "clear diagrams",
    "use these article/data signals",
)

# Absolute ceiling regardless of configuration; image models degrade past this.
HARD_PROMPT_LIMIT = 900

DEFAULT_MAX_PROMPT_CHARS = 400
MIN_PROMPT_CHARS = 120
MAX_PROMPT_CHARS = 900


def resolve_prompt_settings(image_policy: dict[str, Any]) -> tuple[str, int]:
    """Resolve (style_id, max_prompt_chars) from the image policy.

    Lives here rather than in the agent module so both the describer and the generator
    can use it without a tools→agents dependency.
    """
    style_id = resolve_style_id(str(image_policy.get("style_preset") or ""), None)
    requested = int(image_policy.get("prompt_max_chars") or DEFAULT_MAX_PROMPT_CHARS)
    return style_id, max(MIN_PROMPT_CHARS, min(requested, MAX_PROMPT_CHARS))


class VisualSpec(BaseModel):
    """A concrete, text-free description of one picture."""

    asset_index: int = Field(
        default=0,
        description="1-based index echoed from the request, used to map the spec back to its brief",
    )
    role: str = Field(default="", description="Asset role this spec belongs to")
    subject: str = Field(
        default="",
        description="The main concrete object or scene. Physical nouns only; never an abstract concept.",
    )
    setting: str = Field(
        default="",
        description="Environment, materials, light direction, camera angle.",
    )
    composition: str = Field(
        default="",
        description="Where the subject sits, negative space, and any headline safe area.",
    )
    section_link: str = Field(
        default="",
        description="How this picture relates to the argument of its article section (audit trail).",
    )

    def is_usable(self) -> bool:
        """A spec is usable when it actually describes something concrete."""
        return bool(self.subject.strip()) and not forbidden_concepts_in(
            f"{self.subject} {self.setting} {self.composition}"
        )


class VisualSpecBatch(BaseModel):
    """One structured call covers every asset, keeping the styling coherent."""

    items: list[VisualSpec] = Field(default_factory=list)


def _sentence(value: str) -> str:
    cleaned = " ".join(str(value or "").split()).strip()
    if not cleaned:
        return ""
    return cleaned if cleaned.endswith((".", "!", "?")) else f"{cleaned}."


# Topic keyword -> physical scene. Checked in order, so put the most specific first.
#
# Why a table instead of one generic scene: the previous fallback took *only* the role, so
# every article in the system received the same picture. Two unrelated real tasks — one about
# an Anthropic IPO, one about 微信 and 红果 — produced byte-identical specs
# ("A quiet workstation at night: an open laptop, a paper notebook and a cooling mug").
# At least the fallback should follow the subject matter.
#
# This is a mitigation, not a substitute for a working model: it cannot read the article's
# argument, only its broad category. Runs that use it stay flagged as degraded.
_SCENE_HINTS: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (
        ("芯片", "半导体", "算力", "服务器", "数据中心", "云计算", "模型", "人工智能", "ai", "大模型", "算法"),
        "A rack of server hardware in a cold aisle, indicator lights along the front panels",
        "Grey equipment cabinets, cool overhead lighting, cables routed along the top",
    ),
    (
        ("融资", "上市", "ipo", "股价", "估值", "财报", "营收", "投资", "基金", "债券", "汇率", "美联储"),
        "A newspaper financial page and a pair of reading glasses on a dark trading desk",
        "Deep-shadowed office at dusk, single desk lamp, out-of-focus screens behind",
    ),
    (
        ("汽车", "新能源", "电池", "充电", "车企", "车型", "智驾", "自动驾驶"),
        "A parked electric car in an empty concrete car park, charging cable coiled beside it",
        "Cold concrete surfaces, overhead strip lighting, wide empty space around the car",
    ),
    (
        ("地震", "洪水", "台风", "救援", "灾害", "火灾", "事故", "应急"),
        "Rescue equipment laid out on the ground: rope, gloves, a folded blanket and a torch",
        "Overcast outdoor light, damp ground, blurred debris in the far background",
    ),
    (
        ("体育", "比赛", "联赛", "球队", "奥运", "国乒", "夺冠", "赛季"),
        "An empty stadium seating block and a folded team bench seen from the touchline",
        "Late afternoon light across the pitch, long shadows, distant floodlight masts",
    ),
    (
        ("监管", "政策", "法律", "合规", "诉讼", "反垄断", "标准", "法规"),
        "A wooden desk with a stack of bound documents, a stamp pad and a pen",
        "Quiet institutional room, soft window light from the left, plain walls",
    ),
    (
        ("手机", "应用", "平台", "产品", "用户", "社交", "电商", "视频", "直播", "游戏"),
        "Everyday devices arranged on a plain desk: a phone, headphones and a notebook",
        "Bright neutral workspace, soft diffused daylight, clean uncluttered surface",
    ),
)

# Used when nothing matches. Several variants so two unmatched articles still differ.
_GENERIC_SCENES: tuple[tuple[str, str], ...] = (
    (
        "An empty modern office at dusk: a desk, an unlit monitor and a single chair",
        "Cool window light fading across a plain carpet, blurred partition walls behind",
    ),
    (
        "A city street corner in light rain, wet asphalt reflecting a lone street lamp",
        "Dusk with low contrast, shallow depth of field, buildings dissolving out of focus",
    ),
    (
        "A stack of printed papers and a ceramic cup on a bare concrete table",
        "Soft overhead light, plain wall behind, restrained and empty around the subject",
    ),
    (
        "A window seat with a closed notebook and a pair of glasses on the sill",
        "Overcast daylight through the glass, quiet room, nothing else in frame",
    ),
)


def _match_scene(text: str) -> tuple[str, str] | None:
    lowered = str(text or "").lower()
    for keywords, subject, setting in _SCENE_HINTS:
        if any(keyword in lowered for keyword in keywords):
            return subject, setting
    return None


def _generic_scene(seed: str) -> tuple[str, str]:
    """Deterministic pick so different articles do not collide on one picture."""
    index = sum(ord(char) for char in seed) % len(_GENERIC_SCENES)
    return _GENERIC_SCENES[index]


def build_fallback_spec(
    role: str,
    *,
    topic: str = "",
    section: str = "",
    claim: str = "",
) -> VisualSpec:
    """A safe, text-free spec used when no model is available or the call failed.

    When the caller passes the article context the scene follows the subject matter, so two
    different articles no longer receive the identical picture. It still cannot read the
    article's argument, so callers must keep marking the run as degraded and require review.

    The returned spec must pass :meth:`VisualSpec.is_usable`, so every scene above is written
    to avoid :data:`~workflow.utils.image_styles.FORBIDDEN_SUBJECT_CONCEPTS` (notably the
    words "text", "title", "chart", "graph" and "ui").
    """
    if role == "cover":
        composition = (
            "Subject placed slightly off-centre with generous empty space across the top third "
            "for a headline overlay"
        )
    else:
        composition = "Subject filling the lower two thirds, soft empty space above"

    anchor = f"{topic} {section} {claim}".strip()
    matched = _match_scene(anchor)
    if matched:
        subject, setting = matched
        link = f"Fallback visual chosen for the article's subject area ({section or 'cover'})"
    else:
        subject, setting = _generic_scene(anchor or role)
        link = "Fallback visual: no article-aware description was produced"

    return VisualSpec(
        role=role,
        subject=subject,
        setting=setting,
        composition=composition,
        section_link=link,
    )


def assemble_image_prompt(
    *,
    spec: VisualSpec,
    style_id: str | None,
    role: str,
    brand_colors: list[str] | None = None,
    max_chars: int = 400,
    allow_text: bool = False,
) -> str:
    """Assemble the final, short image prompt.

    Structure — style, subject, setting, composition, one exclusion clause. If the
    budget is exceeded the least important segment is dropped first, and the style and
    exclusion clauses are always kept because they carry the look and the text ban.

    ``allow_text`` reflects the operator's explicit opt-in. Left off (the default) the
    prompt bans text outright; that ban is the reason the pictures stopped coming back
    as posters full of garbled Chinese.
    """
    style_clause = build_style_clause(style_id, role, brand_colors)
    segments = [
        ("style", style_clause),
        ("subject", spec.subject),
        ("setting", spec.setting),
        ("composition", spec.composition),
    ]

    budget = max(120, min(int(max_chars or 400), HARD_PROMPT_LIMIT))

    def render(chosen: list[tuple[str, str]]) -> str:
        parts = [_sentence(value) for _, value in chosen if str(value or "").strip()]
        if not allow_text:
            parts.append(TEXT_EXCLUSION_CLAUSE)
        return " ".join(part for part in parts if part).strip()

    chosen = list(segments)
    prompt = render(chosen)
    # Shed the least content-bearing segments first, never the style clause.
    for drop_key in ("composition", "setting"):
        if len(prompt) <= budget:
            break
        chosen = [item for item in chosen if item[0] != drop_key]
        prompt = render(chosen)

    if len(prompt) > budget:
        # Last resort: shrink the style clause, which is a fixed preset string. The
        # subject carries the actual content and the exclusion clause carries the text
        # ban, so both must survive intact.
        subject_part = _sentence(spec.subject)
        tail = "" if allow_text else TEXT_EXCLUSION_CLAUSE
        reserved = len(subject_part) + len(tail) + 2
        style_budget = budget - reserved
        style_part = _clip_style(style_clause, style_budget) if style_budget > 0 else ""
        prompt = " ".join(part for part in (style_part, subject_part, tail) if part.strip()).strip()

    return prompt


def _clip_style(style_clause: str, budget: int) -> str:
    """Trim a style clause on a comma boundary so it stays readable."""
    if budget <= 0:
        return ""
    if len(style_clause) <= budget:
        return _sentence(style_clause)
    head = style_clause[:budget]
    boundary = head.rfind(",")
    if boundary >= budget // 2:
        head = head[:boundary]
    return _sentence(head.rstrip(" ,;")) if head.strip(" ,;") else ""


def prompt_violations(prompt: str, allow_text: bool = False) -> list[str]:
    """Return the reasons a prompt is not acceptable, for tests and runtime guards."""
    violations: list[str] = []
    lowered = str(prompt or "").lower()

    for phrase in HISTORICAL_TRIGGER_PHRASES:
        # The single exclusion clause legitimately mentions text/logos/watermarks, so
        # only the *other* historical phrasings are rejected here.
        if phrase in lowered:
            violations.append(f"historical_trigger_phrase:{phrase}")

    if not lowered.strip():
        violations.append("empty")
    if not allow_text and TEXT_EXCLUSION_CLAUSE.lower() not in lowered:
        violations.append("missing_text_exclusion")

    return violations


def describe_spec(spec: VisualSpec) -> dict[str, Any]:
    """Serialise a spec for state/UI, flagging whether it is model-authored."""
    return {
        "asset_index": spec.asset_index,
        "role": spec.role,
        "subject": spec.subject,
        "setting": spec.setting,
        "composition": spec.composition,
        "section_link": spec.section_link,
        "usable": spec.is_usable(),
    }


def resolved_preset_name(style_id: str | None, role: str) -> str:
    return str(get_preset(resolve_style_id(style_id, role)).get("name") or "")
