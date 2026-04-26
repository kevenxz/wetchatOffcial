"""Build the article outline required by the content workflow."""
from __future__ import annotations

from typing import Any

from workflow.skills.plan_article_angle import plan_article_angle_node
from workflow.state import WorkflowState


def _claim_text(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("claim") or item.get("message") or item.get("title") or "").strip()
    return str(item or "").strip()


def _normalize_outline(blueprint: dict[str, Any], research_state: dict[str, Any]) -> dict[str, Any]:
    evidence_map = list(blueprint.get("evidence_map") or [])
    outline: list[dict[str, Any]] = []
    for index, section in enumerate(list(blueprint.get("sections") or [])):
        mapped = evidence_map[index] if index < len(evidence_map) and isinstance(evidence_map[index], dict) else {}
        outline.append(
            {
                "section": str(section.get("heading") or "").strip(),
                "goal": str(section.get("goal") or "").strip(),
                "shape": str(section.get("shape") or "").strip(),
                "source_refs": [value for value in [mapped.get("source_url")] if value],
                "key_points": [value for value in [mapped.get("source_claim")] if value],
                "image_hint": "inline" if str(section.get("shape") or "") in {"evidence", "case"} else "",
            }
        )

    evidence_pack = dict(research_state.get("evidence_pack") or {})
    must_use_facts = [
        str(item.get("claim") or "").strip()
        for group in ("confirmed_facts", "usable_data_points", "usable_cases")
        for item in list(evidence_pack.get(group) or [])
        if isinstance(item, dict) and str(item.get("claim") or "").strip()
    ][:8]
    risk_boundaries = [
        claim
        for item in list(evidence_pack.get("risk_points") or []) + list(evidence_pack.get("research_gaps") or [])
        if (claim := _claim_text(item))
    ][:6]

    inline_count = sum(1 for item in outline if item.get("image_hint") == "inline")
    return {
        "framework": str(blueprint.get("framework") or "AI 自主判定结构").strip(),
        "title_candidates": list(blueprint.get("title_candidates") or []),
        "thesis": str(blueprint.get("thesis") or "").strip(),
        "reader_value": str(blueprint.get("reader_value") or "").strip(),
        "outline": outline,
        "must_use_facts": must_use_facts,
        "risk_boundaries": risk_boundaries,
        "source_driven_framework": list(blueprint.get("source_driven_framework") or []),
        "evidence_map": evidence_map,
        "image_plan_seed": {
            "cover_needed": True,
            "inline_count": max(1, min(inline_count or 1, 4)),
        },
    }


async def outline_planner_node(state: WorkflowState) -> dict[str, Any]:
    """Use AI/search evidence to decide article title candidates and section outline."""
    result = await plan_article_angle_node(state)
    planning_state = dict(result.get("planning_state") or {})
    research_state = dict(state.get("research_state") or {})
    outline_result = _normalize_outline(dict(planning_state.get("article_blueprint") or {}), research_state)
    planning_state["outline_result"] = outline_result
    return {
        **result,
        "current_skill": "outline_planner",
        "outline_result": outline_result,
        "planning_state": planning_state,
    }
