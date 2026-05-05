"""Run planned research tasks."""
from __future__ import annotations

from typing import Any

from workflow.tools.fetch_extract import fetch_extract_node
from workflow.tools.search_web import search_web_node
from workflow.state import WorkflowState
from workflow.utils.research_contract import SEARCH_DEPTH_LIMITS
from workflow.utils.search_evaluator import evaluate_search_sufficiency


def _chunk_search_queries(search_queries: list[dict[str, Any]], batch_size: int = 1) -> list[list[dict[str, Any]]]:
    if batch_size <= 0:
        batch_size = 1
    return [
        search_queries[index:index + batch_size]
        for index in range(0, len(search_queries), batch_size)
    ]


def _build_search_queries(queries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "query": str(item.get("query") or "").strip(),
            "intent": str(item.get("angle") or item.get("source_type") or item.get("intent") or "default").strip() or "default",
            "purpose": str(item.get("purpose") or item.get("intent") or "").strip(),
            "source_type": str(item.get("source_type") or item.get("angle") or "unknown").strip(),
            "priority": int(item.get("priority") or index + 1),
        }
        for index, item in enumerate(queries)
        if str(item.get("query") or "").strip()
    ]


def _claim_from_text(title: str, text: str, snippet: str) -> str:
    for value in (text, snippet, title):
        cleaned = " ".join(str(value or "").split())
        if cleaned:
            return cleaned[:220]
    return ""


def _build_evidence_items(extracted_contents: list[dict[str, Any]], angle_by_query: dict[str, str]) -> list[dict[str, Any]]:
    evidence_items: list[dict[str, Any]] = []
    for item in extracted_contents:
        source_meta = dict(item.get("source_meta") or {})
        query = str(source_meta.get("query") or "").strip()
        angle = angle_by_query.get(query) or str(source_meta.get("query_intent") or "fact").strip() or "fact"
        claim = _claim_from_text(
            str(item.get("title") or ""),
            str(item.get("text") or ""),
            str(source_meta.get("snippet") or ""),
        )
        authority_score = float(source_meta.get("authority_score") or 0)
        final_score = float(source_meta.get("final_score") or 0)
        evidence_score = round((authority_score * 0.6) + (final_score * 0.4), 4)
        needs_caution = evidence_score < 0.6 or str(source_meta.get("source_type") or "") in {"community", "aggregator"}
        evidence_items.append(
            {
                "angle": angle,
                "query": query,
                "claim": claim,
                "title": str(item.get("title") or "").strip(),
                "url": str(item.get("url") or "").strip(),
                "source_type": str(source_meta.get("source_type") or "unknown").strip(),
                "domain": str(source_meta.get("domain") or "").strip(),
                "provider": str(source_meta.get("provider") or "").strip(),
                "authority_score": authority_score,
                "relevance_score": float(source_meta.get("relevance_score") or 0),
                "freshness_score": float(source_meta.get("freshness_score") or 0),
                "originality_score": float(source_meta.get("originality_score") or 0),
                "cross_source_score": float(source_meta.get("cross_source_score") or 0),
                "content_depth_score": float(source_meta.get("content_depth_score") or 0),
                "risk_penalty": float(source_meta.get("risk_penalty") or 0),
                "duplicate_penalty": float(source_meta.get("duplicate_penalty") or 0),
                "final_score": final_score,
                "evidence_score": evidence_score,
                "needs_caution": needs_caution,
                "snippet": str(source_meta.get("snippet") or "").strip(),
                "retrieved_at": str(source_meta.get("retrieved_at") or "").strip(),
            }
        )
    return evidence_items


def _default_contract(state: WorkflowState, queries: list[dict[str, Any]]) -> dict[str, Any]:
    topic = str(state.get("task_brief", {}).get("topic") or state.get("keywords") or "").strip()
    return {
        "task_id": state.get("task_id", ""),
        "topic": topic,
        "category": "other",
        "search_depth": "quick",
        "query_plan": queries,
        "min_source_count": max(1, len(queries)),
        "min_authoritative_source_count": 0,
        "min_cross_source_count": 1,
        "require_opposing_view": False,
        "requires_manual_review": False,
        "hotspot_verification": {},
    }


def _append_queries(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = list(existing)
    seen = {str(item.get("query") or "").strip() for item in merged}
    for item in incoming:
        query = str(item.get("query") or "").strip()
        if not query or query in seen:
            continue
        seen.add(query)
        merged.append(
            {
                "query": query,
                "angle": str(item.get("source_type") or item.get("angle") or "fact").strip(),
                "intent": str(item.get("purpose") or item.get("intent") or "").strip(),
                "purpose": str(item.get("purpose") or "").strip(),
                "source_type": str(item.get("source_type") or "unknown").strip(),
                "priority": int(item.get("priority") or len(merged) + 1),
            }
        )
    return merged


def _merge_results(existing: list[dict[str, Any]], incoming: list[dict[str, Any]], dedupe_keys: tuple[str, ...]) -> list[dict[str, Any]]:
    merged = list(existing)
    seen = {
        tuple(str(item.get(key) or "").strip() for key in dedupe_keys)
        for item in merged
    }
    for item in incoming:
        dedupe_value = tuple(str(item.get(key) or "").strip() for key in dedupe_keys)
        if dedupe_value in seen:
            continue
        seen.add(dedupe_value)
        merged.append(item)
    return merged


async def run_research_node(state: WorkflowState) -> dict[str, Any]:
    """Run search and extraction for planned research queries."""
    planning_state = dict(state.get("planning_state") or {})
    queries = list(planning_state.get("search_plan", {}).get("queries") or [])
    research_state = dict(state.get("research_state") or {})
    search_contract = dict(planning_state.get("search_contract") or {}) or _default_contract(state, queries)
    depth = str(search_contract.get("search_depth") or "standard")
    limits = SEARCH_DEPTH_LIMITS.get(depth, SEARCH_DEPTH_LIMITS["standard"])
    search_queries = _build_search_queries(sorted(queries, key=lambda item: int(item.get("priority") or 99)))
    if not search_queries:
        research_state.setdefault("research_gaps", []).append(
            {"stage": "run_research", "message": "missing search queries"}
        )
        return {
            "status": "running",
            "current_skill": "run_research",
            "progress": 30,
            "research_state": {
                **research_state,
                "search_results": [],
                "extracted_contents": [],
                "evidence_items": [],
            },
        }

    aggregated_search_results: list[dict[str, Any]] = []
    aggregated_extracted_contents: list[dict[str, Any]] = []
    research_gaps = list(research_state.get("research_gaps") or [])
    search_runs: list[dict[str, Any]] = []
    final_evaluation: dict[str, Any] = {}
    queued_queries = search_queries[: int(limits["max_queries"])]
    executed_queries: set[str] = set()
    evidence_items: list[dict[str, Any]] = []

    for round_index in range(1, int(limits["max_rounds"]) + 1):
        round_queries = [
            item for item in queued_queries
            if str(item.get("query") or "").strip() not in executed_queries
        ][: int(limits["max_queries"])]
        if not round_queries:
            break
        round_search_results: list[dict[str, Any]] = []
        round_extracted_contents: list[dict[str, Any]] = []

        for query_batch in _chunk_search_queries(round_queries, batch_size=1):
            for query in query_batch:
                executed_queries.add(str(query.get("query") or "").strip())
            search_result = await search_web_node(
                {
                    **state,
                    "search_queries": query_batch,
                }
            )
            if search_result.get("status") == "failed":
                failed_queries = [item.get("query") for item in query_batch if item.get("query")]
                research_gaps.append(
                    {
                        "stage": "search_web",
                        "round": round_index,
                        "message": str(search_result.get("error") or "search failed"),
                        "queries": failed_queries,
                    }
                )
                continue

            search_results = list(search_result.get("search_results") or [])
            if not search_results:
                failed_queries = [item.get("query") for item in query_batch if item.get("query")]
                research_gaps.append(
                    {
                        "stage": "search_web",
                        "round": round_index,
                        "message": "no search results",
                        "queries": failed_queries,
                    }
                )
                continue

            round_search_results = _merge_results(round_search_results, search_results, dedupe_keys=("url", "query"))
            aggregated_search_results = _merge_results(
                aggregated_search_results,
                search_results,
                dedupe_keys=("url", "query"),
            )
            extract_result = await fetch_extract_node(
                {
                    **state,
                    "search_results": search_results[: int(limits["fetch_per_query"])],
                }
            )
            if extract_result.get("status") == "failed":
                failed_queries = [item.get("query") for item in search_results if item.get("query")]
                research_gaps.append(
                    {
                        "stage": "fetch_extract",
                        "round": round_index,
                        "message": str(extract_result.get("error") or "extract failed"),
                        "queries": failed_queries,
                    }
                )
                continue

            extracted = list(extract_result.get("extracted_contents") or [])
            round_extracted_contents = _merge_results(round_extracted_contents, extracted, dedupe_keys=("url",))
            aggregated_extracted_contents = _merge_results(
                aggregated_extracted_contents,
                extracted,
                dedupe_keys=("url",),
            )

        angle_by_query = {
            str(item.get("query") or "").strip(): str(item.get("angle") or item.get("source_type") or "").strip()
            for item in _append_queries(queries, queued_queries)
            if str(item.get("query") or "").strip()
        }
        evidence_items = _build_evidence_items(aggregated_extracted_contents, angle_by_query)
        final_evaluation = evaluate_search_sufficiency(
            contract=search_contract,
            evidence_items=evidence_items,
            search_results=aggregated_search_results,
            current_round=round_index,
        )
        search_runs.append(
            {
                "round": round_index,
                "queries": round_queries,
                "search_result_count": len(round_search_results),
                "extracted_count": len(round_extracted_contents),
                "evaluation": final_evaluation,
            }
        )
        if final_evaluation.get("decision") != "continue_search":
            break
        queued_queries = _append_queries(queued_queries, list(final_evaluation.get("next_queries") or []))

    if final_evaluation.get("missing_questions"):
        for gap in final_evaluation["missing_questions"]:
            if gap not in research_gaps:
                research_gaps.append(gap)
    return {
        "status": "running",
        "current_skill": "run_research",
        "progress": 30,
        "research_state": {
            **research_state,
            "research_gaps": research_gaps,
            "search_contract": search_contract,
            "search_runs": search_runs,
            "search_evaluation": final_evaluation,
            "manual_review_reasons": list(final_evaluation.get("missing_questions") or [])
            if final_evaluation.get("manual_review_required")
            else [],
            "search_results": aggregated_search_results,
            "extracted_contents": aggregated_extracted_contents,
            "evidence_items": evidence_items,
        },
        "human_review_required": bool(state.get("human_review_required")) or bool(final_evaluation.get("manual_review_required")),
    }
