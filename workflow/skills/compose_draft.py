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
    return "\n".join(lines)


def _build_fallback_draft(topic: str, blueprint: dict[str, Any]) -> DraftOutput:
    sections = list(blueprint.get("sections") or [])
    title = str(blueprint.get("thesis") or topic or "未命名主题").strip()
    content = "\n\n".join(
        f"## {section['heading']}\n{section['goal']}"
        for section in sections
        if section.get("heading") and section.get("goal")
    )
    return DraftOutput(title=title, content=content, summary="")


async def compose_draft_node(state: WorkflowState) -> dict[str, Any]:
    """Generate the first article draft from blueprint and research evidence."""
    planning_state = dict(state.get("planning_state") or {})
    blueprint = dict(planning_state.get("article_blueprint") or {})
    research_state = dict(state.get("research_state") or {})
    evidence_pack = dict(research_state.get("evidence_pack") or {})
    task_brief = dict(state.get("task_brief") or {})
    topic = str(task_brief.get("topic") or state.get("keywords") or "").strip()

    if not blueprint.get("sections"):
        fallback = _build_fallback_draft(topic, blueprint)
        return {
            "status": "running",
            "current_skill": "compose_draft",
            "progress": 54,
            "writing_state": {"draft": fallback.model_dump(), "review_findings": []},
            "generated_article": {"title": fallback.title, "content": fallback.content},
        }

    text_model_config = get_model_config().text
    if not text_model_config.api_key:
        fallback = _build_fallback_draft(topic, blueprint)
        return {
            "status": "running",
            "current_skill": "compose_draft",
            "progress": 54,
            "writing_state": {"draft": fallback.model_dump(), "review_findings": []},
            "generated_article": {"title": fallback.title, "content": fallback.content},
        }

    system_prompt = (
        "You are a Chinese content drafting agent. "
        "Write a clean Markdown article draft from the provided thesis, sections, and evidence pack. "
        "Keep all provided H2 headings, keep the language concrete, and preserve a risk section when requested."
    )
    human_prompt = (
        "topic:\n{topic}\n\n"
        "article_type:\n{article_type}\n\n"
        "blueprint:\n{blueprint}\n\n"
        "evidence_pack:\n{evidence_pack}\n"
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
        },
        "generated_article": {"title": draft.title, "content": draft.content},
    }
