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
        claims = [str(item.get("claim") or "").strip() for item in items[:3] if str(item.get("claim") or "").strip()]
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


def _build_fallback_draft(topic: str, blueprint: dict[str, Any]) -> DraftOutput:
    sections = list(blueprint.get("sections") or [])
    title = str(blueprint.get("thesis") or topic or "未命名主题").strip()
    alt_titles = [
        candidate
        for candidate in (
            f"{title}，真正要看的是什么",
            f"{title}背后，哪些变化最值得注意",
        )
        if candidate and candidate != title
    ][:2]
    content = "\n\n".join(
        f"## {section['heading']}\n{section['goal']}"
        for section in sections
        if section.get("heading") and section.get("goal")
    )
    return DraftOutput(title=title, alt_titles=alt_titles, content=content, summary="")


async def compose_draft_node(state: WorkflowState) -> dict[str, Any]:
    """Generate the first article draft from blueprint and research evidence."""
    planning_state = dict(state.get("planning_state") or {})
    blueprint = dict(planning_state.get("article_blueprint") or {})
    research_state = dict(state.get("research_state") or {})
    evidence_pack = dict(research_state.get("evidence_pack") or {})
    revision_brief = dict((state.get("writing_state") or {}).get("revision_brief") or {})
    task_brief = dict(state.get("task_brief") or {})
    topic = str(task_brief.get("topic") or state.get("keywords") or "").strip()

    if not blueprint.get("sections"):
        fallback = _build_fallback_draft(topic, blueprint)
        return {
            "status": "running",
            "current_skill": "compose_draft",
            "progress": 54,
            "writing_state": {"draft": fallback.model_dump(), "review_findings": []},
            "generated_article": {
                "title": fallback.title,
                "alt_titles": fallback.alt_titles,
                "summary": fallback.summary,
                "content": fallback.content,
            },
        }

    text_model_config = get_model_config().text
    if not text_model_config.api_key:
        fallback = _build_fallback_draft(topic, blueprint)
        return {
            "status": "running",
            "current_skill": "compose_draft",
            "progress": 54,
            "writing_state": {"draft": fallback.model_dump(), "review_findings": []},
            "generated_article": {
                "title": fallback.title,
                "alt_titles": fallback.alt_titles,
                "summary": fallback.summary,
                "content": fallback.content,
            },
        }

    system_prompt = (
        "You are a Chinese content drafting agent. "
        "Write a clean Markdown article draft from the provided thesis, sections, and evidence pack. "
        "The result should read like a polished WeChat public account article. "
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
        "evidence_pack:\n{evidence_pack}\n\n"
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
        "evidence_pack": _build_evidence_summary(evidence_pack),
        "revision_brief": revision_brief,
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
        draft = _build_fallback_draft(topic, blueprint)

    return {
        "status": "running",
        "current_skill": "compose_draft",
        "progress": 54,
        "writing_state": {
            "draft": draft.model_dump(),
            "review_findings": [],
            "revision_brief": {},
        },
        "generated_article": {
            "title": draft.title,
            "alt_titles": draft.alt_titles,
            "summary": draft.summary,
            "content": draft.content,
        },
    }
