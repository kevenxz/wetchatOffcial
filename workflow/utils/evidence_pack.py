"""Evidence normalization helpers for planner-led workflow."""
from __future__ import annotations

from typing import Any


def _count_by_key(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key) or "unknown").strip() or "unknown"
        counts[value] = counts.get(value, 0) + 1
    return counts


def _confidence(item: dict[str, Any]) -> str:
    score = float(item.get("evidence_score") or item.get("final_score") or 0)
    if score >= 0.78 and not item.get("needs_caution"):
        return "high"
    if score >= 0.58:
        return "medium"
    return "low"


def _citation(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": item.get("title") or item.get("source_title") or item.get("url") or "",
        "url": item.get("url") or "",
        "source_type": item.get("source_type") or "unknown",
        "domain": item.get("domain") or "",
        "retrieved_at": item.get("retrieved_at") or "",
        "confidence": _confidence(item),
    }


def _fact(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "fact": item.get("claim") or "",
        "source": item.get("title") or item.get("domain") or "",
        "source_id": item.get("url") or "",
        "url": item.get("url") or "",
        "confidence": _confidence(item),
    }


def _dedupe_by_url(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        url = str(item.get("url") or "").strip()
        if not url:
            deduped.append(item)
            continue
        if url in seen:
            continue
        seen.add(url)
        deduped.append(item)
    return deduped


def _allowed_claims(items: list[dict[str, Any]]) -> list[str]:
    claims: list[str] = []
    for item in items:
        if _confidence(item) == "high" and item.get("claim"):
            claims.append(f"可以说：{str(item['claim'])[:120]}")
        if len(claims) >= 5:
            break
    return claims


def _forbidden_claims(caution_items: list[dict[str, Any]], research_gaps: list[str]) -> list[str]:
    claims = [
        "不能把未经多源确认的信息写成确定结论",
        "不能使用保证收益、必然颠覆、已经定论等绝对表达",
    ]
    if caution_items:
        claims.append("低权威或社区来源只能作为线索，不能单独支撑核心事实")
    if research_gaps:
        claims.append("缺口对应的信息必须用谨慎语气或不写入正文")
    return claims


def build_evidence_pack(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group evidence items by downstream usage."""
    items = _dedupe_by_url(items)
    high_confidence_items = [
        item for item in items if float(item.get("evidence_score") or 0) >= 0.75 and not item.get("needs_caution")
    ]
    caution_items = [item for item in items if item.get("needs_caution")]
    research_gaps: list[str] = []
    if not any(item.get("angle") == "data" for item in items):
        research_gaps.append("missing_data_evidence")
    if not any(item.get("angle") == "fact" and float(item.get("evidence_score") or 0) >= 0.75 for item in items):
        research_gaps.append("missing_high_confidence_fact")
    if not any(item.get("source_type") in {"official", "documentation"} for item in items):
        research_gaps.append("missing_official_source")
    domains = {str(item.get("domain") or "").strip() for item in items if item.get("domain")}
    if len(domains) < 3 and len(items) >= 3:
        research_gaps.append("insufficient_source_diversity")

    return {
        "confirmed_facts": [item for item in items if item.get("angle") == "fact"],
        "caution_items": caution_items,
        "usable_data_points": [item for item in items if item.get("angle") == "data"],
        "usable_cases": [item for item in items if item.get("angle") == "case"],
        "risk_points": [
            item for item in items
            if item.get("angle") in {"opinion", "opposing_view"} or item.get("source_type") == "opposing_view"
        ],
        "actionable_takeaways": [],
        "key_facts": [_fact(item) for item in high_confidence_items[:8]],
        "timeline": [
            {"event": item.get("claim") or "", "source": item.get("url") or "", "confidence": _confidence(item)}
            for item in items
            if any(token in str(item.get("claim") or item.get("title") or "") for token in ("2024", "2025", "2026", "发布", "宣布", "通报"))
        ][:6],
        "viewpoints": {
            "positive": [item.get("claim") for item in items if item.get("angle") in {"analysis", "media"} and not item.get("needs_caution")][:5],
            "neutral": [item.get("claim") for item in items if _confidence(item) == "medium"][:5],
            "negative": [item.get("claim") for item in items if item in caution_items or item.get("angle") in {"opinion", "opposing_view"}][:5],
        },
        "allowed_claims": _allowed_claims(high_confidence_items),
        "forbidden_claims": _forbidden_claims(caution_items, research_gaps),
        "citations": [_citation(item) for item in items],
        "conflicts": [],
        "research_gaps": research_gaps,
        "quality_summary": {
            "total_items": len(items),
            "high_confidence_items": len(high_confidence_items),
            "caution_items": len(caution_items),
            "source_coverage": _count_by_key(items, "source_type"),
            "angle_coverage": _count_by_key(items, "angle"),
            "authority_ratio": round(len(high_confidence_items) / max(1, len(items)), 4),
            "domain_count": len(domains),
            "traceable_claims": len([item for item in items if item.get("url")]),
        },
    }
