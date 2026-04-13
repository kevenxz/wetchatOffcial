"""Rank search results with authority and intent-aware scoring."""
from __future__ import annotations

import time

import structlog

from workflow.state import WorkflowState

logger = structlog.get_logger(__name__)

INTENT_SOURCE_BONUS: dict[str, dict[str, float]] = {
    "official_fact": {"official": 0.16, "documentation": 0.15, "github": 0.12, "research": 0.1},
    "technical_depth": {"documentation": 0.16, "github": 0.14, "research": 0.12, "official": 0.08},
    "reputable_news": {"media": 0.15, "institution": 0.12, "official": 0.08},
    "market_context": {"media": 0.14, "institution": 0.12, "official": 0.1, "research": 0.08},
    "risk_validation": {"media": 0.12, "institution": 0.1, "community": 0.06},
    "product_validation": {"official": 0.1, "media": 0.1, "community": 0.08},
    "blueprint_hint": {"official": 0.08, "media": 0.08, "research": 0.08},
}


def _score_result(item: dict) -> float:
    source_type = item.get("source_type", "unknown")
    intent = item.get("query_intent", "")
    authority = float(item.get("authority_score", 0.0))
    relevance = float(item.get("relevance_score", 0.0))
    freshness = float(item.get("freshness_score", 0.0))
    official_bonus = float(item.get("official_bonus", 0.0))
    intent_bonus = INTENT_SOURCE_BONUS.get(intent, {}).get(source_type, 0.0)
    return round(authority * 0.4 + relevance * 0.35 + freshness * 0.1 + official_bonus + intent_bonus, 4)


async def rank_sources_node(state: WorkflowState) -> dict:
    """Sort and trim search results while keeping source diversity."""
    task_id = state["task_id"]
    search_results = list(state.get("search_results", []))

    start_time = time.monotonic()
    logger.info(
        "skill_start",
        task_id=task_id,
        skill="rank_sources",
        status="running",
        candidate_count=len(search_results),
    )

    if not search_results:
        duration_ms = round((time.monotonic() - start_time) * 1000)
        logger.error(
            "skill_failed",
            task_id=task_id,
            skill="rank_sources",
            status="failed",
            duration_ms=duration_ms,
            error="没有可排序的搜索结果",
        )
        return {
            "status": "failed",
            "current_skill": "rank_sources",
            "error": "没有可排序的搜索结果",
        }

    for item in search_results:
        item["final_score"] = _score_result(item)

    ranked = sorted(search_results, key=lambda item: item.get("final_score", 0.0), reverse=True)
    domain_counts: dict[str, int] = {}
    selected: list[dict] = []
    for item in ranked:
        domain = item.get("domain", "")
        count = domain_counts.get(domain, 0)
        if domain and count >= 2:
            continue
        selected.append(item)
        if domain:
            domain_counts[domain] = count + 1
        if len(selected) >= 10:
            break

    duration_ms = round((time.monotonic() - start_time) * 1000)
    logger.info(
        "skill_done",
        task_id=task_id,
        skill="rank_sources",
        status="done",
        duration_ms=duration_ms,
        selected_count=len(selected),
    )

    return {
        "status": "running",
        "current_skill": "rank_sources",
        "progress": 60,
        "search_results": selected,
    }
