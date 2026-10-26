"""Review the generated article draft for structural quality."""
from __future__ import annotations

import re
from typing import Any

import structlog
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from workflow.model_factory import invoke_structured, model_context as stage_context, structured_chain
from workflow.model_logging import log_model_request, log_model_response
from workflow.state import WorkflowState

logger = structlog.get_logger(__name__)

_GENERIC_OPENER_PREFIXES = (
    "本文将",
    "接下来将",
    "这篇文章将",
    "我们将从",
    "本文从",
)

_PLANNING_LANGUAGE = (
    "这一节要解决的问题",
    "把这条线索放进正文",
    "放到微信公众号语境",
    "参考线索：",
    "本节目标",
    "目前可用资料",
)


def _structural_findings(content: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    exposed = [phrase for phrase in _PLANNING_LANGUAGE if phrase in content]
    if exposed:
        findings.append(
            {
                "type": "planning_language",
                "message": f"正文暴露了编辑或提示词语言：{'、'.join(exposed[:3])}",
            }
        )
    headings = [line[3:].strip() for line in content.splitlines() if line.startswith("## ")]
    malformed = [
        heading
        for heading in headings
        if len(heading) > 42
        or heading.endswith(("...", "……"))
        or re.search(r"(?:https?://|www\.|\.(?:com|cn|net|org)(?:/|$))", heading, flags=re.I)
    ]
    if malformed:
        findings.append(
            {
                "type": "source_heading",
                "message": "小标题使用了来源标题、网址或截断的搜索摘要",
            }
        )
    if len(headings) > 6:
        findings.append({"type": "fragmented_structure", "message": f"全文有 {len(headings)} 个小标题，叙事被切得过碎"})
    return findings


def _extract_section_bodies(content: str) -> list[str]:
    sections: list[str] = []
    current_body: list[str] = []
    in_section = False
    for line in content.splitlines():
        if line.startswith("## "):
            if in_section and current_body:
                sections.append("\n".join(current_body).strip())
            current_body = []
            in_section = True
            continue
        if in_section:
            current_body.append(line)
    if in_section and current_body:
        sections.append("\n".join(current_body).strip())
    return sections


class ReviewOutput(BaseModel):
    """Structured article review payload."""

    passed: bool = Field(description="Whether the draft passes review")
    score: int = Field(description="Article review score from 0 to 100")
    findings: list[dict[str, str]] = Field(default_factory=list, description="Review findings")
    revision_guidance: list[str] = Field(default_factory=list, description="Specific revision guidance")


def _fallback_review(draft: dict[str, Any], evidence_pack: dict[str, Any] | None = None) -> ReviewOutput:
    content = str(draft.get("content") or "")
    findings = _structural_findings(content)
    pack = dict(evidence_pack or {})
    research_gaps = list(pack.get("research_gaps") or [])
    quality_summary = dict(pack.get("quality_summary") or {})
    opener = content.split("\n\n## ", 1)[0].strip()
    section_bodies = _extract_section_bodies(content)
    needs_boundary = bool(pack.get("research_gaps") or pack.get("risk_points"))
    boundary_signals = ("不确定", "仍需", "尚无", "证据不足", "还不能", "有待验证", "可能")
    if needs_boundary and not any(signal in content for signal in boundary_signals):
        findings.append({"type": "evidence_boundary", "message": "evidence limitations are not stated near uncertain claims"})
    if opener and any(opener.startswith(prefix) for prefix in _GENERIC_OPENER_PREFIXES):
        findings.append({"type": "opener", "message": "opening hook is generic and reads like a roadmap"})
    if section_bodies and any(len("".join(body.split())) < 80 for body in section_bodies):
        findings.append({"type": "density", "message": "section body is too thin and lacks paragraph development"})
    if "missing_data_evidence" in research_gaps or "missing_high_confidence_fact" in research_gaps:
        findings.append({"type": "evidence", "message": "insufficient evidence coverage for key conclusions"})
    if int(quality_summary.get("high_confidence_items") or 0) <= 0 and research_gaps:
        findings.append({"type": "evidence", "message": "high-confidence evidence is still missing"})
    score = 85 if not findings else 68
    revision_guidance: list[str] = []
    if any(item["type"] == "evidence_boundary" for item in findings):
        revision_guidance.append("在相关判断附近说明证据限制或验证条件，不必另设固定章节")
    if any(item["type"] == "opener" for item in findings):
        revision_guidance.append("重写开头钩子，先给判断或冲突点，不要用本文将从这类空话开场")
    if any(item["type"] == "density" for item in findings):
        revision_guidance.append("扩写信息不足的叙事节点并补上自然过渡；不要为了达成固定段落数机械拆分")
    if any(item["type"] == "evidence" for item in findings):
        revision_guidance.append("补充官方或数据证据，并交代当前证据边界")
    if any(item["type"] == "planning_language" for item in findings):
        revision_guidance.append("删除所有编辑备注和写作指令，改写为读者可以直接阅读的完整叙述")
    if any(item["type"] in {"source_heading", "fragmented_structure"} for item in findings):
        revision_guidance.append("按观点聚合素材并重写小标题，不要让来源数量决定章节数量")
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


async def review_article_draft_node(state: WorkflowState) -> dict[str, Any]:
    """Run a structured review over the generated draft."""
    writing_state = dict(state.get("writing_state") or {})
    draft = dict(writing_state.get("draft") or {})
    research_state = dict(state.get("research_state") or {})
    evidence_pack = dict(research_state.get("evidence_pack") or {})
    planning_state = dict(state.get("planning_state") or {})

    system_prompt = (
        "You are a Chinese editorial reviewer. "
        "Review the draft for narrative effectiveness, evidence support, and clarity. "
        "Do not require a fixed framework, section count, section order, or ritual risk section. "
        "Fail any draft that exposes planning instructions or uses raw source titles, URLs, or one section per search result. "
        "Check whether the article answers one central question and whether claims, evidence, explanation, and reader relevance form a coherent chain. "
        "Return concise findings and concrete revision guidance. "
        "Keep the output small: at most five findings and at most five short guidance items."
    )
    human_prompt = (
        "topic:\n{topic}\n\n"
        "article_type:\n{article_type}\n\n"
        "draft_title:\n{title}\n\n"
        "draft_content:\n{content}\n\n"
        "evidence_pack:\n{evidence_pack}\n"
    )
    prompt = ChatPromptTemplate.from_messages([("system", system_prompt), ("human", human_prompt)])
    chain, retry_factory = structured_chain(
        prompt,
        stage="review_article_draft",
        schema=ReviewOutput,
        temperature=0.2,
    )

    if chain is None:
        # No model configured: fall back to the rule-based review.
        review = _fallback_review(draft, evidence_pack)
        writing_state["review_findings"] = review.findings
        writing_state["revision_guidance"] = review.revision_guidance
        writing_state["article_review"] = {"passed": review.passed, "score": review.score}
        writing_state["review_degraded_reason"] = "no_model_configured"
        return {
            "status": "running",
            "current_skill": "review_article_draft",
            "progress": 60,
            "writing_state": writing_state,
        }

    payload = {
        "topic": str(state.get("task_brief", {}).get("topic") or state.get("keywords") or ""),
        "article_type": dict(planning_state.get("article_type") or {}),
        "title": str(draft.get("title") or ""),
        "content": str(draft.get("content") or ""),
        "evidence_pack": _build_evidence_summary(evidence_pack),
    }
    model_ctx = stage_context("review_article_draft", structured_output="ReviewOutput")
    log_model_request(
        logger,
        task_id=str(state.get("task_id") or ""),
        skill="review_article_draft",
        context=model_ctx,
        request=payload,
    )

    try:
        result = await invoke_structured(
            chain,
            payload,
            stage="review_article_draft",
            build_retry_chain=retry_factory,
        )
        if isinstance(result, ReviewOutput):
            review = result
        else:
            review = ReviewOutput(**dict(result))
        structural_findings = _structural_findings(str(draft.get("content") or ""))
        if structural_findings:
            existing_types = {item.get("type") for item in review.findings}
            review.findings.extend(item for item in structural_findings if item.get("type") not in existing_types)
            review.passed = False
            review.score = min(review.score, 55)
            if any(item["type"] == "planning_language" for item in structural_findings):
                review.revision_guidance.append("删除所有编辑备注和写作指令，改写为读者可以直接阅读的正文")
            if any(item["type"] in {"source_heading", "fragmented_structure"} for item in structural_findings):
                review.revision_guidance.append("按观点聚合素材，重写或合并来源驱动的小标题")
        log_model_response(
            logger,
            task_id=str(state.get("task_id") or ""),
            skill="review_article_draft",
            context=model_ctx,
            response=review.model_dump(),
        )
    except Exception as exc:  # noqa: BLE001
        degraded_reason = getattr(exc, "reason", "") or "error"
        logger.warning(
            "review_article_draft_fallback",
            task_id=str(state.get("task_id") or ""),
            degraded_reason=degraded_reason,
            error=str(exc),
            exc_info=True,
        )
        writing_state["review_degraded_reason"] = degraded_reason
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
