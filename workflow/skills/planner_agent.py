"""Planner stage for the redesigned workflow."""
from __future__ import annotations

from typing import Any

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


async def planner_agent_node(state: WorkflowState) -> dict[str, Any]:
    """Create the initial article, search, and visual plan."""
    brief = dict(state.get("task_brief") or {})
    research_state = dict(state.get("research_state") or {})
    registry = get_article_type_registry()
    article_goal = str(brief.get("article_goal") or "").strip()
    article_type = _resolve_article_type(article_goal, registry)
    angles, coverage_targets = _prioritize_angles(research_state)
    planning_state = {
        "article_type": article_type,
        "search_plan": {
            "angles": angles,
            "queries": [],
            "coverage_targets": coverage_targets,
        },
        "visual_plan": {
            "asset_roles": article_type["visual_preferences"],
            "quality_threshold": 75,
        },
        "quality_thresholds": {
            "article": 80,
            "visual": 75,
            "evidence": 80,
            "hotspot": 70,
        },
    }
    return {
        "status": "running",
        "current_skill": "planner_agent",
        "progress": 12,
        "planning_state": planning_state,
    }
