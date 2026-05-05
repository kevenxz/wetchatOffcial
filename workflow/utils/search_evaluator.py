"""Search sufficiency evaluation and evidence context helpers."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from workflow.utils.research_contract import AUTHORITATIVE_TYPES, SEARCH_DEPTH_LIMITS


def _source_type(item: dict[str, Any]) -> str:
    return str(item.get("source_type") or "unknown").strip() or "unknown"


def _domain(item: dict[str, Any]) -> str:
    return str(item.get("domain") or "").strip()


def _score(item: dict[str, Any]) -> float:
    return float(item.get("evidence_score") or item.get("final_score") or 0)


def _is_authoritative(item: dict[str, Any]) -> bool:
    return _source_type(item) in AUTHORITATIVE_TYPES or _score(item) >= 0.75


def _has_opposing_view(item: dict[str, Any]) -> bool:
    text = " ".join(
        str(item.get(key) or "")
        for key in ("angle", "source_type", "query", "claim", "title", "snippet")
    ).lower()
    return any(token in text for token in ("opinion", "opposing", "risk", "争议", "风险", "局限", "谨慎", "反对"))


def _build_next_queries(contract: dict[str, Any], missing: list[str]) -> list[dict[str, Any]]:
    topic = str(contract.get("topic") or "").strip()
    next_queries: list[dict[str, Any]] = []
    for gap in missing:
        if gap == "missing_official_source":
            next_queries.append({"query": f"{topic} 官方 公告 原文", "purpose": "补充官方一手来源", "source_type": "official", "priority": 1})
        elif gap == "missing_authoritative_sources":
            next_queries.append({"query": f"{topic} 权威媒体 行业报告 解读", "purpose": "补充权威来源", "source_type": "media", "priority": 2})
        elif gap == "missing_cross_sources":
            next_queries.append({"query": f"{topic} 多家媒体 报道 对比", "purpose": "补充多源交叉验证", "source_type": "media", "priority": 3})
        elif gap == "missing_opposing_view":
            next_queries.append({"query": f"{topic} 风险 争议 局限 谨慎观点", "purpose": "补充风险和反向观点", "source_type": "opposing_view", "priority": 4})
        elif gap == "missing_timeline":
            next_queries.append({"query": f"{topic} 时间线 发布时间 最新进展", "purpose": "补充时间线", "source_type": "data", "priority": 5})
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in next_queries:
        query = item["query"]
        if query in seen:
            continue
        seen.add(query)
        deduped.append(item)
    return deduped


def evaluate_search_sufficiency(
    *,
    contract: dict[str, Any],
    evidence_items: list[dict[str, Any]],
    search_results: list[dict[str, Any]],
    current_round: int,
) -> dict[str, Any]:
    """Evaluate whether current research satisfies the Search Contract."""
    depth = str(contract.get("search_depth") or "standard")
    limits = SEARCH_DEPTH_LIMITS.get(depth, SEARCH_DEPTH_LIMITS["standard"])
    domains = {_domain(item) for item in evidence_items if _domain(item)}
    source_types = Counter(_source_type(item) for item in evidence_items)
    authoritative_count = sum(1 for item in evidence_items if _is_authoritative(item))
    official_count = source_types.get("official", 0) + source_types.get("documentation", 0)
    opposing_count = sum(1 for item in evidence_items if _has_opposing_view(item))
    timeline_count = sum(
        1
        for item in evidence_items
        if any(token in str(item.get("claim") or item.get("title") or "") for token in ("2024", "2025", "2026", "发布", "宣布", "通报"))
    )

    min_sources = max(int(contract.get("min_source_count") or 0), limits["min_sources"])
    min_authoritative = max(1, int(contract.get("min_authoritative_source_count") or 1))
    min_cross = max(1, int(contract.get("min_cross_source_count") or 3))
    missing: list[str] = []
    if len(evidence_items) < min_sources:
        missing.append("missing_min_sources")
    if official_count < int(contract.get("min_authoritative_source_count") or 1):
        missing.append("missing_official_source")
    if authoritative_count < min_authoritative:
        missing.append("missing_authoritative_sources")
    if len(domains) < min_cross:
        missing.append("missing_cross_sources")
    if contract.get("require_opposing_view", True) and opposing_count < 1:
        missing.append("missing_opposing_view")
    hotspot_rules = dict(contract.get("hotspot_verification") or {})
    if hotspot_rules.get("require_timeline") and timeline_count < 1:
        missing.append("missing_timeline")

    low_quality = sum(1 for item in evidence_items if item.get("needs_caution") or _score(item) < 0.6)
    duplicate_ratio = 0.0
    if search_results:
        unique_urls = {str(item.get("url") or "") for item in search_results if item.get("url")}
        duplicate_ratio = round(max(0, len(search_results) - len(unique_urls)) / max(1, len(search_results)), 4)
    low_quality_ratio = round(low_quality / max(1, len(evidence_items)), 4)

    max_rounds = int(limits["max_rounds"])
    decision = "enough"
    if missing:
        decision = "continue_search" if current_round < max_rounds else "manual_review_required"
    if contract.get("requires_manual_review") and missing:
        decision = "manual_review_required" if current_round >= max_rounds else "continue_search"

    return {
        "decision": decision,
        "missing_questions": missing,
        "next_queries": _build_next_queries(contract, missing),
        "coverage_check": {
            "official_source_found": official_count > 0,
            "multiple_sources_found": len(domains) >= min_cross,
            "opposing_view_found": opposing_count > 0,
            "data_or_timeline_found": timeline_count > 0 or source_types.get("data", 0) > 0,
        },
        "quality_check": {
            "low_quality_sources_ratio": low_quality_ratio,
            "duplicate_sources_ratio": duplicate_ratio,
            "authoritative_source_count": authoritative_count,
            "domain_count": len(domains),
        },
        "manual_review_required": decision == "manual_review_required" or bool(contract.get("requires_manual_review") and missing),
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }
