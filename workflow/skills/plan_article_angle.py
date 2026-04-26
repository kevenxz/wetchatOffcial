"""Build the dynamic article blueprint from task brief and article type."""
from __future__ import annotations

from typing import Any

import structlog
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from api.store import get_model_config
from workflow.model_logging import build_model_context, log_model_request, log_model_response
from workflow.state import WorkflowState

logger = structlog.get_logger(__name__)


class BlueprintOutput(BaseModel):
    """Structured article blueprint payload."""

    framework: str = Field(default="", description="AI-selected article framework")
    title_candidates: list[str] = Field(default_factory=list, description="Publication-ready title candidates")
    thesis: str = Field(description="Core thesis of the article")
    reader_value: str = Field(default="", description="Why the reader should care")
    sections: list[dict[str, str]] = Field(default_factory=list, description="Ordered H2 sections")
    must_cover_points: list[str] = Field(default_factory=list, description="Points that must be covered")
    drop_points: list[str] = Field(default_factory=list, description="Points intentionally left out")
    source_driven_framework: list[dict[str, str]] = Field(
        default_factory=list,
        description="Search-result-backed structure signals used to shape the article",
    )
    evidence_map: list[dict[str, str]] = Field(
        default_factory=list,
        description="Mapping from planned sections to source claims",
    )


def _normalize_sections(sections: list[dict[str, Any]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for section in sections:
        heading = str(section.get("heading") or section.get("title") or "").strip()
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
    payload["sections"] = _normalize_sections(list(payload.get("sections") or []))[:6]
    payload["title_candidates"] = [
        str(item).strip()
        for item in list(payload.get("title_candidates") or [])
        if str(item).strip()
    ][:4]
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


def _material_claim(material: dict[str, Any]) -> str:
    for key in ("claim", "snippet", "title"):
        value = _clean_text(material.get(key), limit=110)
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
                "source_type": str(item.get("source_type") or "unknown").strip(),
                "domain": str(item.get("domain") or "").strip(),
                "url": str(item.get("url") or "").strip(),
            }
        )
    return materials[:10]


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
    if "risk" in angle or "caution" in angle:
        return "risks"
    if "case" in angle or source_type in {"news", "media"}:
        return "case"
    if "data" in angle or source_type in {"dataset", "report"}:
        return "evidence"
    if index == 0:
        return "hook"
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
    sections: list[dict[str, str]] = []
    used_shapes: set[str] = set()
    for material in search_materials:
        section = _section_from_material(topic, material, len(sections))
        shape = section["shape"]
        if shape in used_shapes and shape not in {"case", "evidence"}:
            continue
        used_shapes.add(shape)
        sections.append(section)
        if len(sections) >= 5:
            break
    if sections and not any(section["shape"] == "risks" for section in sections):
        sections.append(
            {
                "heading": "风险和证据边界在哪里",
                "goal": "基于搜索来源质量说明结论边界，避免把单一来源写成确定结论。",
                "shape": "risks",
            }
        )
    return sections[:6]


def _build_dynamic_sections(
    topic: str,
    article_type: dict[str, Any],
    evidence_pack: dict[str, Any],
    search_materials: list[dict[str, str]],
) -> list[dict[str, str]]:
    profile = _topic_profile(topic)
    focus_phrase = _topic_focus_phrase(topic)
    data_points = list(evidence_pack.get("usable_data_points") or [])
    cases = list(evidence_pack.get("usable_cases") or [])
    facts = list(evidence_pack.get("confirmed_facts") or [])
    research_gaps = list(evidence_pack.get("research_gaps") or [])
    quality_summary = dict(evidence_pack.get("quality_summary") or {})
    source_coverage = dict(quality_summary.get("source_coverage") or {})
    source_sections = _build_source_driven_sections(topic, search_materials)

    if len(source_sections) >= 4:
        return source_sections[:6]
    elif source_sections:
        sections = source_sections
        if not any(section["shape"] == "evidence" for section in sections) and data_points:
            sections.append({"heading": f"数据如何验证{focus_phrase}", "goal": "补充搜索证据中的数据和事实支撑", "shape": "evidence"})
        if not any(section["shape"] == "case" for section in sections) and cases:
            sections.append({"heading": f"哪些案例能说明{focus_phrase}", "goal": "用可验证案例承接前文判断", "shape": "case"})
        if not any(section["shape"] == "risks" for section in sections):
            sections.append({"heading": "结论的边界在哪里", "goal": "交代证据强弱和不确定性", "shape": "risks"})
        return sections[:6]

    if profile == "funding":
        sections = [
            {"heading": "这一轮融资潮先看什么", "goal": "先给结论，定义这轮热度的判断标准", "shape": "hook"},
            {"heading": "资金为什么重新流入", "goal": "解释驱动融资回暖的关键因素", "shape": "drivers"},
            {"heading": "资金流向了哪些方向", "goal": "结合数据看热点赛道和节奏", "shape": "evidence"},
            {"heading": "哪些公司真正吃到红利", "goal": "用案例区分热度和兑现能力", "shape": "case"},
            {"heading": "风险边界在哪里", "goal": "说明估值、交付和周期风险", "shape": "risks"},
        ]
    elif profile == "expansion":
        sections = [
            {"heading": "先看出海这件事值不值得做", "goal": "先判断主题的重要性", "shape": "hook"},
            {"heading": "海外市场到底缺什么", "goal": "解释需求侧差异", "shape": "drivers"},
            {"heading": "产品和渠道怎么分化", "goal": "看不同打法的结构差异", "shape": "evidence"},
            {"heading": "谁更有可能先跑出来", "goal": "结合案例判断胜率", "shape": "case"},
            {"heading": "风险边界在哪里", "goal": "说明本地化、成本和交付风险", "shape": "risks"},
        ]
    else:
        sections = [
            {"heading": f"{focus_phrase}为什么会变成一个真问题", "goal": "明确这件事为什么值得关注", "shape": "hook"},
            {"heading": f"{focus_phrase}背后真正卡住的是哪几件事", "goal": "解释驱动因素", "shape": "drivers"},
            {"heading": f"从哪些事实和数据能看清{focus_phrase}", "goal": "整合事实和数据", "shape": "evidence"},
            {"heading": f"{focus_phrase}的风险边界到底在哪", "goal": "约束结论，说明不确定性", "shape": "risks"},
        ]

    if not data_points:
        sections = [section for section in sections if section["shape"] != "evidence"] + [
            {"heading": "还缺哪些关键验证", "goal": "指出证据不足的部分", "shape": "next_steps"}
        ]
    if not cases:
        sections = [section for section in sections if section["shape"] != "case"]
    if not facts and len(sections) < 4:
        sections.insert(1, {"heading": "背景里真正发生了什么", "goal": "补齐必要事实背景", "shape": "context"})
    if "missing_high_confidence_fact" in research_gaps or (
        source_coverage and set(source_coverage).issubset({"community", "aggregator", "unknown"})
    ):
        sections.append(
            {
                "heading": "还哪些核心判断需要验证",
                "goal": "明确哪些结论还缺少官方或数据证据支撑",
                "shape": "validation",
            }
        )

    return sections[:6]


def _build_evidence_map(sections: list[dict[str, str]], search_materials: list[dict[str, str]]) -> list[dict[str, str]]:
    evidence_map: list[dict[str, str]] = []
    for section, material in zip(sections, search_materials, strict=False):
        evidence_map.append(
            {
                "section_heading": section.get("heading", ""),
                "source_title": material.get("title", ""),
                "source_claim": material.get("claim", ""),
                "source_url": material.get("url", ""),
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
    if not any("验证" in section.get("heading", "") or "证据" in section.get("heading", "") for section in blueprint.sections):
        validation_section = {
            "heading": "还需要验证哪些关键判断",
            "goal": "明确当前搜索材料的证据边界，说明哪些结论仍缺少官方、数据或多源确认。",
            "shape": "validation",
        }
        if len(blueprint.sections) >= 6:
            blueprint.sections[-1] = validation_section
        else:
            blueprint.sections.append(validation_section)
    if "补齐官方或数据证据" not in blueprint.must_cover_points:
        blueprint.must_cover_points.append("补齐官方或数据证据")
    return blueprint


def _build_fallback_blueprint(
    topic: str,
    article_type: dict[str, Any],
    evidence_pack: dict[str, Any],
    search_materials: list[dict[str, str]],
) -> BlueprintOutput:
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


def _build_evidence_summary(evidence_pack: dict[str, Any]) -> str:
    lines: list[str] = []
    for label in ("confirmed_facts", "usable_data_points", "usable_cases", "risk_points"):
        items = list(evidence_pack.get(label) or [])
        if not items:
            continue
        claims = [str(item.get("claim") or "").strip() for item in items[:4] if str(item.get("claim") or "").strip()]
        if claims:
            lines.append(f"{label}: " + " | ".join(claims))
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
    for index, item in enumerate(search_materials[:8], start=1):
        claim = item.get("claim") or item.get("title") or ""
        title = item.get("title") or ""
        source = item.get("domain") or item.get("source_type") or "unknown"
        angle = item.get("angle") or "fact"
        lines.append(f"{index}. [{angle}] {title} ({source}) - {claim}")
    return "\n".join(lines)


async def plan_article_angle_node(state: WorkflowState) -> dict[str, Any]:
    """Create a dynamic section plan for the current article."""
    planning_state = dict(state.get("planning_state") or {})
    article_type = dict(planning_state.get("article_type") or {})
    selected_topic = dict(state.get("selected_topic") or {})
    topic = str(selected_topic.get("title") or state.get("task_brief", {}).get("topic", "")).strip()
    research_state = dict(state.get("research_state") or {})
    evidence_pack = dict(research_state.get("evidence_pack") or {})
    search_materials = _collect_search_materials(research_state, evidence_pack)

    text_model_config = get_model_config().text
    if not text_model_config.api_key or not state.get("task_id"):
        blueprint = _build_fallback_blueprint(topic, article_type, evidence_pack, search_materials)
    else:
        system_prompt = (
            "You are a planning agent for Chinese long-form content. "
            "Generate a dynamic article blueprint based on the actual search materials, extracted source content, and evidence density. "
            "You must decide the article framework, final title candidates, and H2 subtitles yourself from the materials. "
            "The result should feel like a WeChat public account article structure planned by an experienced editor. "
            "Section headings should be content-specific, topic-specific, and publication-ready instead of generic placeholders. "
            "Keep 4 to 6 H2 sections. Always include one risk-boundary section. "
            "Use the search_materials to decide the article framework before using any generic topic template. "
            "Each section should map to at least one concrete source signal when possible. "
            "Do not output a fixed template."
        )
        human_prompt = (
            "topic:\n{topic}\n\n"
            "article_type:\n{article_type}\n\n"
            "search_materials:\n{search_materials}\n\n"
            "evidence_pack:\n{evidence_pack}\n"
        )
        prompt = ChatPromptTemplate.from_messages([("system", system_prompt), ("human", human_prompt)])
        llm = ChatOpenAI(
            model=text_model_config.model,
            api_key=text_model_config.api_key,
            base_url=text_model_config.base_url or None,
            max_tokens=1800,
            temperature=0.35,
        )
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
            "evidence_pack": _build_evidence_summary(evidence_pack),
        }
        model_context = build_model_context(
            model=text_model_config.model,
            base_url=text_model_config.base_url,
            api_key=text_model_config.api_key,
            structured_output="BlueprintOutput",
        )
        log_model_request(
            logger,
            task_id=str(state.get("task_id") or ""),
            skill="plan_article_angle",
            context=model_context,
            request=payload,
        )
        try:
            result = await chain.ainvoke(payload)
            blueprint = _normalize_blueprint_output(result)
            if len(blueprint.sections) < 4:
                raise ValueError("insufficient dynamic sections from model blueprint")
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
            blueprint = _build_fallback_blueprint(topic, article_type, evidence_pack, search_materials)

    planning_state["article_blueprint"] = blueprint.model_dump()
    return {
        "status": "running",
        "current_skill": "plan_article_angle",
        "progress": 44,
        "planning_state": planning_state,
    }
