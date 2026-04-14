"""Run planned research tasks."""
from __future__ import annotations

from typing import Any

from workflow.skills.fetch_extract import fetch_extract_node
from workflow.skills.search_web import search_web_node
from workflow.state import WorkflowState


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
                "authority_score": source_meta.get("authority_score"),
                "final_score": source_meta.get("final_score"),
                "snippet": str(source_meta.get("snippet") or "").strip(),
            }
        )
    return evidence_items


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

    search_result = await search_web_node(
        {
            **state,
            "search_queries": search_queries,
        }
    )
    if search_result.get("status") == "failed":
        research_state.setdefault("research_gaps", []).append(
            {"stage": "search_web", "message": str(search_result.get("error") or "search failed")}
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

    search_results = list(search_result.get("search_results") or [])
    extract_result = await fetch_extract_node(
        {
            **state,
            "search_results": search_results,
        }
    )
    if extract_result.get("status") == "failed":
        research_state.setdefault("research_gaps", []).append(
            {"stage": "fetch_extract", "message": str(extract_result.get("error") or "extract failed")}
        )
        return {
            "status": "running",
            "current_skill": "run_research",
            "progress": 30,
            "research_state": {
                **research_state,
                "search_results": search_results,
                "extracted_contents": [],
                "evidence_items": [],
            },
        }

    extracted_contents = list(extract_result.get("extracted_contents") or [])
    angle_by_query = {
        str(item.get("query") or "").strip(): str(item.get("angle") or "").strip()
        for item in queries
        if str(item.get("query") or "").strip()
    }
    evidence_items = _build_evidence_items(extracted_contents, angle_by_query)
    return {
        "status": "running",
        "current_skill": "run_research",
        "progress": 30,
        "research_state": {
            **research_state,
            "search_results": search_results,
            "extracted_contents": extracted_contents,
            "evidence_items": evidence_items,
        },
    }
