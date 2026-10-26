"""Build structured evidence artifacts from research outputs."""
from __future__ import annotations

from typing import Any

import structlog

from workflow.state import WorkflowState
from workflow.utils.evidence_pack import build_evidence_pack
from workflow.utils.source_filter import filter_sources

logger = structlog.get_logger(__name__)


def _evidence_view(item: dict[str, Any]) -> dict[str, Any]:
    """Shape an evidence item for the source filter."""
    return {
        "url": str(item.get("url") or "").strip(),
        "title": str(item.get("title") or "").strip(),
        "text": str(item.get("claim") or item.get("snippet") or item.get("title") or "").strip(),
        "domain": str(item.get("domain") or "").strip(),
        "source_type": str(item.get("source_type") or "unknown").strip(),
        "needs_caution": bool(item.get("needs_caution")),
    }


async def build_evidence_pack_node(state: WorkflowState) -> dict[str, Any]:
    """Convert evidence items into grouped evidence pack fields.

    ``run_research`` already filtered the sources it collected. This second pass is a
    guard for anything that reached ``evidence_items`` by another route (resume,
    imported state, or a future node), so unfiltered material can never silently
    become evidence.
    """
    research_state = dict(state.get("research_state") or {})
    evidence_items = [dict(item) for item in list(research_state.get("evidence_items") or []) if isinstance(item, dict)]

    if evidence_items:
        topic = str(
            (state.get("search_contract") or {}).get("topic")
            or state.get("task_brief", {}).get("topic")
            or state.get("keywords")
            or ""
        ).strip()
        guard = filter_sources(topic, [_evidence_view(item) for item in evidence_items])
        kept_urls = {str(item.get("url") or "").strip() for item in guard.kept}
        allowed = [
            item
            for item in evidence_items
            if not str(item.get("url") or "").strip() or str(item.get("url") or "").strip() in kept_urls
        ]
        if len(allowed) != len(evidence_items):
            logger.info(
                "evidence_pack_filter_guard",
                task_id=str(state.get("task_id") or ""),
                before=len(evidence_items),
                after=len(allowed),
                reasons=guard.summary()["reasons"],
            )
            evidence_items = allowed
            existing = dict(research_state.get("source_filtering") or {})
            existing.setdefault("guard_dropped", len(guard.dropped))
            research_state["source_filtering"] = existing

    evidence_pack = build_evidence_pack(evidence_items)
    search_evaluation = dict(research_state.get("search_evaluation") or {})
    if search_evaluation:
        evidence_pack["search_evaluation"] = search_evaluation
        merged_gaps = list(evidence_pack.get("research_gaps") or [])
        for gap in list(search_evaluation.get("missing_questions") or []):
            if gap not in merged_gaps:
                merged_gaps.append(gap)
        evidence_pack["research_gaps"] = merged_gaps

    filtering = dict(research_state.get("source_filtering") or {})
    if filtering:
        evidence_pack["source_filtering"] = filtering
    research_state["evidence_pack"] = evidence_pack
    return {
        "status": "running",
        "current_skill": "build_evidence_pack",
        "progress": 34,
        "research_state": research_state,
    }
