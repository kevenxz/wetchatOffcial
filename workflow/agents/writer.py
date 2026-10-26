"""Compose article draft from blueprint and evidence pack."""
from __future__ import annotations

import re
from typing import Any

import structlog
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from workflow.model_factory import invoke_structured, model_context as stage_context, structured_chain
from workflow.model_logging import log_model_request, log_model_response
from workflow.state import WorkflowState
from workflow.utils.draft_quality import (
    PLANNING_LANGUAGE as _PLANNING_LANGUAGE,
    classify_violations,
    draft_quality_violations,
    normalize_draft_content,
    safe_heading as _safe_heading,
)
from workflow.utils.headings import subject_from_claim

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
    for label, items in (
        ("key_facts", evidence_pack.get("key_facts") or []),
        ("allowed_claims", evidence_pack.get("allowed_claims") or []),
        ("forbidden_claims", evidence_pack.get("forbidden_claims") or []),
        ("citations", evidence_pack.get("citations") or []),
    ):
        if not items:
            continue
        values: list[str] = []
        for item in list(items)[:5]:
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


_PLANNING_LANGUAGE = (
    "这一节要解决的问题",
    "把这条线索放进正文",
    "放到微信公众号语境",
    "参考线索：",
    "目前可用资料",
    "本节目标",
    "这一部分将",
)


def _build_section_body(section: dict[str, Any], topic: str, evidence_pack: dict[str, Any], index: int) -> str:
    fallback_titles = ("先确认发生了什么", "变化背后的逻辑", "放进真实场景再看", "仍需验证的变量")
    title = _safe_heading(_section_title(section), fallback_titles[min(index, len(fallback_titles) - 1)])
    points = _section_points(section, evidence_pack, index)
    shape = str(section.get("shape") or "").strip()
    lines = [f"## {title}"]
    if points:
        lines.append(points[0].rstrip("。") + "。")
        if len(points) > 1:
            lines.append(
                points[1].rstrip("。")
                + f"。放在“{title}”这个判断下，两条信息至少说明变化并非孤立事件，但它们是否构成稳定趋势，仍取决于后续数据能否持续印证。"
            )
        interpretation = {
            "evidence": "这些材料先划出了事实边界：哪些变化已经发生，哪些只是由现象延伸出的推断。把两者分开，后面的判断才不会建立在错位的前提上。",
            "drivers": "原因分析需要继续追问变化如何传导到成本、选择和竞争关系。只有出现连续的作用链条，相关因素才可能是驱动力，而不只是同时发生。",
            "case": "案例的价值在于展示变化如何进入真实决策，但单个样本不能代表整体。更可靠的观察，是看相似结果能否在不同用户和场景中重复出现。",
            "tension": "相反信号并不会削弱文章，反而能说明判断成立的条件。把这些条件说清楚，读者才能知道何时需要坚持、修正或放弃当前结论。",
            "risks": "相反信号并不会削弱文章，反而能说明判断成立的条件。把这些条件说清楚，读者才能知道何时需要坚持、修正或放弃当前结论。",
        }.get(shape, "真正值得关注的不是消息本身，而是它改变了谁的选择、成本和判断标准。把变化放回具体决策场景，才能分辨短期噪声与长期信号。")
        lines.append(interpretation)
    else:
        lines.append(f"围绕{topic}，现有公开信息只能确认变化正在出现，尚不足以推出统一结论。")
        lines.append("在更多数据出现前，更稳妥的判断是保留分歧，并明确什么新证据会让当前判断成立或失效。")
    if shape in {"risks", "tension", "validation"} or "风险" in title or "验证" in title:
        lines.append("单一来源只能提供观察线索，未经多源确认的数据不应被写成确定结论。接下来需要观察的，是结果能否跨时间、跨场景重复出现。")
    else:
        closing_by_shape = {
            "evidence": "下一步应核对来源、时间和口径，确认这些事实是否指向同一种变化。",
            "drivers": "判断驱动力是否成立，要看行为变化能否先于结果出现，并在更多样本中持续。",
            "case": "读者可以把案例当作检验框架，而不是可以直接复制的标准答案。",
        }
        lines.append(closing_by_shape.get(shape, "判断这件事不能只看曝光和表态，还要看实际使用、交付结果或行为变化是否同步发生。"))
    return "\n\n".join(lines)


def _draft_quality_violations(draft: DraftOutput, article_length: str = "medium") -> list[str]:
    """Return quality violations for a draft (delegates to the shared rules)."""
    return draft_quality_violations(str(draft.content or ""), article_length)


def _is_thin_draft(draft: DraftOutput, outline_result: dict[str, Any]) -> bool:
    return bool(_draft_quality_violations(draft))


def _repair_draft(
    draft: DraftOutput,
    article_length: str,
) -> tuple[DraftOutput, list[str], list[str]]:
    """Repair mechanically fixable violations locally.

    Returns the repaired draft, the applied fix names, and the violations that
    still need content-level work (which may warrant a model call).
    """
    original_violations = _draft_quality_violations(draft, article_length)
    if not original_violations:
        return draft, [], []

    _mechanical, _content = classify_violations(original_violations)
    if not _mechanical:
        return draft, [], original_violations

    normalized_content, fixes = normalize_draft_content(str(draft.content or ""))
    if not fixes:
        return draft, [], original_violations

    repaired = DraftOutput(
        title=draft.title,
        alt_titles=list(draft.alt_titles),
        content=normalized_content,
        summary=draft.summary,
    )
    return repaired, fixes, _draft_quality_violations(repaired, article_length)


def _fallback_heading(claim: str, neutral: str, used: set[str]) -> str:
    """Prefer a heading derived from the claim; fall back to a neutral label."""
    subject = subject_from_claim(claim)
    for candidate in (subject, neutral):
        if candidate and candidate not in used and len(candidate) <= 42:
            return candidate
    return neutral


def _build_fallback_draft(
    topic: str,
    blueprint: dict[str, Any],
    evidence_pack: dict[str, Any] | None = None,
    viral_strategy: dict[str, Any] | None = None,
    outline_result: dict[str, Any] | None = None,
) -> DraftOutput:
    """Deterministic last-resort draft.

    Only used when no model is configured or the structured call failed. Section
    headings are derived from the evidence itself, so two different stories do not
    produce the same outline.
    """
    evidence_pack = dict(evidence_pack or {})
    viral_strategy = dict(viral_strategy or {})
    outline_result = dict(outline_result or blueprint.get("outline_result") or {})
    sections = list(outline_result.get("outline") or blueprint.get("sections") or [])[:5]
    title_candidates = list(
        outline_result.get("title_candidates")
        or viral_strategy.get("title_hypotheses")
        or blueprint.get("title_candidates")
        or []
    )
    title = str(title_candidates[0] if title_candidates else blueprint.get("thesis") or topic or "未命名主题").strip()
    opening_hook = str(viral_strategy.get("opening_hook") or "").strip()
    if any(phrase in opening_hook for phrase in _PLANNING_LANGUAGE) or len(opening_hook) < 24:
        opening_hook = ""
    thesis = str(outline_result.get("thesis") or blueprint.get("thesis") or "").strip()
    intro = opening_hook or (
        f"关于{topic}，最容易得到的是一串热闹的消息，最难得到的是一个经得起核对的判断。"
        f"{thesis or '现有信息显示变化已经出现，但它的影响范围和持续时间仍需结合事实判断。'}\n\n"
        "对读者来说，关键不是记住又发生了一件事，而是看清这件事会改变哪些选择：哪些信号已经落地，哪些仍停留在预期里。"
    )
    section_blocks = [
        _build_section_body(dict(section), topic, evidence_pack, index)
        for index, section in enumerate(sections)
        if isinstance(section, dict) and _section_title(section)
    ]

    used_headings: set[str] = set()
    if not section_blocks:
        # No outline available: build beats from the evidence, heading each one with
        # its own claim rather than a fixed template label.
        for key, neutral in (
            ("confirmed_facts", "已确认的事实"),
            ("usable_data_points", "关键数据"),
            ("usable_cases", "可用案例"),
            ("risk_points", "风险与反向信号"),
        ):
            items = list(evidence_pack.get(key) or [])
            if not items:
                continue
            claim = _claim_text(items[0])
            heading = _fallback_heading(claim, neutral, used_headings)
            used_headings.add(heading)
            section_blocks.append(f"## {heading}\n\n{claim}")
        if evidence_pack.get("research_gaps"):
            gaps = "；".join(str(item) for item in list(evidence_pack["research_gaps"])[:3])
            boundary_heading = f"{subject_from_claim(topic, limit=16) or topic}的结论边界"
            if boundary_heading not in used_headings:
                section_blocks.append(f"## {boundary_heading}\n\n{gaps}")
        if not section_blocks:
            section_blocks.append(
                f"## 目前能确认的信号\n\n{topic}已经值得观察，但现有公开资料不足以支撑统一结论。"
                "与其套用固定分析框架，更重要的是区分已确认事实和仍待验证的判断。"
            )

    closing = (
        f"因此，判断{topic}不必急着追求一个终局答案。更有用的做法，是记住当前最可靠的证据，"
        "同时盯住接下来会改变判断的指标：真实使用、交付结果、持续数据，以及不同来源能否相互印证。"
    )
    synthesis = (
        f"把现有线索放回{topic}这个问题里，重要的是看清事实之间能否形成因果链。"
        "如果事实、数据和案例指向同一方向，判断才可以更明确；如果它们彼此冲突，文章就应保留这种张力，而不是为了结构完整强行收束。\n\n"
        "对读者真正有用的信息，往往来自这种取舍：哪些变化会影响自己的决策，哪些只是短期噪声，以及接下来出现什么新证据时需要重新修正判断。"
    )
    content = "\n\n".join(
        [
            intro,
            *section_blocks,
            synthesis,
            closing,
        ]
    )
    summary = str(outline_result.get("reader_value") or blueprint.get("reader_value") or f"围绕{topic}提炼事实、判断和风险边界。")

    # Alternate titles come from the real candidates; failing that, from the
    # material itself — never from a fixed sentence template.
    alt_titles: list[str] = []
    for candidate in title_candidates[1:3]:
        text = str(candidate).strip()
        if text and text != title:
            alt_titles.append(text)
    if not alt_titles:
        primary_items = (
            list(evidence_pack.get("confirmed_facts") or [])
            or list(evidence_pack.get("usable_data_points") or [])
        )
        if primary_items:
            derived = subject_from_claim(_claim_text(primary_items[0]), limit=24)
            if derived and derived != title:
                alt_titles.append(derived)

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
    viral_strategy = dict(state.get("viral_state", {}).get("strategy") or {})
    topic = str(selected_topic.get("title") or task_brief.get("topic") or state.get("keywords") or "").strip()

    article_length = str(config_snapshot.get("content_template", {}).get("article_length") or "medium")
    previous_draft = dict((state.get("writing_state") or {}).get("draft") or {})
    revision_guidance = list(revision_brief.get("guidance") or [])
    is_revision = bool(revision_brief) and bool(previous_draft.get("content"))
    draft_stage = "compose_draft_revision" if is_revision else "compose_draft"

    system_prompt = (
        "You are a Chinese content drafting agent. "
        "Write a complete WeChat public account article, not a report outline and not a planning note. "
        "Write a clean Markdown article draft from the editorial goal and evidence pack. "
        "The content type is explicitly a WeChat public account article: it needs a strong title, opening hook, readable H2 subtitles, complete paragraphs, transitions, and a clear ending. "
        "Blueprint sections and source_driven_framework are optional narrative hypotheses, never a mandatory outline. "
        "Treat editorial_contract as the coherence backbone: answer one central question, sustain one core thesis, and deliver the promised reader takeaway. "
        "Each developed narrative beat should connect a claim, supporting evidence, explanation, and reader implication; do not print these labels. "
        "You may merge, reorder, rename, replace, or omit suggested sections, and may write an essay-like article without H2 headings when that reads better. "
        "Refine section headings freely when a different phrasing or structure makes the argument stronger. "
        "If selected_skill is provided, follow its expertise, tone, evidence_policy, writing_constraints, and title guidance; treat its framework only as inspiration. "
        "The viral_strategy is the editorial goal contract: honour its audience tension, core promise, novelty angle, emotional arc and share trigger without using clickbait. "
        "Only must_use_facts, evidence boundaries, forbidden claims, and the core reader promise are hard constraints. "
        "Do not copy a generic template and do not preserve a planned section merely because it exists in the blueprint. "
        "Never turn each source into a section. Never use a source title, website name, URL, or search snippet as an H2 heading. "
        "Never expose planning language such as '这一节要解决的问题', '参考线索', '本节目标', or instructions about how to write the article. "
        "Every major claim must be grounded in searched source signals or explicitly qualified. "
        "Produce a publication-ready title, two alternative title candidates, a concise summary, and a strong opening hook paragraph before the first H2 section. "
        "Avoid generic opener language such as '本文将从...展开' or other empty roadmap sentences. "
        "Use natural transitions between the opener and the first section, and between sections when the argument turns. "
        "Use as many or as few sections as the narrative needs; avoid single-sentence fragments when a developed argument is required. "
        "Keep the language concrete. Evidence limitations may appear beside the relevant claim or in a dedicated passage; never add a ritual risk section. "
        "If previous_draft and draft_violations are provided, rewrite the draft into a complete article and eliminate every listed violation. "
        "If ordinary revision guidance is provided, revise only the weak parts instead of changing the whole structure."
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
        "viral_strategy:\n{viral_strategy}\n\n"
        "revision_brief:\n{revision_brief}\n\n"
        "previous_draft:\n{previous_draft}\n\n"
        "draft_violations:\n{draft_violations}\n"
    )

    prompt = ChatPromptTemplate.from_messages([("system", system_prompt), ("human", human_prompt)])
    chain, retry_factory = structured_chain(
        prompt,
        stage=draft_stage,
        schema=DraftOutput,
        temperature=0.45,
    )

    if chain is None:
        # No model configured: ship the deterministic draft, but say so explicitly.
        fallback = _build_fallback_draft(topic, blueprint, evidence_pack, viral_strategy, outline_result)
        fallback_violations = _draft_quality_violations(fallback, article_length)
        return {
            "status": "running",
            "current_skill": "compose_draft",
            "progress": 54,
            "writing_state": {
                "draft": fallback.model_dump(),
                "review_findings": [],
                "outline_result": outline_result,
                "draft_generation_mode": "fallback",
                "draft_quality_violations": fallback_violations,
                "draft_degraded_reason": "no_model_configured",
            },
            "generated_article": {
                "title": fallback.title,
                "alt_titles": fallback.alt_titles,
                "summary": fallback.summary,
                "content": fallback.content,
            },
        }

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
        "viral_strategy": viral_strategy,
        # A revision must see its own previous draft, otherwise the model rewrites
        # the article from scratch and the revision costs a full generation.
        "previous_draft": previous_draft if is_revision else {},
        "draft_violations": revision_guidance if is_revision else [],
    }
    model_ctx = stage_context(draft_stage, structured_output="DraftOutput")
    log_model_request(
        logger,
        task_id=str(state.get("task_id") or ""),
        skill="compose_draft",
        context=model_ctx,
        request=payload,
    )

    draft_generation_mode = "model_revision" if is_revision else "model"
    draft_quality_violations: list[str] = []
    normalization_fixes: list[str] = []
    degraded_reason = ""
    try:
        result = await invoke_structured(
            chain,
            payload,
            stage=draft_stage,
            build_retry_chain=retry_factory,
        )
        if isinstance(result, DraftOutput):
            draft = result
        else:
            draft = DraftOutput(**dict(result))

        # Repair mechanical violations locally before spending a second generation.
        draft, normalization_fixes, draft_quality_violations = _repair_draft(draft, article_length)
        if normalization_fixes:
            logger.info(
                "compose_draft_normalized",
                task_id=str(state.get("task_id") or ""),
                fixes=normalization_fixes,
                remaining_violations=draft_quality_violations,
            )

        if draft_quality_violations:
            logger.info(
                "compose_draft_repair",
                task_id=str(state.get("task_id") or ""),
                violations=draft_quality_violations,
            )
            repair_payload = {
                **payload,
                "previous_draft": draft.model_dump(),
                "draft_violations": draft_quality_violations,
            }
            repaired_result = await invoke_structured(
                chain,
                repair_payload,
                stage=draft_stage,
                build_retry_chain=retry_factory,
            )
            draft = repaired_result if isinstance(repaired_result, DraftOutput) else DraftOutput(**dict(repaired_result))
            draft, repair_fixes, draft_quality_violations = _repair_draft(draft, article_length)
            normalization_fixes = [*normalization_fixes, *repair_fixes]
            draft_generation_mode = f"{draft_generation_mode}_repair"
        if draft_quality_violations:
            logger.warning(
                "compose_draft_repair_failed",
                task_id=str(state.get("task_id") or ""),
                violations=draft_quality_violations,
            )
            draft = _build_fallback_draft(topic, blueprint, evidence_pack, viral_strategy, outline_result)
            draft_generation_mode = "fallback"
            degraded_reason = "content_level_violations"
            draft_quality_violations = _draft_quality_violations(draft, article_length)
        log_model_response(
            logger,
            task_id=str(state.get("task_id") or ""),
            skill="compose_draft",
            context=model_ctx,
            response=draft.model_dump(),
        )
    except Exception as exc:  # noqa: BLE001
        degraded_reason = getattr(exc, "reason", "") or "error"
        logger.warning(
            "compose_draft_fallback",
            task_id=str(state.get("task_id") or ""),
            degraded_reason=degraded_reason,
            error=str(exc),
            exc_info=True,
        )
        draft = _build_fallback_draft(topic, blueprint, evidence_pack, viral_strategy, outline_result)
        draft_generation_mode = "fallback"
        draft_quality_violations = _draft_quality_violations(draft, article_length)

    writing_state_payload: dict[str, Any] = {
        "draft": draft.model_dump(),
        "review_findings": [],
        "revision_brief": {},
        "outline_result": outline_result,
        "draft_generation_mode": draft_generation_mode,
        "draft_quality_violations": draft_quality_violations,
        "draft_normalization": normalization_fixes,
    }
    if degraded_reason:
        writing_state_payload["draft_degraded_reason"] = degraded_reason

    return {
        "status": "running",
        "current_skill": "compose_draft",
        "progress": 54,
        "writing_state": writing_state_payload,
        "generated_article": {
            "title": draft.title,
            "alt_titles": draft.alt_titles,
            "summary": draft.summary,
            "content": draft.content,
        },
    }
