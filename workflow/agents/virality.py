"""Plan and critique the article's distribution potential.

The two nodes in this module deliberately use different roles.  The strategist
defines the editorial bet before drafting; the critic evaluates the produced
artifact afterwards.  Keeping those roles separate prevents the writer from
grading its own work and gives the quality gate a stable, inspectable contract.
"""
from __future__ import annotations

import re
from typing import Any

import structlog
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from workflow.model_factory import build_chat_model, llm_slot, model_context as stage_context
from workflow.model_logging import log_model_request, log_model_response
from workflow.state import WorkflowState

logger = structlog.get_logger(__name__)

DIMENSION_WEIGHTS = {
    "headline": 0.18,
    "hook": 0.18,
    "novelty": 0.15,
    "resonance": 0.14,
    "shareability": 0.15,
    "credibility": 0.12,
    "readability": 0.08,
}


class ViralStrategyOutput(BaseModel):
    """The editorial hypothesis that every downstream agent must honour."""

    audience_tension: str = Field(description="The reader's unresolved tension or anxiety")
    core_promise: str = Field(description="The concrete value delivered after reading")
    novelty_angle: str = Field(description="The non-obvious angle that differentiates the article")
    emotional_arc: str = Field(description="The intended emotional movement from opening to ending")
    social_currency: str = Field(description="Why sharing this article makes the reader look useful or insightful")
    share_trigger: str = Field(description="A specific moment or conclusion worth forwarding")
    opening_hook: str = Field(description="A sharp opening-hook direction, not a finished generic introduction")
    title_hypotheses: list[str] = Field(default_factory=list, description="Three distinct title hypotheses")
    avoid_patterns: list[str] = Field(default_factory=list, description="Cliches or overclaims to avoid")


class ViralReviewOutput(BaseModel):
    """A measurable reflection contract used by the quality gate."""

    headline: int = Field(ge=0, le=100)
    hook: int = Field(ge=0, le=100)
    novelty: int = Field(ge=0, le=100)
    resonance: int = Field(ge=0, le=100)
    shareability: int = Field(ge=0, le=100)
    credibility: int = Field(ge=0, le=100)
    readability: int = Field(ge=0, le=100)
    findings: list[dict[str, str]] = Field(default_factory=list)
    revision_guidance: list[str] = Field(default_factory=list)


def _fallback_strategy(topic: str, task_brief: dict[str, Any]) -> ViralStrategyOutput:
    audience = str(task_brief.get("audience") or task_brief.get("primary_audience") or "关心这一主题的读者")
    return ViralStrategyOutput(
        audience_tension=f"{audience}已经看到{topic}的热度，但还不知道它会怎样影响自己的判断与行动",
        core_promise=f"用可核验的事实拆开{topic}，给出一条从变化信号到行动选择的判断链",
        novelty_angle=f"不复述{topic}本身，重点解释被热度遮住的利益变化、证据边界和下一步",
        emotional_arc="从反常识或冲突切入，经过证据确认与风险降温，最后落到可执行判断",
        social_currency="转发者能够帮助同事或朋友更快看懂变化，而不是只传递一条新闻",
        share_trigger="用一句可复述的判断总结这件事对普通读者意味着什么",
        opening_hook=f"先指出{topic}中最容易被误读的一点，再给出与直觉不同但可验证的判断",
        title_hypotheses=[
            f"{topic}真正值得关注的，不是热度",
            f"别急着下结论：{topic}背后的信号与边界",
            f"看懂{topic}，关键是这条被忽略的变化",
        ],
        avoid_patterns=["震惊体和无依据的确定性承诺", "本文将从三个方面展开", "只复述事件经过"],
    )


async def design_viral_strategy_node(state: WorkflowState) -> dict[str, Any]:
    """Create the editorial distribution hypothesis before outlining."""
    task_brief = dict(state.get("task_brief") or {})
    selected_topic = dict(state.get("selected_topic") or {})
    research_state = dict(state.get("research_state") or {})
    evidence_pack = dict(research_state.get("evidence_pack") or {})
    topic = str(selected_topic.get("title") or task_brief.get("topic") or state.get("keywords") or "").strip()
    fallback = _fallback_strategy(topic, task_brief)
    llm = build_chat_model(stage="design_viral_strategy", max_tokens=700, temperature=0.45)

    if llm is None:
        strategy = fallback
    else:
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a Chinese WeChat distribution strategist. Define an evidence-safe editorial bet before writing. "
                    "Optimise for qualified clicks, reading completion, saves and meaningful shares, never clickbait. "
                    "Find one reader tension, one concrete promise and one non-obvious angle. Keep all claims within the evidence boundary.",
                ),
                (
                    "human",
                    "topic:\n{topic}\n\ntask_brief:\n{task_brief}\n\nselected_topic:\n{selected_topic}\n\n"
                    "evidence_quality:\n{evidence_quality}\n\naccount_profile:\n{account_profile}",
                ),
            ]
        )
        chain = prompt | llm.with_structured_output(ViralStrategyOutput)
        payload = {
            "topic": topic,
            "task_brief": task_brief,
            "selected_topic": selected_topic,
            "evidence_quality": dict(evidence_pack.get("quality_summary") or {}),
            "account_profile": dict(state.get("config_snapshot", {}).get("account_profile") or {}),
        }
        context = stage_context("design_viral_strategy", structured_output="ViralStrategyOutput")
        log_model_request(logger, task_id=str(state.get("task_id") or ""), skill="design_viral_strategy", context=context, request=payload)
        try:
            async with llm_slot():
                result = await chain.ainvoke(payload)
            strategy = result if isinstance(result, ViralStrategyOutput) else ViralStrategyOutput(**dict(result))
            log_model_response(
                logger,
                task_id=str(state.get("task_id") or ""),
                skill="design_viral_strategy",
                context=context,
                response=strategy.model_dump(),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("design_viral_strategy_fallback", task_id=str(state.get("task_id") or ""), error=str(exc))
            strategy = fallback

    return {
        "status": "running",
        "current_skill": "design_viral_strategy",
        "progress": 48,
        "viral_state": {"strategy": strategy.model_dump(), "review": {}},
    }


def _opening(content: str) -> str:
    return content.split("\n## ", 1)[0].strip()


def _clamp(value: int) -> int:
    return max(0, min(value, 100))


def _heuristic_review(
    draft: dict[str, Any],
    strategy: dict[str, Any],
    evidence_pack: dict[str, Any],
) -> ViralReviewOutput:
    title = str(draft.get("title") or "").strip()
    content = str(draft.get("content") or "").strip()
    opener = _opening(content)
    paragraphs = [item.strip() for item in re.split(r"\n\s*\n", content) if item.strip() and not item.startswith("## ")]
    quality_summary = dict(evidence_pack.get("quality_summary") or {})
    high_confidence = int(quality_summary.get("high_confidence_items") or 0)
    citations = len(list(evidence_pack.get("citations") or []))

    headline = 58
    if 10 <= len(title) <= 32:
        headline += 18
    if any(marker in title for marker in ("？", "：", "背后", "真正", "为什么", "如何", "别")):
        headline += 10
    if not any(marker in title for marker in ("震惊", "必看", "疯了", "100%")):
        headline += 8

    hook = 45
    if 45 <= len(opener) <= 260:
        hook += 24
    if any(marker in opener for marker in ("但", "却", "真正", "问题", "变化", "不是")):
        hook += 14
    if not opener.startswith(("本文将", "接下来", "这篇文章")):
        hook += 12

    novelty = 58 + (16 if strategy.get("novelty_angle") else 0)
    resonance = 55 + (12 if strategy.get("audience_tension") else 0) + (12 if strategy.get("core_promise") else 0)
    shareability = 52
    if any(marker in content for marker in ("意味着", "判断", "建议", "下一步", "可以", "值得")):
        shareability += 18
    if strategy.get("share_trigger") or strategy.get("social_currency"):
        shareability += 12
    credibility = 48 + min(high_confidence * 8, 28) + min(citations * 3, 18)
    if evidence_pack.get("research_gaps"):
        credibility -= 8
    readability = 58
    if paragraphs and sum(len(item) for item in paragraphs) / len(paragraphs) <= 220:
        readability += 27

    scores = {
        "headline": _clamp(headline),
        "hook": _clamp(hook),
        "novelty": _clamp(novelty),
        "resonance": _clamp(resonance),
        "shareability": _clamp(shareability),
        "credibility": _clamp(credibility),
        "readability": _clamp(readability),
    }
    findings: list[dict[str, str]] = []
    guidance: list[str] = []
    labels = {
        "headline": "标题点击力",
        "hook": "开篇留存",
        "novelty": "观点新颖度",
        "resonance": "读者共鸣",
        "shareability": "分享动机",
        "credibility": "证据可信度",
        "readability": "阅读流畅度",
    }
    fixes = {
        "headline": "重写主标题：保留真实信息增量，同时加入明确冲突或读者收益",
        "hook": "重写前 120 字：先给反常识判断或冲突，不要从背景介绍开始",
        "novelty": "把传播策略中的非显然角度写成全文主论点，并删掉新闻复述",
        "resonance": "明确点出这件事与目标读者的损失、机会或选择有什么关系",
        "shareability": "增加一句读者愿意转发给特定对象的可复述结论",
        "credibility": "为关键判断补充高可信来源，并主动声明未被证实的边界",
        "readability": "按阅读节奏拆分长段并补充过渡；是否使用小标题由叙事本身决定",
    }
    for key, value in scores.items():
        if value < 75:
            findings.append({"type": key, "message": f"{labels[key]}仅 {value} 分"})
            guidance.append(fixes[key])
    return ViralReviewOutput(**scores, findings=findings, revision_guidance=guidance)


def _review_payload(review: ViralReviewOutput, threshold: int) -> dict[str, Any]:
    dimensions = {key: int(getattr(review, key)) for key in DIMENSION_WEIGHTS}
    score = round(sum(dimensions[key] * weight for key, weight in DIMENSION_WEIGHTS.items()))
    return {
        "passed": score >= threshold,
        "score": score,
        "threshold": threshold,
        "dimensions": dimensions,
        "findings": review.findings,
        "revision_guidance": review.revision_guidance,
    }


async def review_viral_potential_node(state: WorkflowState) -> dict[str, Any]:
    """Use an independent critic to estimate distribution potential."""
    viral_state = dict(state.get("viral_state") or {})
    strategy = dict(viral_state.get("strategy") or {})
    writing_state = dict(state.get("writing_state") or {})
    draft = dict(writing_state.get("draft") or {})
    evidence_pack = dict(state.get("research_state", {}).get("evidence_pack") or {})
    review_policy = dict(state.get("config_snapshot", {}).get("review_policy") or {})
    threshold = int(review_policy.get("viral_threshold") or 78)
    fallback = _heuristic_review(draft, strategy, evidence_pack)
    llm = build_chat_model(stage="review_viral_potential", max_tokens=700, temperature=0.15)

    if llm is None:
        review = fallback
    else:
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are an independent Chinese WeChat growth editor. Score the finished draft, not the plan. "
                    "Judge qualified headline appeal, first-screen retention, non-obvious insight, reader resonance, "
                    "meaningful share motivation, evidence credibility and mobile readability. Never reward clickbait or unsupported certainty.",
                ),
                (
                    "human",
                    "strategy:\n{strategy}\n\ntitle:\n{title}\n\ncontent:\n{content}\n\nevidence_quality:\n{evidence_quality}",
                ),
            ]
        )
        chain = prompt | llm.with_structured_output(ViralReviewOutput)
        payload = {
            "strategy": strategy,
            "title": str(draft.get("title") or ""),
            "content": str(draft.get("content") or ""),
            "evidence_quality": dict(evidence_pack.get("quality_summary") or {}),
        }
        context = stage_context("review_viral_potential", structured_output="ViralReviewOutput")
        log_model_request(
            logger,
            task_id=str(state.get("task_id") or ""),
            skill="review_viral_potential",
            context=context,
            request=payload,
        )
        try:
            async with llm_slot():
                result = await chain.ainvoke(payload)
            review = result if isinstance(result, ViralReviewOutput) else ViralReviewOutput(**dict(result))
            log_model_response(
                logger,
                task_id=str(state.get("task_id") or ""),
                skill="review_viral_potential",
                context=context,
                response=review.model_dump(),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("review_viral_potential_fallback", task_id=str(state.get("task_id") or ""), error=str(exc))
            review = fallback

    review_data = _review_payload(review, threshold)
    viral_state["review"] = review_data
    # NOTE: writing_state is deliberately not written here. This node runs
    # concurrently with review_article_draft under the fan-out graph, and two
    # nodes writing the same state key would conflict. Consumers read
    # viral_state["review"] directly.
    return {
        "status": "running",
        "current_skill": "review_viral_potential",
        "progress": 66,
        "viral_state": viral_state,
    }
