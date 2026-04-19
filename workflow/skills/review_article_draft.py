"""Review the generated article draft for structural quality."""
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

_GENERIC_OPENER_PREFIXES = (
    "本文将",
    "接下来将",
    "这篇文章将",
    "我们将从",
    "本文从",
)


class ReviewOutput(BaseModel):
    """Structured article review payload."""

    passed: bool = Field(description="Whether the draft passes review")
    score: int = Field(description="Article review score from 0 to 100")
    findings: list[dict[str, str]] = Field(default_factory=list, description="Review findings")
    revision_guidance: list[str] = Field(default_factory=list, description="Specific revision guidance")


def _fallback_review(draft: dict[str, Any], evidence_pack: dict[str, Any] | None = None) -> ReviewOutput:
    findings: list[dict[str, str]] = []
    content = str(draft.get("content") or "")
    pack = dict(evidence_pack or {})
    research_gaps = list(pack.get("research_gaps") or [])
    quality_summary = dict(pack.get("quality_summary") or {})
    opener = content.split("\n\n## ", 1)[0].strip()
    if "## 风险边界" not in content and "## 椋庨櫓杈圭晫" not in content:
        findings.append({"type": "structure", "message": "missing risk boundary section"})
    if opener and any(opener.startswith(prefix) for prefix in _GENERIC_OPENER_PREFIXES):
        findings.append({"type": "opener", "message": "opening hook is generic and reads like a roadmap"})
    if "missing_data_evidence" in research_gaps or "missing_high_confidence_fact" in research_gaps:
        findings.append({"type": "evidence", "message": "insufficient evidence coverage for key conclusions"})
    if int(quality_summary.get("high_confidence_items") or 0) <= 0 and research_gaps:
        findings.append({"type": "evidence", "message": "high-confidence evidence is still missing"})
    score = 85 if not findings else 68
    revision_guidance: list[str] = []
    if any(item["type"] == "structure" for item in findings):
        revision_guidance.append("补充风险边界章节")
    if any(item["type"] == "opener" for item in findings):
        revision_guidance.append("重写开头钩子，先给判断或冲突点，不要用本文将从这类空话开场")
    if any(item["type"] == "evidence" for item in findings):
        revision_guidance.append("补充官方或数据证据，并交代当前证据边界")
    return ReviewOutput(
        passed=not findings,
        score=score,
        findings=findings,
        revision_guidance=revision_guidance,
    )


def _build_evidence_summary(evidence_pack: dict[str, Any]) -> str:
    lines: list[str] = []
    for label in ("confirmed_facts", "usable_data_points", "usable_cases", "risk_points"):
        items = list(evidence_pack.get(label) or [])
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


async def review_article_draft_node(state: WorkflowState) -> dict[str, Any]:
    """Run a structured review over the generated draft."""
    writing_state = dict(state.get("writing_state") or {})
    draft = dict(writing_state.get("draft") or {})
    research_state = dict(state.get("research_state") or {})
    evidence_pack = dict(research_state.get("evidence_pack") or {})
    planning_state = dict(state.get("planning_state") or {})

    text_model_config = get_model_config().text
    if not text_model_config.api_key:
        review = _fallback_review(draft, evidence_pack)
        writing_state["review_findings"] = review.findings
        writing_state["revision_guidance"] = review.revision_guidance
        writing_state["article_review"] = {"passed": review.passed, "score": review.score}
        return {
            "status": "running",
            "current_skill": "review_article_draft",
            "progress": 60,
            "writing_state": writing_state,
        }

    system_prompt = (
        "You are a Chinese editorial reviewer. "
        "Review the draft for structure, evidence support, and clarity. "
        "Return concise findings and concrete revision guidance."
    )
    human_prompt = (
        "topic:\n{topic}\n\n"
        "article_type:\n{article_type}\n\n"
        "draft_title:\n{title}\n\n"
        "draft_content:\n{content}\n\n"
        "evidence_pack:\n{evidence_pack}\n"
    )
    prompt = ChatPromptTemplate.from_messages([("system", system_prompt), ("human", human_prompt)])
    llm = ChatOpenAI(
        model=text_model_config.model,
        api_key=text_model_config.api_key,
        base_url=text_model_config.base_url or None,
        max_tokens=1400,
        temperature=0.2,
    )
    chain = prompt | llm.with_structured_output(ReviewOutput)

    payload = {
        "topic": str(state.get("task_brief", {}).get("topic") or state.get("keywords") or ""),
        "article_type": dict(planning_state.get("article_type") or {}),
        "title": str(draft.get("title") or ""),
        "content": str(draft.get("content") or ""),
        "evidence_pack": _build_evidence_summary(evidence_pack),
    }
    model_context = build_model_context(
        model=text_model_config.model,
        base_url=text_model_config.base_url,
        api_key=text_model_config.api_key,
        structured_output="ReviewOutput",
    )
    log_model_request(
        logger,
        task_id=str(state.get("task_id") or ""),
        skill="review_article_draft",
        context=model_context,
        request=payload,
    )

    try:
        result = await chain.ainvoke(payload)
        if isinstance(result, ReviewOutput):
            review = result
        else:
            review = ReviewOutput(**dict(result))
        log_model_response(
            logger,
            task_id=str(state.get("task_id") or ""),
            skill="review_article_draft",
            context=model_context,
            response=review.model_dump(),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "review_article_draft_fallback",
            task_id=str(state.get("task_id") or ""),
            error=str(exc),
        )
        review = _fallback_review(draft, evidence_pack)

    writing_state["review_findings"] = review.findings
    writing_state["revision_guidance"] = review.revision_guidance
    writing_state["article_review"] = {"passed": review.passed, "score": review.score}
    return {
        "status": "running",
        "current_skill": "review_article_draft",
        "progress": 60,
        "writing_state": writing_state,
    }
