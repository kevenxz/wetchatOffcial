"""Tests for the cross-platform frequency signal in hotspot ranking.

Why this exists: the ``newsnow`` source reports no heat value, so ``hot_value`` is always
``None``. With only ``rank`` and ``platform_weight`` to go on, a real snapshot produced eight
candidates tied at exactly 71.2 — and three of those were the *same* earthquake reported as
"西藏那曲巴青县发生7.0级地震", "西藏那曲市7.0级地震" and "西藏7级地震". ``pick_best_hotspot``
returns ``candidates[0]``, so the winner was decided by platform catalogue order: deterministic
but meaningless.

Coverage breadth is the missing signal. The two thresholds are deliberately different and
these tests pin that asymmetry down:

* ``DUPLICATE_SIMILARITY`` (0.90) decides which rows survive — a loose match here would delete
  distinct stories, which is unrecoverable. Unchanged from before.
* ``CROSS_PLATFORM_SIMILARITY`` (0.65) only decides how widely reported a story looks. A false
  positive costs a bounded score bonus, never a row.
"""
from __future__ import annotations

import pytest

from workflow.utils.hotspot_ranker import (
    CROSS_PLATFORM_SIMILARITY,
    DUPLICATE_SIMILARITY,
    FREQUENCY_BONUS_CAP,
    compute_cross_platform_coverage,
    pick_best_hotspot,
    rank_hotspots,
)

# The three real headlines for one earthquake, similarity ≈ 0.76 pairwise.
QUAKE_HEADLINES = [
    "西藏那曲巴青县发生7.0级地震",
    "西藏那曲市7.0级地震",
    "西藏7级地震",
]


def _candidate(title: str, platform: str, *, rank: int = 1, weight: float = 1.0, **extra) -> dict:
    return {
        "title": title,
        "platform_name": platform,
        "provider_id": platform,
        "rank": rank,
        "platform_weight": weight,
        "category": "",
        "hot_value": None,
        "source": "newsnow",
        **extra,
    }


# --------------------------------------------------------------------------- #
# the asymmetry between the two thresholds
# --------------------------------------------------------------------------- #


def test_the_two_thresholds_are_deliberately_different() -> None:
    assert DUPLICATE_SIMILARITY > CROSS_PLATFORM_SIMILARITY


def test_real_cross_platform_headlines_are_grouped() -> None:
    """These are below the dedupe bar but plainly the same story."""
    candidates = [_candidate(title, f"p{index}") for index, title in enumerate(QUAKE_HEADLINES)]

    coverage = compute_cross_platform_coverage(candidates)

    assert [count for count, _ in coverage] == [3, 3, 3]


def test_grouping_does_not_merge_unrelated_stories() -> None:
    candidates = [
        _candidate("西藏那曲市7.0级地震", "weibo"),
        _candidate("Epic 喜加二：《斯盖尔仪式》《归家》游戏免费领", "ithome"),
        _candidate("千亿ETF阵营扩容到5只，越跌越增，谁在搅动逆势增长？", "cls-hot"),
    ]

    coverage = compute_cross_platform_coverage(candidates)

    assert [count for count, _ in coverage] == [1, 1, 1]


def test_a_title_repeated_within_one_platform_counts_once() -> None:
    """One platform listing a story twice must not look like broad coverage."""
    candidates = [
        _candidate("同一条热点", "weibo", rank=1),
        _candidate("同一条热点", "weibo", rank=5),
    ]

    coverage = compute_cross_platform_coverage(candidates)

    assert [count for count, _ in coverage] == [1, 1]


def test_containment_counts_as_the_same_story() -> None:
    candidates = [
        _candidate("国乒女团决赛不敌日本", "weibo"),
        _candidate("国乒女团决赛不敌日本队", "zhihu"),
    ]

    assert compute_cross_platform_coverage(candidates)[0][0] == 2


def test_very_short_titles_are_not_grouped_by_containment() -> None:
    """Containment on 1-2 characters would group almost everything."""
    candidates = [_candidate("召回", "weibo"), _candidate("汽车召回", "zhihu")]

    assert compute_cross_platform_coverage(candidates)[0][0] == 1


def test_source_platforms_are_reported_for_auditing() -> None:
    """An operator must be able to see *why* a story was scored as widely covered."""
    candidates = [_candidate(title, platform) for title, platform in zip(QUAKE_HEADLINES, ["toutiao", "baidu", "weibo"])]

    _, platforms = compute_cross_platform_coverage(candidates)[0]

    assert platforms == ["baidu", "toutiao", "weibo"]


def test_empty_titles_are_handled() -> None:
    coverage = compute_cross_platform_coverage([_candidate("", "weibo"), _candidate("真实标题", "zhihu")])

    assert coverage[0][0] == 1
    assert coverage[1][0] == 1


def test_coverage_falls_back_when_platform_keys_are_missing() -> None:
    candidates = [
        {"title": "同一条热点", "rank": 1},
        {"title": "同一条热点", "rank": 2},
    ]

    coverage = compute_cross_platform_coverage(candidates)

    assert coverage[0][0] == 1, "unknown platforms must not inflate coverage"


# --------------------------------------------------------------------------- #
# scoring
# --------------------------------------------------------------------------- #


def test_widely_reported_story_outranks_a_single_platform_one() -> None:
    """The whole point: coverage breadth beats an isolated rank-1 item."""
    candidates = [
        _candidate(QUAKE_HEADLINES[0], "toutiao"),
        _candidate(QUAKE_HEADLINES[1], "baidu"),
        _candidate(QUAKE_HEADLINES[2], "weibo"),
        _candidate("只在单个平台出现的热点", "ithome"),
    ]

    ranked = rank_hotspots(candidates, categories=[], filters={"min_selection_score": 0})

    assert ranked[0]["cross_platform_count"] == 3
    assert ranked[0]["selection_score"] > ranked[-1]["selection_score"]
    assert ranked[-1]["cross_platform_count"] == 1


def test_frequency_bonus_is_capped() -> None:
    """A ten-platform story must not run away with the score."""
    titles = [f"同一条热点消息内容{i}" for i in range(10)]
    titles = ["完全相同的热点标题"] * 10
    candidates = [_candidate(titles[0], f"platform{index}") for index in range(10)]

    ranked = rank_hotspots(candidates, categories=[], filters={"min_selection_score": 0})

    assert ranked[0]["cross_platform_count"] == 10
    assert ranked[0]["frequency_score"] == FREQUENCY_BONUS_CAP


def test_single_platform_candidate_gets_no_bonus() -> None:
    ranked = rank_hotspots([_candidate("独此一家", "weibo")], categories=[], filters={"min_selection_score": 0})

    assert ranked[0]["frequency_score"] == 0.0
    assert ranked[0]["cross_platform_count"] == 1


def test_score_components_are_all_reported() -> None:
    """Auditability: the operator can see how a score was assembled."""
    ranked = rank_hotspots([_candidate("热点", "weibo")], categories=[], filters={"min_selection_score": 0})

    for key in ("rank_score", "hot_value_score", "platform_weight_score", "category_bonus", "prefer_bonus", "frequency_score"):
        assert key in ranked[0]


def test_score_still_capped_at_100() -> None:
    candidates = [_candidate("同一条热点标题内容", f"p{index}", weight=10.0, hot_value=10_000_000) for index in range(5)]

    ranked = rank_hotspots(candidates, categories=["社会"], filters={"min_selection_score": 0})

    assert all(item["selection_score"] <= 100 for item in ranked)


def test_coverage_is_credited_even_when_a_row_is_later_filtered() -> None:
    """Coverage is measured over the whole pool, before the operator's keyword filters.

    ``exclude_keywords`` matches the *title*, so it drops the shortest headline below; the
    surviving rows must still report that the story appeared on three platforms.
    """
    candidates = [
        _candidate("西藏那曲市7.0级地震", "baidu"),
        _candidate("西藏7级地震", "weibo"),
        _candidate("西藏那曲巴青县发生7.0级地震", "toutiao"),
    ]

    ranked = rank_hotspots(
        candidates,
        categories=[],
        filters={"min_selection_score": 0, "exclude_keywords": ["西藏7级"]},
    )

    assert [item["platform_name"] for item in ranked] == ["baidu", "toutiao"]
    assert all(item["cross_platform_count"] == 3 for item in ranked)


# --------------------------------------------------------------------------- #
# deterministic selection
# --------------------------------------------------------------------------- #


def test_selection_is_no_longer_decided_by_platform_order() -> None:
    """Reordering the input must not change which story wins."""
    single = _candidate("只在单个平台出现的热点", "abcdef")
    quake = [_candidate(title, platform) for title, platform in zip(QUAKE_HEADLINES, ["toutiao", "baidu", "weibo"])]

    forward = rank_hotspots(quake + [single], categories=[], filters={"min_selection_score": 0})
    reverse = rank_hotspots([single] + quake, categories=[], filters={"min_selection_score": 0})

    assert pick_best_hotspot(forward)["cross_platform_count"] == 3
    assert pick_best_hotspot(reverse)["cross_platform_count"] == 3


def test_wider_coverage_wins_a_score_tie() -> None:
    """Two stories at the same score: the one on more platforms is the better pick."""
    # Both are rank 1 on equal-weight platforms, so only coverage separates them.
    one_platform = _candidate("甲热点内容", "weibo")
    three_platforms = [
        _candidate("乙热点内容", "weibo"),
        _candidate("乙热点内容", "zhihu"),
        _candidate("乙热点内容", "baidu"),
    ]

    ranked = rank_hotspots([one_platform] + three_platforms, categories=[], filters={"min_selection_score": 0})

    assert ranked[0]["cross_platform_count"] == 3


def test_dedupe_still_collapses_near_identical_rows() -> None:
    """The output shape is unchanged: dedupe still uses the stricter threshold."""
    candidates = [
        _candidate("完全一样的热点标题", "weibo"),
        _candidate("完全一样的热点标题", "zhihu"),
    ]

    ranked = rank_hotspots(candidates, categories=[], filters={"min_selection_score": 0})

    assert len(ranked) == 1


def test_dedupe_keeps_the_near_but_distinct_headlines() -> None:
    """Real cross-platform variants are below the dedupe bar, so they all survive."""
    candidates = [_candidate(title, platform) for title, platform in zip(QUAKE_HEADLINES, ["toutiao", "baidu", "weibo"])]

    ranked = rank_hotspots(candidates, categories=[], filters={"min_selection_score": 0})

    assert len(ranked) == 3, "the strict threshold must not collapse these"
    assert all(item["cross_platform_count"] == 3 for item in ranked)


@pytest.mark.parametrize("shuffle_seed", [1, 2, 3])
def test_ranking_is_stable_across_input_order(shuffle_seed: int) -> None:
    import random

    candidates = [_candidate(title, f"p{index}") for index, title in enumerate(QUAKE_HEADLINES + ["独立热点"])]
    shuffled = list(candidates)
    random.Random(shuffle_seed).shuffle(shuffled)

    ranked = rank_hotspots(shuffled, categories=[], filters={"min_selection_score": 0})

    assert ranked[0]["cross_platform_count"] == 3
