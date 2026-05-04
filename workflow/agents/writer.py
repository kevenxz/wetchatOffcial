"""Compose article draft from blueprint and evidence pack."""
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


class DraftOutput(BaseModel):
    """Structured article draft payload."""

    title: str = Field(description="Draft title")
    alt_titles: list[str] = Field(default_factory=list, description="Alternative title candidates")
    content: str = Field(description="Markdown draft content")
    summary: str = Field(default="", description="Short draft summary")


def _claim_text(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("claim") or item.get("message") or item.get("title") or "").strip()
    return str(item or "").strip()


def _build_evidence_summary(evidence_pack: dict[str, Any]) -> str:
    lines: list[str] = []
    for label, items in (
        ("confirmed_facts", evidence_pack.get("confirmed_facts") or []),
        ("usable_data_points", evidence_pack.get("usable_data_points") or []),
        ("usable_cases", evidence_pack.get("usable_cases") or []),
        ("risk_points", evidence_pack.get("risk_points") or []),
    ):
        if not items:
            continue
        claims = [claim for item in items[:3] if (claim := _claim_text(item))]
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


def _section_title(section: dict[str, Any]) -> str:
    return str(section.get("section") or section.get("heading") or "").strip()


def _section_goal(section: dict[str, Any]) -> str:
    return str(section.get("goal") or "").strip()


def _section_points(section: dict[str, Any], evidence_pack: dict[str, Any], offset: int) -> list[str]:
    direct_points = [str(item).strip() for item in list(section.get("key_points") or []) if str(item).strip()]
    if direct_points:
        return direct_points[:3]
    claims = [
        claim
        for group in ("confirmed_facts", "usable_data_points", "usable_cases", "risk_points")
        for item in list(evidence_pack.get(group) or [])
        if (claim := _claim_text(item))
    ]
    if not claims:
        return []
    return claims[offset: offset + 2] or claims[:2]


def _build_section_body(section: dict[str, Any], topic: str, evidence_pack: dict[str, Any], index: int) -> str:
    title = _section_title(section)
    goal = _section_goal(section)
    points = _section_points(section, evidence_pack, index)
    shape = str(section.get("shape") or "").strip()
    lines = [f"## {title}"]
    if index == 0:
        lines.append(f"{topic}这件事，不能只看表面的热度。真正值得写的是：它背后出现了什么新信号，以及这些信号能不能被已有资料支撑。")
    if goal:
        lines.append(f"这一节要解决的问题是：{goal}。")
    if points:
        lines.append(f"从已经抓取到的资料看，最直接的线索是：{points[0]}")
        if len(points) > 1:
            lines.append(f"另一个需要放在一起看的信息是：{points[1]}。这意味着文章不能停留在概念判断，而要把事实、数据和案例放在同一条逻辑线上。")
        lines.append("把这条线索放进正文时，不能只作为一句素材引用，而要继续追问它改变了什么：是用户行为变了、商业化压力变了，还是竞争关系开始重新排列。")
    else:
        lines.append("目前可用资料还不足以支撑过强结论，因此这一节只做有限判断，并保留后续验证空间。")
        lines.append("这种写法对公众号更重要，因为读者需要的不只是结论，还需要知道这个结论是怎么从资料里推出来的。")
    if shape in {"risks", "validation"} or "风险" in title or "验证" in title:
        lines.append("这里需要特别收紧表达：没有多源确认的数据，不写成确定结论；只有单一来源的信息，只能作为观察线索。")
    else:
        lines.append("放到微信公众号语境里，这一节需要给读者一个清晰判断：这不是简单复述新闻，而是在解释它为什么和读者有关。")
    return "\n\n".join(lines)


def _is_thin_draft(draft: DraftOutput, outline_result: dict[str, Any]) -> bool:
    if not outline_result:
        return False
    content = str(draft.content or "").strip()
    outline = list(outline_result.get("outline") or [])
    if len(content) < 600:
        return True
    if outline and content.count("## ") < min(2, len(outline)):
        return True
    return False


def _build_fallback_draft(topic: str, blueprint: dict[str, Any], evidence_pack: dict[str, Any] | None = None) -> DraftOutput:
    evidence_pack = dict(evidence_pack or {})
    outline_result = dict(blueprint.get("outline_result") or {})
    sections = list(outline_result.get("outline") or blueprint.get("sections") or [])
    title_candidates = list(outline_result.get("title_candidates") or blueprint.get("title_candidates") or [])
    title = str(title_candidates[0] if title_candidates else blueprint.get("thesis") or topic or "未命名主题").strip()
    alt_titles = [
        candidate
        for candidate in (
            f"{topic}背后，真正要看的是这几个信号",
            f"从搜索资料看{topic}：机会、证据和边界",
        )
        if candidate and candidate != title
    ][:2]
    intro = (
        f"{topic}正在变成一个值得拆开的内容选题。\n\n"
        "如果只把它写成消息复述，读者很难获得增量；更有效的写法，是先把搜索到的事实、数据和案例重新排布，"
        "再判断哪些结论站得住，哪些地方还需要验证。"
    )
    section_blocks = [
        _build_section_body(dict(section), topic, evidence_pack, index)
        for index, section in enumerate(sections)
        if isinstance(section, dict) and _section_title(section)
    ]
    if not section_blocks:
        section_blocks = [
            f"## 先看这件事为什么值得关注\n\n{topic}的核心不在于它是否热闹，而在于它是否已经出现可验证的变化信号。",
            "## 现有证据能支撑什么判断\n\n当前资料可以作为初步观察，但还需要更多数据、官方信息或多源报道来支撑更强结论。",
            "## 风险和证据边界在哪里\n\n没有被证实的信息不能写成确定事实，缺少数据支撑的判断也需要保留条件。",
        ]
    content = "\n\n".join(
        [
            intro,
            *section_blocks,
            "## 最后说一句\n\n一篇好的公众号文章，不是把所有资料都堆进去，而是把搜索材料重新组织成读者能理解、能判断、也知道边界在哪里的结构。\n\n所以这篇文章最终要交付的不是一个大纲，而是一条完整的判断链：先告诉读者发生了什么，再解释为什么重要，最后把证据不足和风险边界交代清楚。",
        ]
    )
    summary = str(outline_result.get("reader_value") or blueprint.get("reader_value") or f"围绕{topic}提炼事实、判断和风险边界。")
    return DraftOutput(title=title, alt_titles=alt_titles, content=content, summary=summary)


async def compose_draft_node(state: WorkflowState) -> dict[str, Any]:
    """Generate the first article draft from blueprint and research evidence."""
    planning_state = dict(state.get("planning_state") or {})
    selected_skill = dict(planning_state.get("selected_skill") or {})
    blueprint = dict(planning_state.get("article_blueprint") or {})
    outline_result = dict(state.get("outline_result") or planning_state.get("outline_result") or {})
    if outline_result:
        blueprint["outline_result"] = outline_result
    research_state = dict(state.get("research_state") or {})
    evidence_pack = dict(research_state.get("evidence_pack") or {})
    revision_brief = dict((state.get("writing_state") or {}).get("revision_brief") or {})
    task_brief = dict(state.get("task_brief") or {})
    selected_topic = dict(state.get("selected_topic") or {})
    config_snapshot = dict(state.get("config_snapshot") or {})
    topic = str(selected_topic.get("title") or task_brief.get("topic") or state.get("keywords") or "").strip()

    if not blueprint.get("sections"):
        fallback = _build_fallback_draft(topic, blueprint, evidence_pack)
        return {
            "status": "running",
            "current_skill": "compose_draft",
            "progress": 54,
            "writing_state": {"draft": fallback.model_dump(), "review_findings": [], "outline_result": outline_result},
            "generated_article": {
                "title": fallback.title,
                "alt_titles": fallback.alt_titles,
                "summary": fallback.summary,
                "content": fallback.content,
            },
        }

    text_model_config = get_model_config().text
    if not text_model_config.api_key:
        fallback = _build_fallback_draft(topic, blueprint, evidence_pack)
        return {
            "status": "running",
            "current_skill": "compose_draft",
            "progress": 54,
            "writing_state": {"draft": fallback.model_dump(), "review_findings": [], "outline_result": outline_result},
            "generated_article": {
                "title": fallback.title,
                "alt_titles": fallback.alt_titles,
                "summary": fallback.summary,
                "content": fallback.content,
            },
        }

    system_prompt = (
        "You are a Chinese content drafting agent. "
        "Write a complete WeChat public account article, not a report outline and not a planning note. "
        "Write a clean Markdown article draft from the provided thesis, sections, and evidence pack. "
        "The content type is explicitly a WeChat public account article: it needs a strong title, opening hook, readable H2 subtitles, complete paragraphs, transitions, and a clear ending. "
        "The article framework must follow the source_driven_framework and evidence_map in the blueprint when they are present. "
        "If selected_skill is provided, follow its tone, framework, evidence_policy, writing_constraints, and title guidance. "
        "The article must strictly follow outline_result when present: title candidates, section order, section goals, source_refs, key_points, must_use_facts, and risk_boundaries. "
        "Do not replace a search-driven framework with a generic template. "
        "Every major H2 section should be grounded in the searched source signals or explicitly state the evidence boundary. "
        "Produce a publication-ready title, two alternative title candidates, a concise summary, and a strong opening hook paragraph before the first H2 section. "
        "Avoid generic opener language such as '本文将从...展开' or other empty roadmap sentences. "
        "Use natural transitions between the opener and the first section, and between sections when the argument turns. "
        "Each H2 section should usually contain 2-3 paragraphs instead of a single thin paragraph. "
        "Keep the section intent and order from the blueprint, but you may refine section headings for readability and stronger publication quality. "
        "Keep the language concrete, and preserve a risk section when requested. "
        "If revision guidance is provided, revise only the weak parts instead of changing the whole structure."
    )
    human_prompt = (
        "topic:\n{topic}\n\n"
        "article_type:\n{article_type}\n\n"
        "blueprint:\n{blueprint}\n\n"
        "outline_result:\n{outline_result}\n\n"
        "evidence_pack:\n{evidence_pack}\n\n"
        "account_profile:\n{account_profile}\n\n"
        "content_template:\n{content_template}\n\n"
        "selected_skill:\n{selected_skill}\n\n"
        "revision_brief:\n{revision_brief}\n"
    )

    prompt = ChatPromptTemplate.from_messages([("system", system_prompt), ("human", human_prompt)])
    llm = ChatOpenAI(
        model=text_model_config.model,
        api_key=text_model_config.api_key,
        base_url=text_model_config.base_url or None,
        max_tokens=2600,
        temperature=0.55,
    )
    chain = prompt | llm.with_structured_output(DraftOutput)

    payload = {
        "topic": topic,
        "article_type": dict(planning_state.get("article_type") or {}),
        "blueprint": blueprint,
        "outline_result": outline_result,
        "evidence_pack": _build_evidence_summary(evidence_pack),
        "revision_brief": revision_brief,
        "account_profile": dict(config_snapshot.get("account_profile") or {}),
        "content_template": dict(config_snapshot.get("content_template") or {}),
        "selected_skill": selected_skill,
    }
    model_context = build_model_context(
        model=text_model_config.model,
        base_url=text_model_config.base_url,
        api_key=text_model_config.api_key,
        structured_output="DraftOutput",
    )
    log_model_request(
        logger,
        task_id=str(state.get("task_id") or ""),
        skill="compose_draft",
        context=model_context,
        request=payload,
    )

    try:
        result = await chain.ainvoke(payload)
        if isinstance(result, DraftOutput):
            draft = result
        else:
            draft = DraftOutput(**dict(result))
        if _is_thin_draft(draft, outline_result):
            draft = _build_fallback_draft(topic, blueprint, evidence_pack)
        log_model_response(
            logger,
            task_id=str(state.get("task_id") or ""),
            skill="compose_draft",
            context=model_context,
            response=draft.model_dump(),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "compose_draft_fallback",
            task_id=str(state.get("task_id") or ""),
            error=str(exc),
        )
        draft = _build_fallback_draft(topic, blueprint, evidence_pack)

    return {
        "status": "running",
        "current_skill": "compose_draft",
        "progress": 54,
        "writing_state": {
            "draft": draft.model_dump(),
            "review_findings": [],
            "revision_brief": {},
            "outline_result": outline_result,
        },
        "generated_article": {
            "title": draft.title,
            "alt_titles": draft.alt_titles,
            "summary": draft.summary,
            "content": draft.content,
        },
    }
