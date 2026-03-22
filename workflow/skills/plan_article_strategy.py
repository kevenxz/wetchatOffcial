"""Skill: plan article strategy based on roles, keywords and extracted content."""
from __future__ import annotations

import time

import structlog

from workflow.article_generation import ARTICLE_STRATEGY_LABELS, normalize_generation_config, role_focus_points
from workflow.state import WorkflowState

logger = structlog.get_logger(__name__)


def _infer_strategy(keywords: str, audience_roles: list[str]) -> str:
    text = f"{keywords} {' '.join(audience_roles)}".lower()
    if any(token in text for token in ("vs", "pk", "对比", "评测", "横评", "测评")):
        return "application_review"
    if any(token in text for token in ("原理", "架构", "技术", "源码", "解析", "拆解")):
        return "tech_breakdown"
    if any(token in text for token in ("趋势", "前景", "机会", "投资", "市场", "格局")):
        return "trend_outlook"

    primary_role = audience_roles[0] if audience_roles else ""
    if primary_role in {"开发者"}:
        return "tech_breakdown"
    if primary_role in {"投资者", "企业管理者"}:
        return "trend_outlook"
    return "application_review"


def _title_strategy(strategy: str) -> str:
    if strategy == "tech_breakdown":
        return "标题要突出原理拆解、关键机制或能力边界。"
    if strategy == "application_review":
        return "标题要突出场景体验、效果对比或实用结论。"
    return "标题要突出趋势判断、行业变量和行动窗口。"


def _section_outline(strategy: str, audience_roles: list[str]) -> list[str]:
    if strategy == "tech_breakdown":
        core_section = "## 技术拆解：核心原理与能力边界"
    elif strategy == "application_review":
        core_section = "## 应用评测：场景、效果与体验"
    else:
        core_section = "## 趋势判断：行业走向与关键变量"

    if len(audience_roles) > 1:
        role_section = f"## 多角色视角：{' / '.join(audience_roles)}"
    else:
        role_section = f"## {audience_roles[0]}视角：最该关注什么"

    return [
        "## 开篇：为什么现在值得关注",
        "## 关键信息与背景",
        core_section,
        role_section,
        "## 局限与风险",
        "## 行动建议",
    ]


async def plan_article_strategy_node(state: WorkflowState) -> dict:
    """Build a deterministic article plan before LLM writing."""
    task_id = state["task_id"]
    generation_config = normalize_generation_config(state.get("generation_config"))

    start_time = time.monotonic()
    logger.info(
        "skill_start",
        task_id=task_id,
        skill="plan_article_strategy",
        status="running",
        generation_config=generation_config,
    )

    strategy = generation_config["article_strategy"]
    resolved_strategy = _infer_strategy(state.get("keywords", ""), generation_config["audience_roles"]) if strategy == "auto" else strategy
    audience_roles = generation_config["audience_roles"]
    primary_role = audience_roles[0]
    role_focuses = [
        {
            "role": role,
            "focus_points": role_focus_points(role),
        }
        for role in audience_roles
    ]
    article_plan = {
        "primary_role": primary_role,
        "audience_roles": audience_roles,
        "requested_strategy": strategy,
        "resolved_strategy": resolved_strategy,
        "resolved_strategy_label": ARTICLE_STRATEGY_LABELS.get(resolved_strategy, resolved_strategy),
        "title_strategy": _title_strategy(resolved_strategy),
        "section_outline": _section_outline(resolved_strategy, audience_roles),
        "role_focuses": role_focuses,
        "planned_illustrations": 3,
        "tone": "理性兴奋",
    }

    duration_ms = round((time.monotonic() - start_time) * 1000)
    logger.info(
        "skill_done",
        task_id=task_id,
        skill="plan_article_strategy",
        status="done",
        duration_ms=duration_ms,
        resolved_strategy=resolved_strategy,
        primary_role=primary_role,
    )

    return {
        "status": "running",
        "current_skill": "plan_article_strategy",
        "progress": 60,
        "generation_config": generation_config,
        "article_plan": article_plan,
    }
