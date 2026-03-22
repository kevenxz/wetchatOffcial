"""Infer structured user intent before style and search planning."""
from __future__ import annotations

import time

import structlog

from workflow.article_generation import infer_article_strategy, normalize_generation_config, role_focus_points
from workflow.state import WorkflowState

logger = structlog.get_logger(__name__)


def _build_article_goal(strategy: str, primary_role: str) -> str:
    if primary_role == "投资者":
        return "帮助读者理解市场空间、商业化进展、关键风险与跟踪指标"
    if primary_role == "开发者":
        return "帮助读者理解技术原理、实现方式、能力边界和落地成本"
    if strategy == "application_review":
        return "帮助读者快速判断适用场景、使用门槛和实际效果"
    if strategy == "trend_outlook":
        return "帮助读者判断行业变化、核心变量与下一步行动窗口"
    return "帮助读者快速理解主题背景、关键变化和实际价值"


async def interpret_user_intent_node(state: WorkflowState) -> dict:
    """Resolve a lightweight intent object from topic and generation config."""
    task_id = state["task_id"]
    generation_config = normalize_generation_config(state.get("generation_config"))
    keywords = (state.get("keywords") or "").strip()

    start_time = time.monotonic()
    logger.info(
        "skill_start",
        task_id=task_id,
        skill="interpret_user_intent",
        status="running",
        keywords=keywords,
        generation_config=generation_config,
    )

    requested_strategy = generation_config["article_strategy"]
    audience_roles = generation_config["audience_roles"]
    resolved_strategy = (
        infer_article_strategy(keywords, audience_roles)
        if requested_strategy == "auto"
        else requested_strategy
    )
    primary_role = audience_roles[0]

    user_intent = {
        "topic": keywords,
        "target_roles": audience_roles,
        "primary_role": primary_role,
        "requested_strategy": requested_strategy,
        "resolved_strategy": resolved_strategy,
        "article_goal": _build_article_goal(resolved_strategy, primary_role),
        "core_questions": role_focus_points(primary_role),
        "style_hint": generation_config.get("style_hint", ""),
    }

    duration_ms = round((time.monotonic() - start_time) * 1000)
    logger.info(
        "skill_done",
        task_id=task_id,
        skill="interpret_user_intent",
        status="done",
        duration_ms=duration_ms,
        resolved_strategy=resolved_strategy,
        primary_role=primary_role,
    )

    return {
        "status": "running",
        "current_skill": "interpret_user_intent",
        "progress": 15,
        "generation_config": generation_config,
        "user_intent": user_intent,
    }
