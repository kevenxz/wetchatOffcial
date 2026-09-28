"""Build the dynamic article blueprint from task brief and article type."""
from __future__ import annotations

import json
import re
from typing import Any

import structlog
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from workflow.model_factory import build_chat_model, llm_slot, model_context as stage_context
from workflow.model_logging import log_model_request, log_model_response
from workflow.state import WorkflowState

logger = structlog.get_logger(__name__)


class BlueprintOutput(BaseModel):
    """Structured article blueprint payload."""

    framework: str = Field(default="", description="Optional narrative hypothesis, never a mandatory template")
    structure_mode: str = Field(default="adaptive", description="adaptive by default; structure follows the material")
    title_candidates: list[str] = Field(default_factory=list, description="Publication-ready title candidates")
    thesis: str = Field(description="Core thesis of the article")
    reader_value: str = Field(default="", description="Why the reader should care")
    central_question: str = Field(default="", description="The single question the article must answer")
    opening_move: str = Field(default="", description="How the opening creates relevance or tension")
    narrative_arc: str = Field(default="", description="The intended movement of the argument, not a section template")
    ending_move: str = Field(default="", description="How the ending resolves the thesis and points forward")
    sections: list[dict[str, str]] = Field(
        default_factory=list,
        description="Candidate narrative beats; the writer may merge, reorder, rename, or omit them",
    )
    must_cover_points: list[str] = Field(default_factory=list, description="Points that must be covered")
    drop_points: list[str] = Field(default_factory=list, description="Points intentionally left out")
    source_driven_framework: list[dict[str, str]] = Field(
        default_factory=list,
        description="Search-result-backed narrative signals, not a required section sequence",
    )
    evidence_map: list[dict[str, str]] = Field(
        default_factory=list,
        description="Mapping from planned sections to source claims",
    )


def _clean_heading(value: Any) -> str:
    heading = " ".join(str(value or "").replace("#", " ").split()).strip(" -—:：")
    if not heading or len(heading) > 42:
        return ""
    if re.search(r"(?:https?://|www\.|\.(?:com|cn|net|org)(?:/|$))", heading, flags=re.I):
        return ""
    if heading.endswith("...") or heading.endswith("……"):
        return ""
    return heading


def _normalize_sections(sections: list[dict[str, Any]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for section in sections:
        heading = _clean_heading(section.get("heading") or section.get("title"))
        goal = str(section.get("goal") or section.get("content") or "").strip()
        shape = str(section.get("shape") or "").strip()
        if not heading or not goal:
            continue
        normalized.append({"heading": heading, "goal": goal, "shape": shape})
    return normalized


def _normalize_blueprint_output(result: BlueprintOutput | dict[str, Any]) -> BlueprintOutput:
    if isinstance(result, BlueprintOutput):
        payload = result.model_dump()
    else:
        payload = dict(result)
    payload["sections"] = _normalize_sections(list(payload.get("sections") or []))
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


def _material_excerpt(material: dict[str, Any]) -> str:
    for key in ("text", "content", "summary", "claim", "snippet"):
        value = _clean_text(material.get(key), limit=900)
        if value:
            return value
    return ""


def _material_title(material: dict[str, Any]) -> str:
    return _clean_text(material.get("title") or material.get("claim") or material.get("snippet"), limit=64)


def _dedupe_materials(items: list[dict[str, Any]]) -> list[dict[str, str]]:
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
        materials.append(
            {
                "angle": str(item.get("angle") or item.get("query_intent") or "fact").strip() or "fact",
                "query": str(item.get("query") or "").strip(),
                "title": title,
                "claim": claim,
                "excerpt": _material_excerpt(item),
                "source_type": str(item.get("source_type") or "unknown").strip(),
                "domain": str(item.get("domain") or "").strip(),
                "url": str(item.get("url") or "").strip(),
                "published_at": str(item.get("published_at") or item.get("date") or "").strip(),
            }
        )
    return materials[:12]


def _collect_search_materials(research_state: dict[str, Any], evidence_pack: dict[str, Any]) -> list[dict[str, str]]:
    raw_items: list[dict[str, Any]] = []
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


def _section_from_material(topic: str, material: dict[str, str], index: int) -> dict[str, str]:
    focus_phrase = _topic_focus_phrase(topic)
    title = _material_title(material) or focus_phrase
    claim = _material_claim(material)
    shape = _shape_from_material(material, index)
    if shape == "hook":
        heading = f"先从{title}看清问题"
        goal = f"用搜索结果中最强的信号开篇，说明{focus_phrase}为什么值得写。"
    elif shape == "evidence":
        heading = f"{title}给出了什么数据线索"
        goal = "围绕搜索到的数据、报告或事实材料建立判断，而不是先套固定模板。"
    elif shape == "case":
        heading = f"{title}这个案例说明了什么"
        goal = "用搜索到的案例解释具体变化，区分现象、动作和可验证结果。"
    elif shape == "risks":
        heading = f"{title}背后的风险边界"
        goal = "把搜索材料里的不确定性、争议和证据缺口讲清楚。"
    else:
        heading = f"{title}背后真正的驱动因素"
        goal = "从搜索材料拆出原因链条，解释变化为什么发生。"
    if claim:
        goal = f"{goal} 参考线索：{claim}"
    return {"heading": heading, "goal": goal, "shape": shape}


def _build_source_driven_sections(topic: str, search_materials: list[dict[str, str]]) -> list[dict[str, str]]:
    """Cluster sources by narrative job so source count never becomes section count."""
    buckets: dict[str, list[str]] = {"evidence": [], "drivers": [], "case": [], "tension": []}
    for index, material in enumerate(search_materials):
        claim = _material_claim(material)
        if not claim:
            continue
        shape = _shape_from_material(material, index)
        bucket = shape if shape in buckets else "drivers"
        if claim not in buckets[bucket]:
            buckets[bucket].append(claim)

    focus = _topic_focus_phrase(topic)
    definitions = (
        ("evidence", "先确认发生了什么", f"用可核验事实回答{focus}发生了哪些变化，区分事实与推断。"),
        ("drivers", "变化为什么会在此时出现", "解释事实之间的原因链条，以及哪些只是同时发生而非因果关系。"),
        ("case", "把变化放进真实场景", "用具体案例说明影响如何发生，并交代案例能证明和不能证明什么。"),
        ("tension", "仍需验证的关键变量", "呈现相反信号、证据缺口与下一步验证条件，不制造虚假的确定性。"),
    )
    sections: list[dict[str, str]] = []
    for shape, heading, goal in definitions:
        claims = buckets[shape]
        if not claims:
            continue
        evidence_hint = "；".join(claims[:2])
        sections.append({"heading": heading, "goal": f"{goal} 可用证据：{evidence_hint}", "shape": shape})
    return sections


def _build_dynamic_sections(
    topic: str,
    article_type: dict[str, Any],
    evidence_pack: dict[str, Any],
    search_materials: list[dict[str, str]],
) -> list[dict[str, str]]:
    source_sections = _build_source_driven_sections(topic, search_materials)
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


def _build_legacy_fallback_blueprint(
    topic: str,
    article_type: dict[str, Any],
    evidence_pack: dict[str, Any],
    search_materials: list[dict[str, str]],
    selected_skill: dict[str, Any] | None = None,
) -> BlueprintOutput:
    selected_skill = dict(selected_skill or {})
    if selected_skill.get("skill_id") == "quantum_tech_explainer":
        sections = [
            {"heading": "先把这项量子技术到底是什么讲清楚", "goal": "用准确但可读的方式解释核心概念和常见误解", "shape": "hook"},
            {"heading": "真正的新进展发生在工程指标上", "goal": "围绕硬件、纠错、相干时间、保真度或通信链路拆解变化", "shape": "evidence"},
            {"heading": "它距离产业应用还有哪几道门槛", "goal": "连接安全通信、材料计算、药物模拟或优化问题等应用场景", "shape": "drivers"},
            {"heading": "哪些结论现在还不能写得太满", "goal": "交代实验室指标、规模化、成本和商业化周期的证据边界", "shape": "risks"},
        ]
        if search_materials:
            source_sections = _build_source_driven_sections(topic, search_materials)
            sections = (source_sections[:3] + sections)[0:6]
        return BlueprintOutput(
            framework=str(selected_skill.get("framework") or "量子科技深度解读"),
            title_candidates=[
                f"{topic}：真正值得看的不是概念，而是这些工程指标",
                f"{topic}背后，量子科技走到了哪一步",
                f"别把{topic}写玄了：进展、边界和产业信号",
            ],
            thesis=f"{topic}的关键不在于概念热度，而在于科学原理、工程指标和商业化边界是否同时站得住。",
            reader_value="帮助读者区分量子科技的真实进展、工程门槛和产业化想象。",
            sections=sections[:6],
            must_cover_points=[
                "区分科学原理、工程样机和商业化产品",
                "解释关键术语并说明验证指标",
                "保留证据边界和不确定性",
            ],
            drop_points=["量子玄学化表达", "马上取代经典计算的夸张判断"],
            source_driven_framework=sections[:6],
            evidence_map=_build_evidence_map(sections[:6], search_materials),
        )

    profile = _topic_profile(topic)
    research_gaps = list(evidence_pack.get("research_gaps") or [])
    quality_summary = dict(evidence_pack.get("quality_summary") or {})
    source_coverage = dict(quality_summary.get("source_coverage") or {})
    thesis_map = {
        "funding": f"{topic}正在从热度走向分化判断",
        "expansion": f"{topic}的关键不在热闹，而在能否完成本地化落地",
        "launch": f"{topic}更值得看的是真实影响，而不是发布动作本身",
        "general": f"{topic}需要从主题和证据两侧重新组织判断",
    }
    reader_value_map = {
        "funding": "帮助读者判断这一轮融资热度的含金量",
        "expansion": "帮助读者判断出海机会和落地难点",
        "launch": "帮助读者判断新动作背后的真实价值",
        "general": "帮助读者快速建立主题判断框架",
    }
    framework_map = {
        "funding": "融资趋势解读型",
        "expansion": "出海机会分析型",
        "launch": "产品发布解读型",
        "general": "搜索证据解读型",
    }
    sections = _build_dynamic_sections(topic, article_type, evidence_pack, search_materials)
    title_candidates = [
        f"{topic}，真正值得看的不是热闹",
        f"从搜索证据看{topic}的下一步",
        f"{topic}背后的信号和边界",
    ]
    must_cover_points = [section["heading"] for section in sections[:3]]
    if "missing_high_confidence_fact" in research_gaps or "missing_data_evidence" in research_gaps:
        must_cover_points.append("补齐官方或数据证据")
    if source_coverage and set(source_coverage).issubset({"community", "aggregator", "unknown"}):
        must_cover_points.append("交代当前证据边界")
    drop_points = ["泛泛背景复述"] if profile in {"funding", "expansion"} else []
    return BlueprintOutput(
        framework=framework_map[profile],
        title_candidates=title_candidates,
        thesis=thesis_map[profile],
        reader_value=reader_value_map[profile],
        sections=sections,
        must_cover_points=must_cover_points,
        drop_points=drop_points,
        source_driven_framework=sections,
        evidence_map=_build_evidence_map(sections, search_materials),
    )


def _build_fallback_blueprint(
    topic: str,
    article_type: dict[str, Any],
    evidence_pack: dict[str, Any],
    search_materials: list[dict[str, str]],
    selected_skill: dict[str, Any] | None = None,
) -> BlueprintOutput:
    """Build a WeChat-oriented fallback blueprint from skill and available evidence."""
    selected_skill = dict(selected_skill or {})
    profile = _topic_profile(topic)
    research_gaps = list(evidence_pack.get("research_gaps") or [])
    quality_summary = dict(evidence_pack.get("quality_summary") or {})
    source_coverage = dict(quality_summary.get("source_coverage") or {})
    skill_id = str(selected_skill.get("skill_id") or "")
    skill_name = str(selected_skill.get("name") or "").strip()
    skill_framework = str(selected_skill.get("framework") or "").strip()
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
        "funding": f"{topic}需要先看资金流向、估值分化和真实兑现能力，而不是只看热度。",
        "expansion": f"{topic}的关键不在热门，而在需求、渠道和本地化落地是否成立。",
        "launch": f"{topic}更值得看的是真实影响、使用场景和风险边界，而不是发布动作本身。",
        "general": f"{topic}需要放回搜索证据里判断：哪些已经被证明，哪些仍只是信号。",
    }

    source_sections = _build_source_driven_sections(topic, search_materials)
    quantum_sections = [
        {"heading": "先把这项量子技术到底是什么讲清楚", "goal": "用准确但可读的方式解释核心概念和常见误解", "shape": "hook"},
        {"heading": "真正的新进展发生在工程指标上", "goal": "围绕硬件、纠错、相干时间、保真度或通信链路拆解变化", "shape": "evidence"},
        {"heading": "它距离产业应用还有哪几道门槛", "goal": "连接安全通信、材料计算、药物模拟或优化问题等应用场景", "shape": "drivers"},
        {"heading": "哪些结论现在还不能写得太满", "goal": "交代实验室指标、规模化、成本和商业化周期的证据边界", "shape": "risks"},
    ]
    if source_sections:
        sections = list(source_sections)
        if skill_id == "quantum_tech_explainer" and not any("工程指标" in section.get("heading", "") for section in sections):
            sections.append(
                {
                    "heading": "关键进展看哪些工程指标",
                    "goal": "围绕硬件、纠错、相干时间、保真度或通信链路拆解变化。",
                    "shape": "evidence",
                }
            )
        if skill_id == "quantum_tech_explainer" and len(sections) < 4:
            sections.extend(quantum_sections)
    elif skill_id == "quantum_tech_explainer":
        sections = [
            {"heading": "先把这项量子技术到底是什么讲清楚", "goal": "用准确但可读的方式解释核心概念和常见误解", "shape": "hook"},
            {"heading": "真正的新进展发生在工程指标上", "goal": "围绕硬件、纠错、相干时间、保真度或通信链路拆解变化", "shape": "evidence"},
            {"heading": "它距离产业应用还有哪几道门槛", "goal": "连接安全通信、材料计算、药物模拟或优化问题等应用场景", "shape": "drivers"},
            {"heading": "哪些结论现在还不能写得太满", "goal": "交代实验室指标、规模化、成本和商业化周期的证据边界", "shape": "risks"},
        ]
    elif section_guidance:
        shapes = ["hook", "evidence", "case", "risks", "next_steps"]
        sections = [
            {
                "heading": f"{topic}：{_clean_text(guidance, limit=26)}",
                "goal": f"按所选 skill 的写作要求展开：{guidance}",
                "shape": shapes[min(index, len(shapes) - 1)],
            }
            for index, guidance in enumerate(section_guidance)
        ]
    else:
        sections = _build_dynamic_sections(topic, article_type, evidence_pack, search_materials)

    existing = {(section.get("heading", ""), section.get("shape", "")) for section in sections}
    for section in _build_dynamic_sections(topic, article_type, evidence_pack, search_materials):
        signature = (section.get("heading", ""), section.get("shape", ""))
        if signature not in existing:
            sections.append(section)
            existing.add(signature)
        if len(sections) >= 3:
            break

    framework = skill_framework or (f"{skill_name} · 微信公众号文章蓝图" if skill_name else framework_map[profile])
    title_candidates = [
        f"{topic}，真正值得看的不是热闹",
        f"从搜索证据看{topic}的下一步",
        f"{topic}背后的信号、证据和边界",
    ]
    must_cover_points = [section["heading"] for section in sections[:3]]
    if selected_skill.get("evidence_policy"):
        must_cover_points.append(str(selected_skill["evidence_policy"]))
    must_cover_points.extend(writing_constraints[:3])
    if "missing_high_confidence_fact" in research_gaps or "missing_data_evidence" in research_gaps:
        must_cover_points.append("补齐官方或数据证据")
    if source_coverage and set(source_coverage).issubset({"community", "aggregator", "unknown"}):
        must_cover_points.append("交代当前证据边界")

    drop_points = ["泛泛背景复述"] if profile in {"funding", "expansion"} else []
    if skill_id == "quantum_tech_explainer":
        title_candidates = [
            f"{topic}：真正值得看的不是概念，而是工程指标",
            f"{topic}背后，量子科技走到了哪一步",
            f"别把{topic}写玄了：进展、边界和产业信号",
        ]
        thesis_map["general"] = f"{topic}的关键不在概念热度，而在科学原理、工程指标和商业化边界是否同时站得住。"
        reader_value_map["general"] = "帮助读者区分量子科技的真实进展、工程门槛和产业化想象。"
        drop_points.extend(["量子玄学化表达", "马上取代经典计算的夸张判断"])

    return BlueprintOutput(
        framework=framework,
        title_candidates=title_candidates,
        thesis=thesis_map[profile],
        reader_value=reader_value_map[profile],
        central_question=f"围绕{topic}，目前最值得读者弄清楚的变化、影响和证据边界是什么？",
        opening_move="从一个已确认的变化、具体场景或认知冲突切入，在首屏给出中心判断和读者关联。",
        narrative_arc="沿着事实确认、原因解释、现实影响与未决变量自然推进；素材不足时合并或省略节点。",
        ending_move="回扣中心判断，给出下一步观察指标或可执行启示，不重复全文、不喊口号。",
        sections=sections,
        must_cover_points=list(dict.fromkeys(must_cover_points)),
        drop_points=list(dict.fromkeys(drop_points)),
        source_driven_framework=sections,
        evidence_map=_build_evidence_map(sections, search_materials),
    )


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
) -> BlueprintOutput:
    """Final fallback blueprint builder with neutral title candidates."""
    selected_skill = dict(selected_skill or {})
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

    source_sections = _build_source_driven_sections(topic, search_materials)
    if source_sections:
        sections = list(source_sections)
        if skill_id == "quantum_tech_explainer" and not any("工程指标" in section.get("heading", "") for section in sections):
            sections.append(
                {
                    "heading": "关键进展看哪些工程指标",
                    "goal": "围绕硬件、纠错、相干时间、保真度或通信链路拆解变化。",
                    "shape": "evidence",
                }
            )
    else:
        sections = _build_dynamic_sections(topic, article_type, evidence_pack, search_materials)

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

    return BlueprintOutput(
        framework=framework,
        title_candidates=title_candidates,
        thesis=thesis_map[profile],
        reader_value=reader_value_map[profile],
        central_question=f"围绕{topic}，目前最值得读者弄清楚的变化、影响和证据边界是什么？",
        opening_move="从一个已确认的变化、具体场景或认知冲突切入，在首屏给出中心判断和读者关联。",
        narrative_arc="沿着事实确认、原因解释、现实影响与未决变量自然推进；素材不足时合并或省略节点。",
        ending_move="回扣中心判断，给出下一步观察指标或可执行启示，不重复全文、不喊口号。",
        sections=sections,
        must_cover_points=list(dict.fromkeys(must_cover_points)),
        drop_points=list(dict.fromkeys(drop_points)),
        source_driven_framework=sections,
        evidence_map=_build_evidence_map(sections, search_materials),
    )


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

    llm = build_chat_model(stage="plan_article_angle", max_tokens=1800, temperature=0.35)
    if llm is None or not state.get("task_id"):
        blueprint = _build_fallback_blueprint(topic, article_type, evidence_pack, search_materials, selected_skill)
    else:
        system_prompt = (
            "You are a planning agent for Chinese WeChat public account articles. "
            "Generate a dynamic article blueprint based on the actual search materials, extracted source content, and evidence density. "
            "Read source_context first; it contains the real search results, extracted page text, source URLs, and evidence pack. "
            "The output is a WeChat article blueprint, not a research report, not a search plan, and not a generic outline. "
            "You must decide the article framework, final title candidates, opening logic, and H2 subtitles from the searched materials. "
            "The result should feel like a WeChat public account article structure planned by an experienced editor: readable, specific, and publication-ready. "
            "Section headings should be content-specific, topic-specific, and publication-ready instead of generic placeholders. "
            "You may decide whether H2 sections are needed at all, and freely choose their number, order, and shape. "
            "The sections field contains candidate narrative beats, not a contract: the writer may merge, reorder, rename, replace, or omit them. "
            "Choose a scene-led, question-led, argument-led, chronological, contrast, list, or essay-like narrative only when it fits the material. "
            "Use source_context and search_materials to decide the article framework before using any generic topic template. "
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
            "source_context:\n{source_context}\n\n"
            "selected_skill:\n{selected_skill}\n\n"
            "search_materials:\n{search_materials}\n\n"
            "evidence_pack:\n{evidence_pack}\n"
        )
        prompt = ChatPromptTemplate.from_messages([("system", system_prompt), ("human", human_prompt)])
        chain = prompt | llm.with_structured_output(BlueprintOutput)
        payload = {
            "topic": topic,
            "article_type": {
                **article_type,
                "selected_topic": selected_topic,
                "account_profile": planning_state.get("account_profile") or {},
                "content_template": planning_state.get("content_template") or {},
            },
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
            async with llm_slot():
                result = await chain.ainvoke(payload)
            blueprint = _normalize_blueprint_output(result)
            blueprint = _enforce_evidence_boundary_sections(blueprint, evidence_pack)
            if search_materials and not blueprint.source_driven_framework:
                blueprint.source_driven_framework = _build_source_driven_sections(topic, search_materials)
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
            logger.warning(
                "plan_article_angle_fallback",
                task_id=str(state.get("task_id") or ""),
                error=str(exc),
            )
            blueprint = _build_fallback_blueprint(topic, article_type, evidence_pack, search_materials, selected_skill)

    blueprint_payload = blueprint.model_dump()
    if selected_skill:
        blueprint_payload["selected_skill"] = selected_skill
    planning_state["article_blueprint"] = blueprint_payload
    return {
        "status": "running",
        "current_skill": "plan_article_angle",
        "progress": 44,
        "planning_state": planning_state,
        "article_blueprint": blueprint_payload,
    }
