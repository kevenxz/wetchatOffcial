"""Run planned research tasks."""
from __future__ import annotations

from typing import Any

from workflow.tools.fetch_extract import fetch_extract_node
from workflow.tools.search_web import search_web_node
from workflow.state import WorkflowState


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
            "intent": str(item.get("angle") or item.get("intent") or "default").strip() or "default",
            "priority": index + 1,
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
                "final_score": final_score,
                "evidence_score": evidence_score,
                "needs_caution": needs_caution,
                "snippet": str(source_meta.get("snippet") or "").strip(),
            }
        )
    return evidence_items


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
    search_queries = _build_search_queries(queries)
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

    for query_batch in _chunk_search_queries(search_queries, batch_size=1):
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
                    "message": "no search results",
                    "queries": failed_queries,
                }
            )
            continue

        aggregated_search_results = _merge_results(
            aggregated_search_results,
            search_results,
            dedupe_keys=("url", "query"),
        )
        extract_result = await fetch_extract_node(
            {
                **state,
                "search_results": search_results,
            }
        )
        if extract_result.get("status") == "failed":
            failed_queries = [item.get("query") for item in search_results if item.get("query")]
            research_gaps.append(
                {
                    "stage": "fetch_extract",
                    "message": str(extract_result.get("error") or "extract failed"),
                    "queries": failed_queries,
                }
            )
            continue

        aggregated_extracted_contents = _merge_results(
            aggregated_extracted_contents,
            list(extract_result.get("extracted_contents") or []),
            dedupe_keys=("url",),
        )

    angle_by_query = {
        str(item.get("query") or "").strip(): str(item.get("angle") or "").strip()
        for item in queries
        if str(item.get("query") or "").strip()
    }
    evidence_items = _build_evidence_items(aggregated_extracted_contents, angle_by_query)
    return {
        "status": "running",
        "current_skill": "run_research",
        "progress": 30,
        "research_state": {
            **research_state,
            "research_gaps": research_gaps,
            "search_results": aggregated_search_results,
            "extracted_contents": aggregated_extracted_contents,
            "evidence_items": evidence_items,
        },
    }
