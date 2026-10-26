"""Build the dynamic article blueprint from task brief and article type."""
from __future__ import annotations

import json
import re
from typing import Any

import structlog
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field, field_validator, model_validator

from workflow.model_factory import invoke_structured, model_context as stage_context, structured_chain
from workflow.model_logging import log_model_request, log_model_response
from workflow.state import WorkflowState
from workflow.utils.headings import subject_from_claim

logger = structlog.get_logger(__name__)


def _coerce_str_list(value: Any) -> list[str]:
    """Accept a string, a list, or a scalar and return a clean list of strings.

    Exists because the planner naturally writes ``key_evidence`` as a *list* of evidence
    lines and ``supporting_sources`` as a list of source ids. The schema used to demand
    ``str`` for both, so a perfectly good blueprint failed validation with nine type
    errors and the entire adaptive structure was discarded for the fixed fallback.
    """
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _coerce_mapping_list(value: Any) -> list[dict[str, Any]]:
    """Accept a list of dicts, a single dict, or loose rows and return list[dict]."""
    if value is None:
        return []
    if isinstance(value, dict):
        return [dict(value)]
    if not isinstance(value, (list, tuple)):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def clamp_type_label(text: str, limit: int = 12) -> str:
    """Reduce a model-written article type to a short label.

    Asked to name the type in its own words, a model sometimes answers with a whole
    title: ``事件复盘：从一座百年市政厅被烧看法国骚乱的象征冲突与秩序风险``. That is a
    headline, not a type, and it breaks any grouping by type. There is no preset enum —
    the label is still the model's own choice, just kept short.
    """
    cleaned = " ".join(str(text or "").split()).strip(" -—:：。")
    if not cleaned:
        return ""
    for marker in ("：", ":", "，", ",", "；", ";", "。", "——", "---", "(", "（"):
        head = cleaned.split(marker, 1)[0].strip()
        if 2 <= len(head) <= limit:
            return head
    if len(cleaned) <= limit:
        return cleaned
    clipped = cleaned[:limit]
    for marker in ("：", ":", "，", ",", "、"):
        cut = clipped.rfind(marker)
        if cut >= 2:
            return clipped[:cut].strip()
    return clipped.strip()


class BlueprintOutput(BaseModel):
    """Structured article blueprint payload.

    Only ``thesis`` is required, and it is recovered from a sibling field when absent
    (see the validator). Before this, a single missing field was enough to discard the
    whole blueprint: several real runs produced a genuinely story-specific structure and
    it was thrown away because one key was absent.
    """

    model_config = {"extra": "allow"}

    article_type: str = Field(
        default="",
        description=(
            "Short label for the article type the planner itself decided on, e.g. 事件复盘, "
            "政策解读, 案例分析. A label, not a title."
        ),
    )
    article_type_reason: str = Field(
        default="", description="Why this type fits this particular story"
    )
    structure_rationale: str = Field(
        default="", description="Why this section order was chosen, in one or two sentences"
    )
    framework: str = Field(default="", description="Optional narrative hypothesis, never a mandatory template")
    structure_mode: str = Field(default="adaptive", description="adaptive by default; structure follows the material")
    title_candidates: list[str] = Field(default_factory=list, description="Publication-ready title candidates")
    thesis: str = Field(default="", description="Core thesis of the article")
    reader_value: str = Field(default="", description="Why the reader should care")
    central_question: str = Field(default="", description="The single question the article must answer")
    opening_move: str = Field(default="", description="How the opening creates relevance or tension")
    narrative_arc: str = Field(default="", description="The intended movement of the argument, not a section template")
    ending_move: str = Field(default="", description="How the ending resolves the thesis and points forward")
    sections: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Candidate narrative beats; the writer may merge, reorder, rename, or omit them",
    )
    must_cover_points: list[str] = Field(default_factory=list, description="Points that must be covered")
    drop_points: list[str] = Field(default_factory=list, description="Points intentionally left out")
    source_driven_framework: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Search-result-backed narrative signals, not a required section sequence",
    )
    evidence_map: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Mapping from planned sections to source claims",
    )

    @field_validator("article_type", mode="before")
    @classmethod
    def _normalize_type_label(cls, value: Any) -> Any:
        """Keep `article_type` a label rather than a headline."""
        return clamp_type_label(str(value or ""))

    @model_validator(mode="after")
    def _thesis_from_alternatives(self) -> BlueprintOutput:
        """Never lose a whole blueprint because `thesis` arrived under another name.

        Runs after validation because field order matters: ``thesis`` is declared before
        ``central_question``, so a field-level validator would not see the alternatives.
        """
        if str(self.thesis or "").strip():
            return self
        for candidate in (self.central_question, self.reader_value, self.framework, self.narrative_arc):
            if str(candidate or "").strip():
                self.thesis = str(candidate).strip()
                break
        return self

    @field_validator("must_cover_points", "drop_points", "title_candidates", mode="before")
    @classmethod
    def _coerce_string_lists(cls, value: Any) -> list[str]:
        return _coerce_str_list(value)

    @field_validator("sections", "source_driven_framework", "evidence_map", mode="before")
    @classmethod
    def _coerce_row_lists(cls, value: Any) -> list[dict[str, Any]]:
        return _coerce_mapping_list(value)


_HEADING_NOISE = re.compile(r"[#【】\[\]（）()“”\"']|\.{2,}|…+")
_TRUNCATED_TAIL = re.compile(r"(?:为何在此时发生|落地后的真实样子|仍待验证的部分|：发生了什么)$")


def _clean_heading(value: Any) -> str:
    heading = " ".join(str(value or "").replace("#", " ").split()).strip(" -—:：")
    if not heading or len(heading) > 42:
        return ""
    if re.search(r"(?:https?://|www\.|\.(?:com|cn|net|org)(?:/|$))", heading, flags=re.I):
        return ""
    if heading.endswith("...") or heading.endswith("……"):
        return ""
    return heading


def _heading_quality(heading: str) -> int:
    """Score a heading from the model; higher is better, <=0 means reject.

    Used to pick a usable H2 and to decide whether a *derived* heading is needed. The
    thresholds here are what stop truncated scraped text such as
    ``#法国骚乱商店餐馆被砸汽车被烧#】法国数十万人1为何在此时发生`` from becoming an H2.
    """
    text = str(heading or "").strip()
    if not text:
        return -100
    score = 0
    if _HEADING_NOISE.search(text):
        score -= 6
    if _TRUNCATED_TAIL.search(text):
        score -= 4
    # A heading cut mid-phrase usually ends without terminal punctuation but with a
    # dangling connective or an opening quote.
    if re.search(r"[，,、：:；;]$", text):
        score -= 3
    if text.count("，") >= 3:
        score -= 3
    if len(text) > 30:
        score -= 2
    # A long, comma-joined clause is prose, not a heading. Titles the model got right
    # are mostly under ~25 characters, so anything much longer is treated as suspect.
    if len(text) > 34:
        score -= 3
    if re.search(r"(?:\d{4}年|如何|为什么|为何|怎么|什么|哪些|谁)", text):
        score += 2
    if 6 <= len(text) <= 22:
        score += 2
    return score


def _clamp_heading(text: str, limit: int = 24) -> str:
    """Reduce a recovered sentence to a heading-sized phrase.

    Headings recovered from a section's ``purpose``/``goal`` arrive as full clauses such
    as ``复盘政府、内政部门与地方警力的应对方式``. Taken whole they read as a sentence, not
    an H2, so cut at the first structural break.
    """
    cleaned = " ".join(str(text or "").split()).strip(" -—:：。")
    if not cleaned:
        return ""
    if len(cleaned) <= limit:
        return cleaned
    for marker in ("，", "、", "：", ":", "；", ";", "。"):
        head = cleaned.split(marker, 1)[0].strip()
        if 5 <= len(head) <= limit:
            return head
    head = cleaned[:limit]
    cut = head.rfind("、")
    if cut >= 5:
        head = head[:cut]
    return head.strip(" -—:：。，、")


def _resolve_heading(section: dict[str, Any], fallback: str) -> str:
    """Prefer the model's heading when it is publication-worthy, else use the fallback."""
    for key in ("heading", "title", "heading_text"):
        candidate = _clean_heading(section.get(key))
        if candidate and _heading_quality(candidate) > 0:
            return candidate

    recovered = _recover_heading(section)
    if recovered:
        return recovered

    return _clean_heading(fallback)


def _recover_heading(section: dict[str, Any]) -> str:
    """Rebuild a heading from the section's own content when its title is unusable.

    Keeps a story-specific heading instead of falling back to a fixed, topic-anchored
    one, which is what made every article's section list look alike.
    """
    sources: list[str] = []
    for key in ("goal", "content", "purpose", "summary", "argument", "key_claim"):
        value = section.get(key)
        if isinstance(value, str) and value.strip():
            sources.append(value.strip())
        elif isinstance(value, (list, tuple)):
            sources.extend(str(item).strip() for item in value if str(item).strip())
    for key in ("key_evidence", "key_points", "evidence", "source_claims"):
        value = section.get(key)
        if isinstance(value, (list, tuple)):
            sources.extend(str(item).strip() for item in value if str(item).strip())
        elif isinstance(value, str) and value.strip():
            sources.append(value.strip())

    for source in sources:
        subject = subject_from_claim(source, limit=22)
        candidate = _clean_heading(_clamp_heading(subject or source))
        if candidate and _heading_quality(candidate) > 0:
            return candidate
    return ""


def _normalize_sections(sections: list[dict[str, Any]], topic: str = "") -> list[dict[str, Any]]:
    """Keep the planner's own sections, preserving any extra fields it provided.

    The previous version rebuilt every section as exactly ``{heading, goal, shape}``,
    discarding ``key_evidence`` and anything else the model wrote — which is also why the
    extra fields caused validation errors upstream.
    """
    focus = _topic_focus_phrase(topic) if topic else ""
    normalized: list[dict[str, Any]] = []
    used: set[str] = set()

    for index, section in enumerate(sections):
        if not isinstance(section, dict):
            continue
        fallback = f"{focus}相关进展" if focus else ""
        heading = _resolve_heading(section, fallback)
        if not heading:
            heading = fallback
        if not heading:
            continue
        if heading in used:
            recovered = _recover_heading(section)
            if recovered and recovered not in used:
                heading = recovered
            else:
                heading = f"{heading}（{index + 1}）"
        used.add(heading)

        goal = _section_goal(section)
        if not goal:
            goal = heading

        row: dict[str, Any] = dict(section)
        row["heading"] = heading
        row["goal"] = goal
        row["shape"] = str(section.get("shape") or section.get("beat") or "").strip()
        normalized.append(row)

    return normalized


def _section_goal(section: dict[str, Any]) -> str:
    """Extract a usable goal, accepting the several keys models actually use."""
    for key in ("goal", "content", "purpose", "summary", "argument", "key_claim"):
        value = section.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (list, tuple)):
            joined = "；".join(str(item).strip() for item in value if str(item).strip())
            if joined:
                return joined
    evidence = _coerce_str_list(section.get("key_evidence") or section.get("key_points"))
    if evidence:
        return "；".join(evidence[:2])
    return ""


def _normalize_blueprint_output(
    result: BlueprintOutput | dict[str, Any],
    topic: str = "",
) -> BlueprintOutput:
    if isinstance(result, BlueprintOutput):
        payload = result.model_dump()
    else:
        payload = dict(result)
    payload["sections"] = _normalize_sections(list(payload.get("sections") or []), topic=topic)
    payload["title_candidates"] = [
        str(item).strip()
        for item in list(payload.get("title_candidates") or [])
        if str(item).strip()
    ]
    return BlueprintOutput(**payload)


def _topic_profile(topic: str) -> str:
    lowered = topic.lower()
    if "融资" in topic or "funding" in lowered or "investment" in lowered:
        return "funding"
    if "出海" in topic or "overseas" in lowered or "global" in lowered:
        return "expansion"
    if "发布" in topic or "launch" in lowered or "product" in lowered:
        return "launch"
    return "general"


def _topic_focus_phrase(topic: str) -> str:
    cleaned = str(topic or "").strip("？?！!。,.， ")
    if not cleaned:
        return "这个变化"
    if "为什么" in cleaned:
        cleaned = cleaned.replace("为什么", "").strip("：:，, ")
    return cleaned or "这个变化"


def _clean_text(value: Any, limit: int = 90) -> str:
    cleaned = " ".join(str(value or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip("，,。.;；:： ") + "..."


def _build_fallback_title_candidates(topic: str, search_materials: list[dict[str, str]]) -> list[str]:
    """Build neutral fallback title candidates without clickbait phrasing."""
    cleaned_topic = str(topic or "").strip() or "未命名主题"
    candidates = [
        f"{cleaned_topic}：真正发生变化的是什么",
        f"重新理解{cleaned_topic}：事实、影响与未决问题",
        f"从公开证据看{cleaned_topic}",
    ]
    deduped: list[str] = []
    for candidate in candidates:
        cleaned = _clean_text(candidate, limit=42)
        if cleaned and cleaned not in deduped:
            deduped.append(cleaned)
    return deduped[:4]


def _material_claim(material: dict[str, Any]) -> str:
    for key in ("claim", "snippet", "title"):
        value = _clean_text(material.get(key), limit=110)
        if value:
            return value
    return ""


def _material_excerpt(material: dict[str, Any], limit: int = 400) -> str:
    """Trimmed excerpt used as material context.

    Kept deliberately small for searched pages: the prompt previously carried ~11k
    characters and pushed the model into truncating its structured output. The
    hotspot's own article gets a larger budget via ``_material_excerpt_limit``.
    """
    for key in ("text", "content", "summary", "claim", "snippet"):
        value = _clean_text(material.get(key), limit=limit)
        if value:
            return value
    return ""


def _material_excerpt_limit(angle: str) -> int:
    """Primary hotspot material is allowed a much larger excerpt."""
    return 3000 if str(angle or "").lower() == "hotspot_source" else 400


def _material_title(material: dict[str, Any]) -> str:
    """The source's real title, if it has one.

    Deliberately does not fall back to the claim: ``_material_claim`` already does
    that for display, and conflating the two made the claim text look like a source
    title, which then blocked legitimate claim-derived headings.
    """
    return _clean_text(material.get("title") or material.get("source_title"), limit=64)


def _dedupe_materials(
    items: list[dict[str, Any]],
    *,
    primary_limit: int = 2,
    secondary_limit: int = 6,
) -> list[dict[str, str]]:
    """Normalize and cap material, keeping hotspot sources ahead of searched pages."""
    materials: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        title = _material_title(item)
        claim = _material_claim(item)
        if not title and not claim:
            continue
        key = (title, claim)
        if key in seen:
            continue
        seen.add(key)
        angle = str(item.get("angle") or item.get("query_intent") or "fact").strip() or "fact"
        materials.append(
            {
                "angle": angle,
                "is_primary": angle.lower() == "hotspot_source",
                "query": str(item.get("query") or "").strip(),
                "title": title,
                "claim": claim,
                "excerpt": _material_excerpt(item, limit=_material_excerpt_limit(angle)),
                "source_type": str(item.get("source_type") or "unknown").strip(),
                "domain": str(item.get("domain") or "").strip(),
                "url": str(item.get("url") or "").strip(),
                "published_at": str(item.get("published_at") or item.get("date") or "").strip(),
            }
        )

    primary = [item for item in materials if item["is_primary"]][:primary_limit]
    secondary = [item for item in materials if not item["is_primary"]][:secondary_limit]
    return primary + secondary


def _collect_search_materials(research_state: dict[str, Any], evidence_pack: dict[str, Any]) -> list[dict[str, str]]:
    raw_items: list[dict[str, Any]] = []

    # The hotspot's own article is the primary material and must come first.
    for item in list(research_state.get("hotspot_sources") or []):
        if isinstance(item, dict):
            raw_items.append(
                {
                    **item,
                    "angle": "hotspot_source",
                    # Use the article body as the claim. Without this, _material_claim
                    # falls back to the title and a raw source title ends up as an H2.
                    "claim": _clean_text(item.get("text"), limit=220),
                }
            )

    raw_items.extend([dict(item) for item in list(research_state.get("evidence_items") or []) if isinstance(item, dict)])

    for label in ("confirmed_facts", "usable_data_points", "usable_cases", "risk_points"):
        for item in list(evidence_pack.get(label) or []):
            if isinstance(item, dict):
                raw_items.append({**item, "angle": item.get("angle") or label})

    for item in list(research_state.get("extracted_contents") or []):
        if not isinstance(item, dict):
            continue
        source_meta = dict(item.get("source_meta") or {})
        raw_items.append(
            {
                "angle": source_meta.get("query_intent") or source_meta.get("angle") or "fact",
                "query": source_meta.get("query"),
                "title": item.get("title"),
                "claim": item.get("text"),
                "snippet": source_meta.get("snippet"),
                "source_type": source_meta.get("source_type"),
                "domain": source_meta.get("domain"),
                "url": item.get("url"),
            }
        )

    for item in list(research_state.get("search_results") or []):
        if isinstance(item, dict):
            raw_items.append(item)

    return _dedupe_materials(raw_items)


def _shape_from_material(material: dict[str, str], index: int) -> str:
    angle = str(material.get("angle") or "").lower()
    source_type = str(material.get("source_type") or "").lower()
    if angle == "hotspot_source":
        return "event"
    if any(token in angle for token in ("risk", "caution", "counter", "opposing", "gap")):
        return "tension"
    if "case" in angle:
        return "case"
    if any(token in angle for token in ("data", "fact", "official", "confirmed")) or source_type in {
        "official", "dataset", "report", "paper", "research"
    }:
        return "evidence"
    if any(token in angle for token in ("analysis", "driver", "cause", "opinion", "news")) or source_type in {
        "news", "media", "analysis"
    }:
        return "drivers"
    if index == 0:
        return "evidence"
    return "drivers"


# Narrative jobs, in the order a WeChat article usually needs them. The heading is
# derived from the story's own claims (see _heading_from_claim) — these jobs only
# describe what the section must accomplish.
_NARRATIVE_JOBS: tuple[tuple[str, str, str], ...] = (
    ("event", "把这条消息本身讲清楚", "用热点原文交代发生了什么：关键动作、时间、参与方，并区分事实与转述。"),
    ("evidence", "可核验的数据与事实", "用可核验的事实说明这次变化具体体现在哪些指标或结果上。"),
    ("drivers", "变化为什么在此时出现", "解释事实之间的原因链条，并指出哪些只是同时发生而非因果。"),
    ("case", "把变化放进真实场景", "用具体案例说明影响如何发生，并交代案例能证明与不能证明什么。"),
    ("tension", "仍需验证的关键变量", "呈现相反信号、证据缺口与下一步验证条件，不制造虚假的确定性。"),
)

_JOB_BY_SHAPE = {shape: (goal, detail) for shape, goal, detail in _NARRATIVE_JOBS}


def _order_shapes(shapes: list[str], opener: str | None = None) -> list[str]:
    """Order narrative shapes by story logic instead of by the fixed job table.

    This is what stops every degraded article from sharing one skeleton. The fixed
    ``_NARRATIVE_JOBS`` order put ``evidence`` before ``drivers`` before ``tension`` for
    every story, so two unrelated news events came out structurally identical. Here the
    opener (facts or the event itself) leads, and the remaining beats follow the story's
    own dependency: what happened -> what it means -> why now -> concrete scenes -> what
    is still unproven.

    Shapes that did not exist in the original table keep their material ordering at the
    end, so nothing is silently dropped.
    """
    preferred: list[str] = []
    if opener:
        preferred.append(opener)
    for shape in ("event", "evidence", "interpretation", "drivers", "case", "consequence", "tension"):
        if shape in shapes and shape not in preferred:
            preferred.append(shape)
    for shape in shapes:
        if shape not in preferred:
            preferred.append(shape)
    return preferred


def _detect_opener(search_materials: list[dict[str, str]], primary_source: dict[str, Any]) -> str | None:
    """Choose the opening beat from the material itself.

    A hotspot with its own article leads with the event; otherwise a run that is rich in
    data leads with evidence; otherwise the story opens on interpretation.
    """
    if str(primary_source.get("text") or "").strip():
        return "event"
    angles = {str(item.get("angle") or "").lower() for item in search_materials}
    types = {str(item.get("source_type") or "").lower() for item in search_materials}
    if angles & {"data", "official", "fact"} or types & {"official", "dataset", "report", "paper", "research"}:
        return "evidence"
    return None


_SHAPE_HEADING_SUFFIX = {
    "event": "",
    "evidence": "",
    "drivers": "为何在此时发生",
    "case": "落地后的真实样子",
    "tension": "仍待验证的部分",
}


def _shape_heading_suffix(shape: str) -> str:
    """Suffix for a *derived* heading; only used when the claim itself is too thin."""
    return _SHAPE_HEADING_SUFFIX.get(shape, "")


def _subject_from_claim(claim: str, limit: int = 24) -> str:
    """Extract a short, story-specific subject phrase from one claim.

    Thin wrapper around the shared helper so the blueprint and the deterministic
    draft builder derive headings the same way.
    """
    return subject_from_claim(claim, limit=limit)


def _heading_from_claim(
    claim: str,
    shape: str,
    *,
    used: set[str],
    forbidden_subjects: set[str] | None = None,
) -> str:
    """Build a heading from the claim itself so headings differ per story.

    Returns an empty string when nothing usable can be derived, letting the caller
    fall back to a topic-anchored heading rather than a fixed placeholder.

    ``forbidden_subjects`` rejects headings that are just a raw source title: using
    a source's own title as an H2 is explicitly not allowed.
    """
    subject = _subject_from_claim(claim)
    if not subject:
        return ""
    if forbidden_subjects and subject.strip() in forbidden_subjects:
        return ""
    candidate = f"{subject}{_SHAPE_HEADING_SUFFIX.get(shape, '')}"
    if _clean_heading(candidate) and candidate not in used:
        return candidate
    if _clean_heading(subject) and subject not in used:
        return subject
    return ""


def _source_titles(search_materials: list[dict[str, Any]]) -> set[str]:
    """Raw source titles, which must never become section headings."""
    return {
        title.strip()
        for title in (_material_title(material) for material in search_materials)
        if title and len(title.strip()) >= 2
    }


def _build_source_driven_sections(
    topic: str,
    search_materials: list[dict[str, str]],
    opener: str | None = None,
) -> list[dict[str, str]]:
    """Cluster sources by narrative job and derive headings from the material.

    Section headings come from the strongest claim in each cluster, so two different
    stories produce different heading sets. The beat *order* also follows the material
    (see ``_order_shapes``) rather than the fixed job table, which is what previously
    made two unrelated stories come out with the same skeleton.
    """
    buckets: dict[str, list[str]] = {shape: [] for shape, _goal, _detail in _NARRATIVE_JOBS}
    for index, material in enumerate(search_materials):
        claim = _material_claim(material)
        if not claim:
            continue
        shape = _shape_from_material(material, index)
        if shape not in buckets:
            shape = "drivers"
        if claim not in buckets[shape]:
            buckets[shape].append(claim)

    titles = _source_titles(search_materials)
    focus = _topic_focus_phrase(topic)
    used: set[str] = set()
    sections: list[dict[str, str]] = []
    ordered = _order_shapes([shape for shape, claims in buckets.items() if claims], opener=opener)

    for shape in ordered:
        claims = buckets.get(shape) or []
        if not claims:
            continue
        job_goal, job_detail = _JOB_BY_SHAPE.get(shape, ("推进这一段叙事", "围绕素材展开这一段。"))

        heading = ""
        for claim in claims[:3]:
            heading = _heading_from_claim(claim, shape, used=used, forbidden_subjects=titles)
            if heading:
                break
        if not heading:
            # Last resort: still anchored to this topic, never a fixed placeholder.
            suffix = _shape_heading_suffix(shape)
            heading = f"{focus}：发生了什么" if shape == "event" else f"{focus}{suffix}"
            heading = _clean_heading(heading) or f"{focus}相关进展"
        if heading in used:
            continue
        used.add(heading)

        # Evidence is kept as a list so downstream image-prompt building can clean it,
        # and so the section carries structured data rather than one packed string.
        sections.append(
            {
                "heading": heading,
                "goal": f"{job_goal}。{job_detail}",
                "shape": shape,
                "key_evidence": claims[:2],
            }
        )
    return sections


def _primary_source(research_state: dict[str, Any]) -> dict[str, str]:
    """Return the fetched hotspot article, when one is available."""
    for item in list(research_state.get("hotspot_sources") or []):
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        return {
            "title": str(item.get("title") or "").strip(),
            "url": str(item.get("url") or "").strip(),
            "text": text,
            "source_type": str(item.get("source_type") or "hotspot_source").strip(),
        }
    return {}


def _build_primary_source_block(primary_source: dict[str, str], limit: int = 3000) -> str:
    """Prompt block for the hotspot's own article."""
    if not primary_source:
        return (
            "(none: the hotspot source article could not be fetched; "
            "plan from source_context only and say so in the risk boundary)"
        )
    return json.dumps(
        {
            "title": primary_source.get("title", ""),
            "url": primary_source.get("url", ""),
            "article_text": str(primary_source.get("text") or "")[:limit],
            "instruction": "Derive the narrative spine from this article first.",
        },
        ensure_ascii=False,
        indent=2,
    )


def _build_primary_source_sections(topic: str, primary_source: dict[str, str]) -> list[dict[str, str]]:
    """Derive narrative beats from the hotspot article's own paragraphs.

    This is the no-model path for "read the hotspot article first, then decide the
    structure": the beats follow the source article's own order instead of a fixed
    template, so different stories yield different outlines.
    """
    text = str(primary_source.get("text") or "").strip()
    if not text:
        return []

    paragraphs = [
        " ".join(block.split())
        for block in re.split(r"\n+", text)
        if len(" ".join(block.split())) >= 40
    ]
    if not paragraphs:
        return []

    used: set[str] = set()
    # The article's own title must never become a section heading.
    forbidden = {str(primary_source.get("title") or "").strip()} - {""}
    sections: list[dict[str, str]] = []
    for index, paragraph in enumerate(paragraphs[:5]):
        claim = _clean_text(paragraph, limit=140)
        shape = "event" if index == 0 else ("evidence" if index == 1 else "drivers")
        heading = _heading_from_claim(claim, shape, used=used, forbidden_subjects=forbidden)
        if not heading:
            continue
        used.add(heading)
        sections.append(
            {
                "heading": heading,
                "goal": f"来自热点原文：{claim}",
                "shape": shape,
            }
        )
    return sections


def _merge_sections(
    primary_sections: list[dict[str, str]],
    source_sections: list[dict[str, str]],
    limit: int = 6,
) -> list[dict[str, str]]:
    """Keep the primary-source beats first, then extend with search-derived beats."""
    merged = list(primary_sections[:limit])
    seen = {str(section.get("heading") or "") for section in merged}
    for section in source_sections:
        if len(merged) >= limit:
            break
        heading = str(section.get("heading") or "")
        if not heading or heading in seen:
            continue
        seen.add(heading)
        merged.append(section)
    return merged


def _build_dynamic_sections(
    topic: str,
    article_type: dict[str, Any],
    evidence_pack: dict[str, Any],
    search_materials: list[dict[str, str]],
    opener: str | None = None,
) -> list[dict[str, str]]:
    source_sections = _build_source_driven_sections(topic, search_materials, opener=opener)
    if source_sections:
        return source_sections

    def evidence_text(item: Any) -> str:
        if isinstance(item, dict):
            return _clean_text(item.get("claim") or item.get("fact") or item.get("title"), limit=30)
        return _clean_text(item, limit=30)

    sections: list[dict[str, str]] = []
    evidence_groups = (
        ("confirmed_facts", "fact", "已确认的变化"),
        ("usable_data_points", "evidence", "数字呈现的另一面"),
        ("usable_cases", "case", "一个具体样本"),
        ("risk_points", "tension", "仍未收束的矛盾"),
    )
    for key, shape, fallback_heading in evidence_groups:
        items = list(evidence_pack.get(key) or [])
        if not items:
            continue
        signal = evidence_text(items[0])
        sections.append(
            {
                "heading": signal or fallback_heading,
                "goal": f"围绕现有{key}展开这个叙事节点；可与其他节点合并、换序或省略。",
                "shape": shape,
            }
        )

    if not sections:
        sections.append(
            {
                "heading": f"目前能确认的{_topic_focus_phrase(topic)}",
                "goal": "只沿当前可验证信号展开，不为凑结构添加章节。",
                "shape": "open_question",
            }
        )
    return sections


def _build_evidence_map(sections: list[dict[str, str]], search_materials: list[dict[str, str]]) -> list[dict[str, str]]:
    evidence_map: list[dict[str, str]] = []
    for section_index, section in enumerate(sections):
        section_shape = str(section.get("shape") or "").strip()
        matched = [
            material
            for index, material in enumerate(search_materials)
            if _shape_from_material(material, index) == section_shape
        ]
        if not matched and section_index < len(search_materials):
            matched = [search_materials[section_index]]
        evidence_map.append(
            {
                "section_heading": section.get("heading", ""),
                "source_title": "；".join(item.get("title", "") for item in matched[:2] if item.get("title")),
                "source_claim": "；".join(item.get("claim", "") for item in matched[:2] if item.get("claim")),
                "source_url": next((item.get("url", "") for item in matched if item.get("url")), ""),
            }
        )
    return evidence_map


def _enforce_evidence_boundary_sections(blueprint: BlueprintOutput, evidence_pack: dict[str, Any]) -> BlueprintOutput:
    research_gaps = list(evidence_pack.get("research_gaps") or [])
    quality_summary = dict(evidence_pack.get("quality_summary") or {})
    source_coverage = dict(quality_summary.get("source_coverage") or {})
    needs_validation = bool(
        "missing_high_confidence_fact" in research_gaps
        or "missing_data_evidence" in research_gaps
        or (source_coverage and set(source_coverage).issubset({"community", "aggregator", "unknown"}))
    )
    if not needs_validation:
        return blueprint
    boundary_requirement = "对证据不足的判断使用条件化表达，并在相关位置说明验证边界"
    if boundary_requirement not in blueprint.must_cover_points:
        blueprint.must_cover_points.append(boundary_requirement)
    if "补齐官方或数据证据；无法补齐时删除对应强结论" not in blueprint.must_cover_points:
        blueprint.must_cover_points.append("补齐官方或数据证据；无法补齐时删除对应强结论")
    return blueprint


def _build_evidence_summary(evidence_pack: dict[str, Any]) -> str:
    lines: list[str] = []
    for label in ("confirmed_facts", "usable_data_points", "usable_cases", "risk_points"):
        items = list(evidence_pack.get(label) or [])
        if not items:
            continue
        claims = []
        for item in items[:4]:
            if isinstance(item, dict):
                claim = str(item.get("claim") or item.get("message") or item.get("title") or "").strip()
            else:
                claim = str(item or "").strip()
            if claim:
                claims.append(claim)
        if claims:
            lines.append(f"{label}: " + " | ".join(claims))
    for label in ("key_facts", "allowed_claims", "forbidden_claims", "citations"):
        items = list(evidence_pack.get(label) or [])
        values: list[str] = []
        for item in items[:5]:
            if isinstance(item, dict):
                values.append(str(item.get("fact") or item.get("title") or item.get("url") or "").strip())
            else:
                values.append(str(item).strip())
        values = [value for value in values if value]
        if values:
            lines.append(f"{label}: " + " | ".join(values))
    research_gaps = list(evidence_pack.get("research_gaps") or [])
    if research_gaps:
        lines.append("research_gaps: " + " | ".join(str(item).strip() for item in research_gaps if str(item).strip()))
    quality_summary = dict(evidence_pack.get("quality_summary") or {})
    if quality_summary:
        for key in ("high_confidence_items", "caution_items", "source_coverage", "angle_coverage"):
            value = quality_summary.get(key)
            if value in (None, "", [], {}):
                continue
            lines.append(f"{key}: {value}")
    return "\n".join(lines)


def _build_search_materials_summary(search_materials: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for index, item in enumerate(search_materials[:10], start=1):
        claim = item.get("claim") or item.get("title") or ""
        title = item.get("title") or ""
        source = item.get("domain") or item.get("source_type") or "unknown"
        angle = item.get("angle") or "fact"
        excerpt = item.get("excerpt") or claim
        url = item.get("url") or ""
        lines.append(
            f"{index}. [{angle}] {title} ({source})\n"
            f"   url: {url}\n"
            f"   source_signal: {claim}\n"
            f"   extracted_content: {excerpt}"
        )
    return "\n".join(lines)


def _build_source_context(search_materials: list[dict[str, str]], evidence_pack: dict[str, Any]) -> str:
    payload = {
        "instruction": (
            "Use these search and extraction results as the primary material for discovering the best narrative. "
            "Do not force every source into an H2, and do not create a structure before reading the sources."
        ),
        "sources": [
            {
                "index": index,
                "angle": item.get("angle", ""),
                "query": item.get("query", ""),
                "title": item.get("title", ""),
                "domain": item.get("domain", ""),
                "url": item.get("url", ""),
                "published_at": item.get("published_at", ""),
                "source_type": item.get("source_type", ""),
                "claim": item.get("claim", ""),
                "extracted_content": item.get("excerpt", ""),
            }
            for index, item in enumerate(search_materials[:12], start=1)
        ],
        "evidence_pack": {
            key: evidence_pack.get(key)
            for key in (
                "confirmed_facts",
                "usable_data_points",
                "usable_cases",
                "risk_points",
                "research_gaps",
                "quality_summary",
            )
            if evidence_pack.get(key)
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _build_fallback_blueprint(
    topic: str,
    article_type: dict[str, Any],
    evidence_pack: dict[str, Any],
    search_materials: list[dict[str, str]],
    selected_skill: dict[str, Any] | None = None,
    primary_source: dict[str, str] | None = None,
) -> BlueprintOutput:
    """Final fallback blueprint builder.

    Used only when no model is configured or the structured call failed. It is
    deliberately content-driven so a degraded run still produces a story-shaped
    outline rather than the same headings for every article — the beat order, the
    derived article type and the headings all come from this story's material.
    """
    selected_skill = dict(selected_skill or {})
    primary_source = dict(primary_source or {})
    opener = _detect_opener(search_materials, primary_source)
    profile = _topic_profile(topic)
    research_gaps = list(evidence_pack.get("research_gaps") or [])
    quality_summary = dict(evidence_pack.get("quality_summary") or {})
    source_coverage = dict(quality_summary.get("source_coverage") or {})
    skill_id = str(selected_skill.get("skill_id") or "")
    skill_name = str(selected_skill.get("name") or "").strip()
    skill_framework = str(selected_skill.get("framework") or "").strip()
    section_guidance = [
        str(item).strip()
        for item in list(selected_skill.get("section_guidance") or [])
        if str(item).strip()
    ]
    writing_constraints = [
        str(item).strip()
        for item in list(selected_skill.get("writing_constraints") or [])
        if str(item).strip()
    ]

    framework_map = {
        "funding": "融资趋势解读型",
        "expansion": "出海机会分析型",
        "launch": "产品发布解读型",
        "general": "搜索证据解读型",
    }
    reader_value_map = {
        "funding": "帮助读者判断这一轮融资热度的含金量",
        "expansion": "帮助读者判断出海机会和落地难点",
        "launch": "帮助读者判断新动作背后的真实价值",
        "general": "帮助读者快速建立主题判断框架",
    }
    thesis_map = {
        "funding": f"{topic}需要结合资金流向、估值分化和真实兑现能力来判断。",
        "expansion": f"{topic}需要放在需求、渠道和本地化落地条件里判断。",
        "launch": f"{topic}需要回到真实影响、使用场景和风险边界中判断。",
        "general": f"{topic}需要放回搜索证据里判断：哪些已经被证明，哪些仍只是信号。",
    }

    source_sections = _build_source_driven_sections(topic, search_materials, opener=opener)
    primary_sections = _build_primary_source_sections(topic, primary_source)

    if primary_sections:
        # The hotspot's own article leads; searched material only extends it.
        sections = _merge_sections(primary_sections, source_sections)
    elif source_sections:
        sections = list(source_sections)
    else:
        sections = _build_dynamic_sections(topic, article_type, evidence_pack, search_materials, opener=opener)

    if skill_id == "quantum_tech_explainer" and not any("工程指标" in section.get("heading", "") for section in sections):
        sections.append(
            {
                "heading": "关键进展看哪些工程指标",
                "goal": "围绕硬件、纠错、相干时间、保真度或通信链路拆解变化。",
                "shape": "evidence",
            }
        )

    if skill_id == "quantum_tech_explainer" and not source_sections:
        quantum_data = list(evidence_pack.get("usable_data_points") or [])
        if quantum_data:
            sections = [
                {
                    "heading": "工程指标透露了什么",
                    "goal": "从可验证工程指标出发组织叙事，是否扩展其他节点由素材决定。",
                    "shape": "evidence",
                }
            ]

    if not sections:
        sections = [
            {"heading": f"{topic}的核心事实", "goal": "先整理已知事实和搜索材料里的主要信号。", "shape": "hook"},
            {"heading": f"{topic}的影响路径", "goal": "说明它可能影响哪些对象、场景或行业环节。", "shape": "analysis"},
        ]

    framework = skill_framework or (f"{skill_name} · 微信公众号文章蓝图" if skill_name else framework_map[profile])
    title_candidates = _build_fallback_title_candidates(topic, search_materials)
    if skill_id == "quantum_tech_explainer":
        title_candidates = [
            f"{topic}：工程指标、应用前景与边界",
            f"{topic}的技术进展和验证条件",
            f"从公开证据看{topic}",
        ]
        thesis_map["general"] = f"{topic}需要同时看科学原理、工程指标和商业化边界。"
        reader_value_map["general"] = "帮助读者区分技术进展、工程门槛和产业化条件。"

    must_cover_points: list[str] = []
    if selected_skill.get("evidence_policy"):
        must_cover_points.append(str(selected_skill["evidence_policy"]))
    must_cover_points.extend(writing_constraints[:3])
    if "missing_high_confidence_fact" in research_gaps or "missing_data_evidence" in research_gaps:
        must_cover_points.append("补齐官方或数据证据")
    if source_coverage and set(source_coverage).issubset({"community", "aggregator", "unknown"}):
        must_cover_points.append("交代当前证据边界")

    drop_points = ["泛泛背景复述"] if profile in {"funding", "expansion"} else []
    if skill_id == "quantum_tech_explainer":
        drop_points.extend(["量子玄学化表达", "马上取代经典计算的夸张判断"])

    # The type and the spine are derived from this story's own material, so a degraded
    # run still reads as a story-shaped article instead of one fixed skeleton.
    derived_type = _derive_article_type(sections, primary_source, evidence_pack)
    shape_list = [str(section.get("shape") or "") for section in sections if section.get("shape")]
    rationale = _describe_structure(shape_list, derived_type, has_primary=bool(primary_source.get("text")))

    return BlueprintOutput(
        article_type=derived_type,
        article_type_reason=(
            "由素材结构自动推断（本次未走到模型规划阶段）："
            f"共 {len(sections)} 个叙事节点，按 { ' → '.join(shape_list) or '素材顺序' } 推进。"
        ),
        structure_rationale=rationale,
        framework=framework,
        title_candidates=title_candidates,
        thesis=thesis_map[profile],
        reader_value=reader_value_map[profile],
        central_question=f"围绕{topic}，目前最值得读者弄清楚的变化、影响和证据边界是什么？",
        opening_move=(
            "从热点原文交代的事件本身切入，先让读者看清发生了什么。"
            if primary_source.get("text")
            else "从一个已确认的变化、具体场景或认知冲突切入，在首屏给出中心判断和读者关联。"
        ),
        narrative_arc="沿着事实确认、原因解释、现实影响与未决变量自然推进；素材不足时合并或省略节点。",
        ending_move="回扣中心判断，给出下一步观察指标或可执行启示，不重复全文、不喊口号。",
        sections=sections,
        must_cover_points=list(dict.fromkeys(must_cover_points)),
        drop_points=list(dict.fromkeys(drop_points)),
        source_driven_framework=sections,
        evidence_map=_build_evidence_map(sections, search_materials),
    )


def _derive_article_type(
    sections: list[dict[str, Any]],
    primary_source: dict[str, Any],
    evidence_pack: dict[str, Any],
) -> str:
    """Name the article type from the structure the material produced.

    The planner is asked to name its own type (no preset enum), and this is the degraded
    equivalent so a fallback run still reports a type rather than leaving the field empty
    — which is what left ``article_type`` as ``None`` on every stored task.
    """
    shapes = {str(section.get("shape") or "") for section in sections}
    has_primary = bool(str(primary_source.get("text") or "").strip())
    data_points = list(evidence_pack.get("usable_data_points") or [])
    cases = list(evidence_pack.get("usable_cases") or [])

    if has_primary and "drivers" in shapes:
        return "事件复盘"
    if "case" in shapes or cases:
        return "案例分析"
    if data_points and "evidence" in shapes:
        return "数据解读"
    if has_primary:
        return "热点解读"
    if "drivers" in shapes and "tension" in shapes:
        return "深度分析"
    if "tension" in shapes:
        return "观点评论"
    return "主题解读"


def _describe_structure(shapes: list[str], article_type: str, *, has_primary: bool) -> str:
    """One-line account of why this section order was chosen."""
    if not shapes:
        return f"素材不足，按{article_type}的方式组织：先给事实，再给判断。"
    spine = " → ".join(shapes)
    lead = "以热点原文交代的事件开场" if has_primary else f"以{shapes[0]}类素材开场"
    return f"按{article_type}组织，{lead}，其后沿 {spine} 推进；素材不足的节点已省略。"


# Human override: a non-empty `requested_article_type` arrives from the task form and
# takes precedence over whatever the agent would decide.
_OVERRIDE_KEYS = ("requested_article_type", "article_type_override", "manual_article_type")


def _requested_type_override(state: WorkflowState) -> str:
    """Return an operator-specified article type, if one was set for this task."""
    brief = dict(state.get("task_brief") or {})
    snapshot = dict(state.get("config_snapshot") or {})
    # `intake` stores the generation config under "generation"; older/imported states
    # may carry it under "generation_config". Read both, then the snapshot as a fallback.
    generation = {
        **dict(snapshot.get("generation_config") or {}),
        **dict(snapshot.get("generation") or {}),
    }
    for source in (brief, generation, snapshot):
        for key in _OVERRIDE_KEYS:
            value = str(source.get(key) or "").strip()
            if value:
                return value
    return ""


def _apply_type_override(blueprint: BlueprintOutput, requested_type: str) -> BlueprintOutput:
    """Let an explicit operator choice win over the agent's own judgement."""
    if not requested_type:
        return blueprint
    blueprint.article_type = requested_type
    if not blueprint.article_type_reason:
        blueprint.article_type_reason = "由运营在创建任务时指定。"
    return blueprint


async def plan_article_angle_node(state: WorkflowState) -> dict[str, Any]:
    """Create a dynamic section plan for the current article."""
    planning_state = dict(state.get("planning_state") or {})
    article_type = dict(planning_state.get("article_type") or {})
    selected_skill = dict(planning_state.get("selected_skill") or {})
    selected_topic = dict(state.get("selected_topic") or {})
    topic = str(selected_topic.get("title") or state.get("task_brief", {}).get("topic", "")).strip()
    research_state = dict(state.get("research_state") or {})
    evidence_pack = dict(research_state.get("evidence_pack") or {})
    search_materials = _collect_search_materials(research_state, evidence_pack)
    primary_source = _primary_source(research_state)
    requested_type = _requested_type_override(state)

    blueprint_source = "llm"
    degraded_reason = ""

    override_clause = (
        f"The operator has explicitly chosen the article type: '{requested_type}'. "
        "Honour that choice for article_type, and design the section structure that this "
        "type requires for THESE sources. "
        if requested_type
        else "Decide the article type yourself from the material and name it in your own words in article_type "
        "(for example 事件复盘, 政策解读, 案例分析, 趋势展望, 观点评论, 工具评测, 人物故事, or any other label that fits). "
        "There is no fixed list to choose from and no default: the type must come from what the sources actually are. "
    )

    system_prompt = (
        "You are a planning agent for Chinese WeChat public account articles. "
        "Generate a dynamic article blueprint based on the actual source material, extracted page text, and evidence density. "
        + override_clause +
        "Read primary_source FIRST: it is the article the hotspot is actually about. Derive the narrative spine from what that "
        "article itself says and how it is organised (what happened, which figures or actions matter, what changes for the reader, "
        "what remains unresolved), then use source_context only to corroborate, add background, add data, or add opposing views. "
        "The output is a WeChat article blueprint, not a research report, not a search plan, and not a generic outline. "
        "You must decide the article framework, final title candidates, opening logic, and H2 subtitles from the material. "
        "The result should feel like a WeChat public account article structure planned by an experienced editor: readable, specific, and publication-ready. "
        "Section headings must be specific to THIS story. Two different stories must never share the same heading set. "
        "Never fall back on generic placeholder headings such as '先确认发生了什么' or '变化为什么会在此时出现'. "
        "A heading must be a complete, readable phrase: never a truncated fragment, never a raw source title, "
        "never scraped markup, hashtags, or trailing punctuation. "
        "Sections carry their own evidence: put the supporting lines in key_evidence as a list. "
        "You may decide whether H2 sections are needed at all, and freely choose their number, order, and shape. "
        "Different article types need genuinely different structures — a 政策解读 reads nothing like an 事件复盘, "
        "and neither reads like a 工具评测. Do not reuse one section order across types. "
        "Record why this structure fits this story in structure_rationale. "
        "The sections field contains candidate narrative beats, not a contract: the writer may merge, reorder, rename, replace, or omit them. "
        "Choose a scene-led, question-led, argument-led, chronological, contrast, list, or essay-like narrative only when it fits the material. "
        "If selected_skill is provided, use its expertise, tone, evidence policy, and forbidden patterns; its framework is inspiration, not a skeleton. "
        "Map claims to evidence, not sections to sources. A source may support several beats and a beat may use several sources. "
        "Cluster sources around claims; never create one section for each search result. "
        "Never use a raw source title, website name, URL, or truncated snippet as a section heading. "
        "Define one central_question plus opening_move, narrative_arc, and ending_move so the writer has a coherent editorial backbone. "
        "Three to five narrative beats often work for a medium article, but this is guidance rather than a required count. "
        "Do not output a fixed template."
    )
    human_prompt = (
        "topic:\n{topic}\n\n"
        "article_type:\n{article_type}\n\n"
        "primary_source:\n{primary_source}\n\n"
        "source_context:\n{source_context}\n\n"
        "selected_skill:\n{selected_skill}\n\n"
        "search_materials:\n{search_materials}\n\n"
        "evidence_pack:\n{evidence_pack}\n"
    )
    prompt = ChatPromptTemplate.from_messages([("system", system_prompt), ("human", human_prompt)])
    chain, retry_factory = structured_chain(
        prompt,
        stage="plan_article_angle",
        schema=BlueprintOutput,
        temperature=0.35,
    )

    if chain is None or not state.get("task_id"):
        blueprint = _build_fallback_blueprint(
            topic, article_type, evidence_pack, search_materials, selected_skill, primary_source
        )
        # An explicit operator choice outranks the type derived from the material, and
        # must apply on the degraded path too — otherwise the setting silently does
        # nothing whenever no model is configured.
        blueprint = _apply_type_override(blueprint, requested_type)
        blueprint_source = "fallback"
        degraded_reason = "no_model_configured"
    else:
        payload = {
            "topic": topic,
            "article_type": {
                **article_type,
                "selected_topic": selected_topic,
                "account_profile": planning_state.get("account_profile") or {},
                "content_template": planning_state.get("content_template") or {},
            },
            "primary_source": _build_primary_source_block(primary_source),
            "search_materials": _build_search_materials_summary(search_materials),
            "source_context": _build_source_context(search_materials, evidence_pack),
            "selected_skill": selected_skill,
            "evidence_pack": _build_evidence_summary(evidence_pack),
        }
        model_context = stage_context("plan_article_angle", structured_output="BlueprintOutput")
        log_model_request(
            logger,
            task_id=str(state.get("task_id") or ""),
            skill="plan_article_angle",
            context=model_context,
            request=payload,
        )
        try:
            result = await invoke_structured(
                chain,
                payload,
                stage="plan_article_angle",
                build_retry_chain=retry_factory,
            )
            blueprint = _normalize_blueprint_output(result, topic=topic)
            blueprint = _apply_type_override(blueprint, requested_type)
            blueprint = _enforce_evidence_boundary_sections(blueprint, evidence_pack)
            if search_materials and not blueprint.source_driven_framework:
                blueprint.source_driven_framework = _build_source_driven_sections(
                    topic, search_materials, opener=_detect_opener(search_materials, primary_source)
                )
            if search_materials and not blueprint.evidence_map:
                blueprint.evidence_map = _build_evidence_map(blueprint.sections, search_materials)
            log_model_response(
                logger,
                task_id=str(state.get("task_id") or ""),
                skill="plan_article_angle",
                context=model_context,
                response=blueprint.model_dump(),
            )
        except Exception as exc:  # noqa: BLE001
            blueprint_source = "fallback"
            degraded_reason = getattr(exc, "reason", "") or "error"
            logger.warning(
                "plan_article_angle_fallback",
                task_id=str(state.get("task_id") or ""),
                degraded_reason=degraded_reason,
                error=str(exc),
                exc_info=True,
            )
            blueprint = _build_fallback_blueprint(
                topic, article_type, evidence_pack, search_materials, selected_skill, primary_source
            )
            blueprint = _apply_type_override(blueprint, requested_type)

    blueprint_payload = blueprint.model_dump()
    if selected_skill:
        blueprint_payload["selected_skill"] = selected_skill
    blueprint_payload["blueprint_source"] = blueprint_source
    planning_state["article_blueprint"] = blueprint_payload
    planning_state["blueprint_source"] = blueprint_source
    if degraded_reason:
        planning_state["blueprint_degraded_reason"] = degraded_reason
    return {
        "status": "running",
        "current_skill": "plan_article_angle",
        "progress": 44,
        "planning_state": planning_state,
        "article_blueprint": blueprint_payload,
    }
