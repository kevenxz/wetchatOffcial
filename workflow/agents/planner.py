"""Planner stage for the redesigned workflow."""
from __future__ import annotations

from typing import Any

import structlog
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from api.store import get_model_config
from workflow.article_skills import list_article_skills, select_article_skill
from workflow.model_logging import build_model_context, log_model_request, log_model_response
from workflow.state import WorkflowState
from workflow.utils.article_type_registry import get_article_type_registry
from workflow.utils.research_contract import (
    build_fallback_search_contract,
    normalize_research_policy,
    normalize_search_contract,
)

logger = structlog.get_logger(__name__)


class QueryPlanItem(BaseModel):
    query: str = Field(description="Search query")
    purpose: str = Field(description="Why this query is needed")
    source_type: str = Field(description="Expected source type")
    priority: int = Field(default=1, ge=1, le=10)


class ResearchContractOutput(BaseModel):
    topic: str
    research_goal: str
    category: str
    search_depth: str
    freshness_window_days: int = 7
    search_questions: list[str] = Field(default_factory=list)
    query_plan: list[QueryPlanItem] = Field(default_factory=list)
    must_have_evidence: list[str] = Field(default_factory=list)
    source_rules: dict[str, list[str]] = Field(default_factory=dict)
    min_source_count: int = 6
    min_authoritative_source_count: int = 1
    min_cross_source_count: int = 3
    require_opposing_view: bool = True
    requires_manual_review: bool = False
    hotspot_verification: dict[str, bool] = Field(default_factory=dict)


def _resolve_article_type(article_goal: str, registry: dict[str, dict[str, Any]]) -> dict[str, Any]:
    lowered = article_goal.lower()
    if any(keyword in article_goal for keyword in ("趋势", "分析", "解读")) or "trend" in lowered:
        return registry["trend_analysis"]
    return registry["hotspot_interpretation"]


def _prioritize_angles(research_state: dict[str, Any]) -> tuple[list[str], list[str]]:
    default_angles = ["fact", "news", "opinion", "case", "data"]
    evidence_pack = dict(research_state.get("evidence_pack") or {})
    research_gaps = list(evidence_pack.get("research_gaps") or [])
    quality_summary = dict(evidence_pack.get("quality_summary") or {})
    source_coverage = dict(quality_summary.get("source_coverage") or {})

    priority_order: list[str] = []
    coverage_targets: list[str] = []

    if "missing_high_confidence_fact" in research_gaps:
        priority_order.append("fact")
        coverage_targets.append("official")
    if "missing_data_evidence" in research_gaps:
        priority_order.append("data")
        coverage_targets.append("dataset")
    if source_coverage and set(source_coverage).issubset({"community", "aggregator", "unknown"}):
        priority_order.extend(["fact", "data"])
        coverage_targets.extend(["official", "dataset"])

    angles: list[str] = []
    for angle in priority_order + default_angles:
        if angle not in angles:
            angles.append(angle)

    deduped_targets: list[str] = []
    for target in coverage_targets:
        if target not in deduped_targets:
            deduped_targets.append(target)
    return angles, deduped_targets


def _thresholds_for_policy(policy: dict[str, Any]) -> dict[str, int]:
    strictness = str(policy.get("strictness") or "standard")
    if strictness == "strict":
        return {"article": 86, "visual": 80, "evidence": 84, "hotspot": 75}
    if strictness == "lenient":
        return {"article": 74, "visual": 68, "evidence": 70, "hotspot": 58}
    return {"article": 80, "visual": 75, "evidence": 80, "hotspot": 70}


def _visual_roles(article_type: dict[str, Any], image_policy: dict[str, Any]) -> list[str]:
    if not image_policy.get("enabled", True):
        return []
    roles: list[str] = []
    if image_policy.get("cover_enabled", True):
        roles.append("cover")
    if image_policy.get("inline_enabled", True):
        preferred = [role for role in article_type.get("visual_preferences", []) if role != "cover"]
        inline_count = int(image_policy.get("inline_count") or 0)
        roles.extend((preferred or ["contextual_illustration"])[:inline_count])
    return roles


def _available_skill_summary() -> list[dict[str, Any]]:
    return [
        {
            "skill_id": skill.get("skill_id"),
            "name": skill.get("name"),
            "description": skill.get("description"),
            "decision_rule": skill.get("decision_rule"),
        }
        for skill in list_article_skills()
    ]


async def _build_ai_search_contract(
    *,
    state: WorkflowState,
    fallback_contract: dict[str, Any],
    selected_skill: dict[str, Any],
    research_policy: dict[str, Any],
) -> dict[str, Any] | None:
    if not state.get("config_snapshot"):
        return None
    text_model_config = get_model_config().text
    if not text_model_config.api_key:
        return None
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "你是 Research Planner，不是 Writer。你的任务是为微信公众号内容生产系统制定高质量搜索计划。"
                "必须判断主题类别、搜索深度、核心研究问题、多角度查询矩阵、证据要求、来源优先级、"
                "不可信来源和是否需要人工审核。财经、军事、社会争议类默认 strict；科技发布至少需要官方来源；"
                "热点类至少需要多源确认。不允许直接生成文章正文。输出必须符合结构化 schema。",
            ),
            (
                "human",
                "topic: {topic}\n"
                "task_brief: {task_brief}\n"
                "selected_hotspot: {selected_hotspot}\n"
                "selected_skill: {selected_skill}\n"
                "research_policy: {research_policy}\n"
                "fallback_contract: {fallback_contract}\n",
            ),
        ]
    )
    llm = ChatOpenAI(
        model=text_model_config.model,
        api_key=text_model_config.api_key,
        base_url=text_model_config.base_url or None,
        temperature=0.2,
    )
    chain = prompt | llm.with_structured_output(ResearchContractOutput)
    payload = {
        "topic": fallback_contract["topic"],
        "task_brief": state.get("task_brief") or {},
        "selected_hotspot": state.get("selected_hotspot") or {},
        "selected_skill": selected_skill,
        "research_policy": research_policy,
        "fallback_contract": fallback_contract,
    }
    context = build_model_context(
        model=text_model_config.model,
        base_url=text_model_config.base_url,
        api_key=text_model_config.api_key,
    )
    log_model_request(logger, task_id=state["task_id"], skill="planner_agent", context=context, request=payload)
    try:
        result = await chain.ainvoke(payload)
        contract = result.model_dump()
        log_model_response(logger, task_id=state["task_id"], skill="planner_agent", context=context, response=contract)
        contract["planner_source"] = "ai"
        return contract
    except Exception as exc:  # noqa: BLE001
        logger.warning("research_planner_ai_failed", task_id=state["task_id"], error=str(exc))
        return None


async def planner_agent_node(state: WorkflowState) -> dict[str, Any]:
    """Create the initial skill, search, visual, and quality plan."""
    brief = dict(state.get("task_brief") or {})
    config_snapshot = dict(state.get("config_snapshot") or {})
    account_profile = dict(brief.get("account_profile") or config_snapshot.get("account_profile") or {})
    content_template = dict(brief.get("content_template") or config_snapshot.get("content_template") or {})
    review_policy = dict(brief.get("review_policy") or config_snapshot.get("review_policy") or {})
    image_policy = dict(brief.get("image_policy") or config_snapshot.get("image_policy") or {})
    generation_config = dict(config_snapshot.get("generation") or state.get("generation_config") or {})
    research_policy = normalize_research_policy(
        brief.get("research_policy")
        or config_snapshot.get("research_policy")
        or generation_config.get("research_policy")
    )
    research_state = dict(state.get("research_state") or {})
    registry = get_article_type_registry()
    article_goal = str(brief.get("article_goal") or "").strip()
    selected_hotspot = dict(brief.get("selected_hotspot") or state.get("selected_hotspot") or {})
    hotspot_titles = [
        str(item.get("title") or "").strip()
        for item in list(state.get("hotspot_candidates") or [])
        if isinstance(item, dict) and str(item.get("title") or "").strip()
    ][:8]

    selected_skill = select_article_skill(
        {
            "topic": brief.get("topic") or state.get("keywords"),
            "article_goal": article_goal,
            "style_hint": generation_config.get("style_hint"),
            "audience_roles": brief.get("audience_roles"),
            "hotspot_titles": [selected_hotspot.get("title"), *hotspot_titles],
        }
    )
    article_type = _resolve_article_type(article_goal, registry)
    angles, coverage_targets = _prioritize_angles(research_state)
    style_profile = {
        "content_type": "wechat_public_account_article",
        "tone": selected_skill.get("tone", ""),
        "style_hint": generation_config.get("style_hint", ""),
        "audience_roles": list(brief.get("audience_roles") or []),
    }
    visual_style = image_policy.get("style") or selected_skill.get("visual_style", "")
    topic = str(brief.get("topic") or state.get("keywords") or "").strip()
    fallback_contract = build_fallback_search_contract(
        task_id=state["task_id"],
        topic=topic,
        article_goal=article_goal,
        selected_hotspot=selected_hotspot,
        research_policy=research_policy,
    )
    ai_contract = await _build_ai_search_contract(
        state=state,
        fallback_contract=fallback_contract,
        selected_skill=selected_skill,
        research_policy=research_policy,
    )
    search_contract = normalize_search_contract(ai_contract or fallback_contract, fallback=fallback_contract)
    research_plan = {
        "topic": search_contract["topic"],
        "research_goal": search_contract["research_goal"],
        "category": search_contract["category"],
        "freshness": f"last_{search_contract['freshness_window_days']}_days",
        "search_questions": list(search_contract.get("search_questions") or []),
        "query_plan": list(search_contract.get("query_plan") or []),
        "must_have_evidence": list(search_contract.get("must_have_evidence") or []),
        "source_rules": dict(search_contract.get("source_rules") or {}),
    }

    planning_state = {
        "article_type": article_type,
        "available_skills": _available_skill_summary(),
        "selected_skill": selected_skill,
        "style_profile": style_profile,
        "account_profile": account_profile,
        "content_template": content_template,
        "review_policy": review_policy,
        "image_policy": image_policy,
        "research_policy": research_policy,
        "research_plan": research_plan,
        "search_contract": search_contract,
        "search_plan": {
            "angles": angles,
            "queries": [],
            "query_plan": list(search_contract.get("query_plan") or []),
            "coverage_targets": coverage_targets,
            "search_depth": search_contract.get("search_depth"),
        },
        "visual_plan": {
            "asset_roles": _visual_roles(article_type, image_policy),
            "quality_threshold": 75,
            "style": visual_style,
            "brand_colors": list(image_policy.get("brand_colors") or []),
            "title_safe_area": bool(image_policy.get("title_safe_area", True)),
        },
        "quality_thresholds": _thresholds_for_policy(review_policy),
    }
    return {
        "status": "running",
        "current_skill": "planner_agent",
        "progress": 12,
        "planning_state": planning_state,
        "style_profile": style_profile,
    }
