"""Tests for hotspot scoring and selection."""
from __future__ import annotations

from workflow.utils.hotspot_ranker import pick_best_hotspot, rank_hotspots


def test_rank_hotspots_filters_dedup_and_min_score() -> None:
    candidates = [
        {
            "title": "OpenAI 发布新模型",
            "rank": 1,
            "hot_value": 12000,
            "platform_weight": 1.1,
            "category": "ai",
            "platform_name": "知乎热榜",
        },
        {
            "title": "OpenAI发布新模型",
            "rank": 2,
            "hot_value": 9000,
            "platform_weight": 1.0,
            "category": "ai",
            "platform_name": "微博热搜",
        },
        {
            "title": "娱乐八卦话题",
            "rank": 1,
            "hot_value": 50000,
            "platform_weight": 1.0,
            "category": "news",
            "platform_name": "微博热搜",
        },
    ]

    ranked = rank_hotspots(
        candidates,
        categories=["ai"],
        filters={
            "min_selection_score": 55,
            "exclude_keywords": ["八卦"],
            "prefer_keywords": ["OpenAI"],
        },
    )

    assert len(ranked) == 1
    assert ranked[0]["title"] == "OpenAI 发布新模型"
    assert ranked[0]["selection_score"] >= 55
    assert ranked[0]["selection_star"] >= 3


def test_pick_best_hotspot_returns_first_item() -> None:
    best = pick_best_hotspot(
        [
            {"title": "A", "selection_score": 90},
            {"title": "B", "selection_score": 80},
        ]
    )
    assert best is not None
    assert best["title"] == "A"
