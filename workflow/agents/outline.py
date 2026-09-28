"""Build the article outline required by the content workflow."""
from __future__ import annotations

from typing import Any

from workflow.nodes.plan_article_angle import plan_article_angle_node
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
    thesis = str(blueprint.get("thesis") or "").strip()
    reader_value = str(blueprint.get("reader_value") or "").strip()
    editorial_contract = {
        "framework_name": "柔性论证型公众号文章",
        "central_question": str(blueprint.get("central_question") or thesis).strip(),
        "core_thesis": thesis,
        "reader_takeaway": reader_value,
        "opening_job": str(blueprint.get("opening_move") or "").strip()
        or "用具体变化、场景或认知冲突切入，首屏内给出中心判断以及它与读者的关系。",
        "development_rule": "叙事节点数量由素材决定；每个节点应完成观点、证据、解释和读者意义，素材不足就少写，不为凑结构增加章节。",
        "heading_rule": "小标题表达本节判断，不使用来源名、网址、截断的搜索摘要或‘原因/风险’式占位词。",
        "paragraph_rule": "一段只承担一个中心意思，通常使用二至四句，保持适合手机阅读的节奏。",
        "boundary_rule": "不确定性紧邻受影响的判断，区分已确认事实、合理推断和待验证信号。",
        "ending_job": str(blueprint.get("ending_move") or "").strip()
        or "回扣中心判断并给出下一步观察或行动，不复述全文、不喊口号。",
        "narrative_arc": str(blueprint.get("narrative_arc") or "").strip(),
    }
    return {
        "framework": str(blueprint.get("framework") or "由素材自主生成叙事").strip(),
        "structure_mode": str(blueprint.get("structure_mode") or "adaptive"),
        "structure_note": "以下为候选叙事节点，写作 Agent 可合并、改名、重排或舍弃；只锁定事实与证据边界。",
        "selected_skill": dict(blueprint.get("selected_skill") or {}),
        "title_candidates": list(blueprint.get("title_candidates") or []),
        "thesis": thesis,
        "reader_value": reader_value,
        "editorial_contract": editorial_contract,
        "outline": outline,
        "narrative_beats": outline,
        "must_use_facts": must_use_facts,
        "risk_boundaries": risk_boundaries,
        "source_driven_framework": list(blueprint.get("source_driven_framework") or []),
        "evidence_map": evidence_map,
        "image_plan_seed": {
            "cover_needed": True,
            "inline_count": max(1, min(inline_count or 1, 4)),
        },
    }


def merge_viral_into_outline(outline_result: dict[str, Any], viral_strategy: dict[str, Any]) -> dict[str, Any]:
    """Fold the distribution strategy into the outline result.

    Deterministic merge so the virality strategist and the blueprint planner can
    run concurrently and only meet here.
    """
    merged = dict(outline_result)
    viral_titles = [str(item).strip() for item in list(viral_strategy.get("title_hypotheses") or []) if str(item).strip()]
    if viral_titles:
        merged["title_candidates"] = list(
            dict.fromkeys([*viral_titles, *list(merged.get("title_candidates") or [])])
        )[:5]
    if viral_strategy.get("core_promise"):
        merged["reader_value"] = str(viral_strategy["core_promise"])
    if viral_strategy:
        merged["viral_strategy"] = viral_strategy
    return merged


async def outline_planner_base_node(state: WorkflowState) -> dict[str, Any]:
    """Build the article outline from the blueprint without the strategy merge.

    This is the fan-out leg that runs concurrently with ``design_viral_strategy``;
    ``merge_outline_strategy`` folds both results together afterwards.
    """
    result = await plan_article_angle_node(state)
    planning_state = dict(result.get("planning_state") or {})
    research_state = dict(state.get("research_state") or {})
    outline_result = _normalize_outline(dict(planning_state.get("article_blueprint") or {}), research_state)
    if planning_state.get("selected_skill"):
        outline_result["selected_skill"] = dict(planning_state.get("selected_skill") or {})
    planning_state["outline_result"] = outline_result
    return {
        **result,
        "current_skill": "outline_planner",
        "outline_result": outline_result,
        "planning_state": planning_state,
    }


async def outline_planner_node(state: WorkflowState) -> dict[str, Any]:
    """Use AI/search evidence to decide article title candidates and section outline."""
    result = await plan_article_angle_node(state)
    planning_state = dict(result.get("planning_state") or {})
    research_state = dict(state.get("research_state") or {})
    outline_result = _normalize_outline(dict(planning_state.get("article_blueprint") or {}), research_state)
    viral_strategy = dict(state.get("viral_state", {}).get("strategy") or {})
    outline_result = merge_viral_into_outline(outline_result, viral_strategy)
    if planning_state.get("selected_skill"):
        outline_result["selected_skill"] = dict(planning_state.get("selected_skill") or {})
    planning_state["outline_result"] = outline_result
    return {
        **result,
        "current_skill": "outline_planner",
        "outline_result": outline_result,
        "planning_state": planning_state,
    }
