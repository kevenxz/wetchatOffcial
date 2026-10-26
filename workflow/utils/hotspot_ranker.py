"""Hotspot candidate scoring and selection.

Two similarity thresholds, deliberately different
-------------------------------------------------
``DUPLICATE_SIMILARITY`` (0.90) decides which rows survive — a high bar, because dropping a
genuinely distinct story is unrecoverable.

``CROSS_PLATFORM_SIMILARITY`` (0.65) decides only how *widely reported* a story looks. It is
much looser on purpose, and the asymmetry is safe: a loose match here can at worst add a
bounded score bonus, never delete a row. This matters because real cross-platform coverage is
rarely word-for-word — one story about the same earthquake arrived as
"西藏那曲巴青县发生7.0级地震", "西藏那曲市7.0级地震" and "西藏7级地震"
(pairwise similarity ≈ 0.76, so the strict matcher treats them as three unrelated rows).

Why a frequency term at all: the ``newsnow`` source reports no heat value, so ``hot_value`` is
always ``None``. With only rank and platform weight, eight rank-1 items from equal-weight
platforms all scored exactly 71.2 and the winner was decided by platform ordering — i.e.
arbitrary. Coverage breadth is the signal that was missing.
"""
from __future__ import annotations

import math
import re
from difflib import SequenceMatcher
from typing import Any

# Rows at or above this similarity are treated as duplicates and collapsed.
DUPLICATE_SIMILARITY = 0.9
# Loose grouping used only for the cross-platform frequency signal.
CROSS_PLATFORM_SIMILARITY = 0.65
# Titles shorter than this must match exactly: a ratio of 0.67 on two characters means
# nothing ("召回" vs "汽车召回").
MIN_LOOSE_TITLE_LENGTH = 4
# Per additional platform covering the same story, and the cap on that bonus.
FREQUENCY_BONUS_PER_PLATFORM = 6.0
FREQUENCY_BONUS_CAP = 12.0


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
        if ratio >= DUPLICATE_SIMILARITY:
            return True
    return False


def _similar_title(left: str, right: str) -> bool:
    """Loose title match used by the frequency signal (never by dedupe)."""
    if not left or not right:
        return False
    if left == right:
        return True
    # Below this length a ratio test is meaningless: "召回" and "汽车召回" would score 0.67
    # and merge two different things. Short titles must match exactly.
    if len(left) < MIN_LOOSE_TITLE_LENGTH or len(right) < MIN_LOOSE_TITLE_LENGTH:
        return False
    # A cheap length guard before the expensive matcher. Two headlines of very different
    # lengths cannot be the same story, and this keeps grouping near-linear in practice.
    shorter, longer = sorted((len(left), len(right)))
    if shorter / longer < 0.45:
        return False
    # A title fully contained in a longer one is the same story more often than not.
    if left in right or right in left:
        return True
    return SequenceMatcher(None, left, right).ratio() >= CROSS_PLATFORM_SIMILARITY


def _platform_label(candidate: dict[str, Any]) -> str:
    """Stable identity of the platform a candidate came from."""
    for key in ("provider_id", "platform_path", "platform_name", "source"):
        value = _clean_text(str(candidate.get(key) or ""))
        if value:
            return value
    return "unknown"


def compute_cross_platform_coverage(candidates: list[dict[str, Any]]) -> list[tuple[int, list[str]]]:
    """For each candidate, how many distinct platforms covered the same story.

    Returns ``(distinct_platform_count, platform_labels)`` aligned with ``candidates``.

    Grouping is **transitive** (connected components), not pairwise. Real coverage arrives as
    a chain rather than a star: of the three earthquake headlines,
    "西藏那曲巴青县发生7.0级地震" only resembles "西藏那曲市7.0级地震", which in turn resembles
    "西藏7级地震" — the middle headline bridges the outer two, which never match each other.
    A pairwise comparison therefore reported coverage of 2/3/2 for one story; connected
    components correctly report 3/3/3.

    Duplicate rows from the *same* platform count once, so a single platform listing a story
    twice does not masquerade as broad coverage.
    """
    normalized = [_normalize_title(str(candidate.get("title") or "")) for candidate in candidates]
    platforms = [_platform_label(candidate) for candidate in candidates]
    count = len(candidates)

    # Union-find over the loose similarity relation.
    parent = list(range(count))

    def find(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    for i in range(count):
        if not normalized[i]:
            continue
        for j in range(i + 1, count):
            if not normalized[j]:
                continue
            if _similar_title(normalized[i], normalized[j]):
                union(i, j)

    members: dict[int, list[int]] = {}
    for index in range(count):
        members.setdefault(find(index), []).append(index)

    coverage: list[tuple[int, list[str]]] = []
    for index in range(count):
        group = members[find(index)]
        labels = sorted({platforms[member] for member in group})
        coverage.append((len(labels), labels))
    return coverage


def _frequency_score(platform_count: int) -> float:
    """Bonus for a story covered by several platforms."""
    extra = max(0, int(platform_count) - 1)
    return min(FREQUENCY_BONUS_CAP, extra * FREQUENCY_BONUS_PER_PLATFORM)


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

    # Coverage is computed over the whole candidate pool *before* any filtering, so a story
    # is credited for being on several platforms even if some of those rows are then
    # excluded by the operator's own keyword filters.
    coverage = compute_cross_platform_coverage(candidates)

    scored: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
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
        platform_count, source_platforms = coverage[index]
        frequency_component = _frequency_score(platform_count)

        rank_component = _rank_score(rank)
        hot_value_component = _hot_value_score(hot_value)
        platform_component = _platform_weight_score(platform_weight)
        raw_score = (
            rank_component
            + hot_value_component
            + platform_component
            + category_bonus
            + prefer_bonus
            + frequency_component
        )
        selection_score = round(max(0.0, min(raw_score, 100.0)), 2)

        merged = dict(candidate)
        merged.update(
            {
                "rank_score": round(rank_component, 2),
                "hot_value_score": round(hot_value_component, 2),
                "platform_weight_score": round(platform_component, 2),
                "category_bonus": round(category_bonus, 2),
                "prefer_bonus": round(prefer_bonus, 2),
                "frequency_score": round(frequency_component, 2),
                "cross_platform_count": platform_count,
                "source_platforms": source_platforms,
                "duplicate_penalty": 0.0,
                "selection_score": selection_score,
                "selection_star": _score_to_star(selection_score),
            }
        )
        scored.append(merged)

    # Tie-break deterministically and meaningfully. Previously any two candidates with the
    # same score were ordered by the platform catalogue, which made the winner arbitrary.
    # Now wider coverage wins first, then the higher-weight platform, then the shorter
    # (usually more canonical) headline, and only then the original order.
    scored.sort(
        key=lambda item: (
            float(item.get("selection_score") or 0),
            int(item.get("cross_platform_count") or 1),
            -int(item.get("rank") or 9999),
            float(item.get("platform_weight") or 1.0),
            -len(str(item.get("title") or "")),
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
