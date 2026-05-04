"""Planner stage for the redesigned workflow."""
from __future__ import annotations

from typing import Any

from workflow.article_skills import list_article_skills, select_article_skill
from workflow.state import WorkflowState
from workflow.utils.article_type_registry import get_article_type_registry


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


async def planner_agent_node(state: WorkflowState) -> dict[str, Any]:
    """Create the initial article, search, and visual plan."""
    brief = dict(state.get("task_brief") or {})
    config_snapshot = dict(state.get("config_snapshot") or {})
    account_profile = dict(brief.get("account_profile") or config_snapshot.get("account_profile") or {})
    content_template = dict(brief.get("content_template") or config_snapshot.get("content_template") or {})
    review_policy = dict(brief.get("review_policy") or config_snapshot.get("review_policy") or {})
    image_policy = dict(brief.get("image_policy") or config_snapshot.get("image_policy") or {})
    research_state = dict(state.get("research_state") or {})
    registry = get_article_type_registry()
    article_goal = str(brief.get("article_goal") or "").strip()
    generation_config = dict(config_snapshot.get("generation") or state.get("generation_config") or {})
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
    planning_state = {
        "article_type": article_type,
        "available_skills": [
            {
                "skill_id": skill.get("skill_id"),
                "name": skill.get("name"),
                "description": skill.get("description"),
                "decision_rule": skill.get("decision_rule"),
            }
            for skill in list_article_skills()
        ],
        "selected_skill": selected_skill,
        "account_profile": account_profile,
        "content_template": content_template,
        "review_policy": review_policy,
        "image_policy": image_policy,
        "search_plan": {
            "angles": angles,
            "queries": [],
            "coverage_targets": coverage_targets,
        },
        "visual_plan": {
            "asset_roles": _visual_roles(article_type, image_policy),
            "quality_threshold": 75,
            "style": image_policy.get("style") or selected_skill.get("visual_style", ""),
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
    }
