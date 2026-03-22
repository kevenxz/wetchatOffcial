"""Plan structured search queries from article blueprint."""
from __future__ import annotations

import time

import structlog

from workflow.article_generation import normalize_generation_config
from workflow.state import WorkflowState

logger = structlog.get_logger(__name__)


def _add_query(queries: list[dict], seen: set[str], query: str, intent: str, priority: int) -> None:
    cleaned = " ".join(query.split()).strip()
    if not cleaned:
        return
    lowered = cleaned.lower()
    if lowered in seen:
        return
    seen.add(lowered)
    queries.append({"query": cleaned, "intent": intent, "priority": priority})


async def plan_search_queries_node(state: WorkflowState) -> dict:
    """Generate a small query set that prefers official and reputable sources."""
    task_id = state["task_id"]
    generation_config = normalize_generation_config(state.get("generation_config"))
    user_intent = state.get("user_intent", {})
    article_blueprint = state.get("article_blueprint", {})

    start_time = time.monotonic()
    logger.info(
        "skill_start",
        task_id=task_id,
        skill="plan_search_queries",
        status="running",
    )

    topic = user_intent.get("topic", state.get("keywords", "")).strip()
    resolved_strategy = user_intent.get("resolved_strategy", generation_config["article_strategy"])
    primary_role = user_intent.get("primary_role", generation_config["audience_roles"][0])

    queries: list[dict] = []
    seen: set[str] = set()

    _add_query(queries, seen, f"{topic} official announcement OR official blog OR documentation", "official_fact", 1)
    _add_query(queries, seen, f"{topic} latest news analysis", "reputable_news", 2)
    _add_query(queries, seen, f"{topic} risk controversy limitation", "risk_validation", 3)

    if resolved_strategy == "tech_breakdown":
        _add_query(queries, seen, f"{topic} github paper benchmark architecture", "technical_depth", 2)
    elif resolved_strategy == "application_review":
        _add_query(queries, seen, f"{topic} review comparison use case", "product_validation", 2)
    else:
        _add_query(queries, seen, f"{topic} market size funding competition", "market_context", 2)

    if primary_role == "投资者":
        _add_query(queries, seen, f"{topic} business model market size funding", "market_context", 1)
    elif primary_role == "开发者":
        _add_query(queries, seen, f"{topic} documentation api architecture github", "technical_depth", 1)
    elif primary_role == "产品经理":
        _add_query(queries, seen, f"{topic} workflow use case product adoption", "product_validation", 2)

    for hint in article_blueprint.get("search_query_hints", []):
        _add_query(queries, seen, f"{topic} {hint}", "blueprint_hint", 4)
        if len(queries) >= 7:
            break

    duration_ms = round((time.monotonic() - start_time) * 1000)
    logger.info(
        "skill_done",
        task_id=task_id,
        skill="plan_search_queries",
        status="done",
        duration_ms=duration_ms,
        query_count=len(queries),
    )

    return {
        "status": "running",
        "current_skill": "plan_search_queries",
        "progress": 45,
        "search_queries": queries[:7],
    }
