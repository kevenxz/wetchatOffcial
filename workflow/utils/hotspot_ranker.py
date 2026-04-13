"""Hotspot candidate scoring and selection."""
from __future__ import annotations

import math
import re
from difflib import SequenceMatcher
from typing import Any


def _clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _normalize_title(value: str) -> str:
    text = _clean_text(value).lower()
    return re.sub(r"[\W_]+", "", text)


def _contains_any_keyword(text: str, keywords: list[str]) -> bool:
    if not text or not keywords:
        return False
    lowered_text = text.lower()
    return any(keyword.lower() in lowered_text for keyword in keywords if keyword)


def _rank_score(rank: int) -> float:
    # Rank 1 ~= 62, rank 10 ~= 21.
    return max(0.0, 62.0 - (max(rank, 1) - 1) * 4.5)


def _hot_value_score(hot_value: float | None) -> float:
    if hot_value is None or hot_value <= 0:
        return 0.0
    return min(22.0, math.log10(hot_value + 1) * 8.5)


def _platform_weight_score(weight: float) -> float:
    normalized = max(0.1, min(weight, 10.0))
    return max(0.0, min(16.0, (normalized - 1.0) * 12.0 + 8.0))


def _category_bonus(candidate_category: str, categories: list[str]) -> float:
    if not categories:
        return 0.0
    normalized_category = _clean_text(candidate_category).lower()
    normalized_targets = {_clean_text(category).lower() for category in categories if category}
    if normalized_category and normalized_category in normalized_targets:
        return 8.0
    return 0.0


def _score_to_star(score: float) -> int:
    if score >= 90:
        return 5
    if score >= 75:
        return 4
    if score >= 60:
        return 3
    if score >= 45:
        return 2
    return 1


def _is_duplicate_title(title: str, kept_titles: list[str]) -> bool:
    current = _normalize_title(title)
    if not current:
        return True
    for seen in kept_titles:
        if not seen:
            continue
        if current == seen:
            return True
        ratio = SequenceMatcher(None, current, seen).ratio()
        if ratio >= 0.9:
            return True
    return False


def rank_hotspots(
    candidates: list[dict[str, Any]],
    *,
    categories: list[str] | None = None,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Score, filter and dedupe hotspot candidates."""
    categories = categories or []
    filters = filters or {}
    min_selection_score = float(filters.get("min_selection_score", 60) or 0)
    exclude_keywords = list(filters.get("exclude_keywords", []) or [])
    prefer_keywords = list(filters.get("prefer_keywords", []) or [])

    scored: list[dict[str, Any]] = []
    for candidate in candidates:
        title = _clean_text(str(candidate.get("title", "")))
        if not title:
            continue
        if _contains_any_keyword(title, exclude_keywords):
            continue

        rank = int(candidate.get("rank") or 999)
        hot_value_raw = candidate.get("hot_value")
        hot_value = float(hot_value_raw) if hot_value_raw is not None else None
        platform_weight = float(candidate.get("platform_weight") or 1.0)
        category_bonus = _category_bonus(str(candidate.get("category", "")), categories)
        prefer_bonus = 5.0 if _contains_any_keyword(title, prefer_keywords) else 0.0

        rank_component = _rank_score(rank)
        hot_value_component = _hot_value_score(hot_value)
        platform_component = _platform_weight_score(platform_weight)
        raw_score = rank_component + hot_value_component + platform_component + category_bonus + prefer_bonus
        selection_score = round(max(0.0, min(raw_score, 100.0)), 2)

        merged = dict(candidate)
        merged.update(
            {
                "rank_score": round(rank_component, 2),
                "hot_value_score": round(hot_value_component, 2),
                "platform_weight_score": round(platform_component, 2),
                "category_bonus": round(category_bonus, 2),
                "prefer_bonus": round(prefer_bonus, 2),
                "duplicate_penalty": 0.0,
                "selection_score": selection_score,
                "selection_star": _score_to_star(selection_score),
            }
        )
        scored.append(merged)

    scored.sort(
        key=lambda item: (
            float(item.get("selection_score") or 0),
            -int(item.get("rank") or 9999),
        ),
        reverse=True,
    )

    deduped: list[dict[str, Any]] = []
    kept_titles: list[str] = []
    for item in scored:
        title = str(item.get("title", ""))
        if _is_duplicate_title(title, kept_titles):
            continue
        if float(item.get("selection_score") or 0) < min_selection_score:
            continue
        deduped.append(item)
        kept_titles.append(_normalize_title(title))

    return deduped


def pick_best_hotspot(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pick the top-scored candidate if available."""
    if not candidates:
        return None
    return candidates[0]
