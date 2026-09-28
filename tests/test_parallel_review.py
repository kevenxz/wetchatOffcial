"""Tests for the concurrent review node."""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from workflow.nodes.parallel_review import parallel_review_node


def _state() -> dict:
    return {
        "task_id": "task-review",
        "task_brief": {"topic": "机器人融资"},
        "writing_state": {"draft": {"title": "标题", "content": "正文"}},
        "viral_state": {"strategy": {"core_promise": "给出判断"}},
        "research_state": {"evidence_pack": {}},
        "config_snapshot": {"review_policy": {"viral_threshold": 78}},
    }


@pytest.mark.asyncio
async def test_reviews_run_concurrently_when_draft_has_no_hard_failure() -> None:
    active = 0
    max_active = 0

    async def fake_article(state: dict) -> dict:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.05)
        active -= 1
        return {
            "writing_state": {
                "article_review": {"passed": True, "score": 88},
                "review_findings": [],
                "revision_guidance": [],
            }
        }

    async def fake_viral(state: dict) -> dict:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.05)
        active -= 1
        return {"viral_state": {"review": {"score": 80, "passed": True, "dimensions": {}}}}

    with patch("workflow.nodes.parallel_review.review_article_draft_node", side_effect=fake_article):
        with patch("workflow.nodes.parallel_review.review_viral_potential_node", side_effect=fake_viral):
            result = await parallel_review_node(_state())

    assert max_active > 1, "reviews were executed serially"
    assert result["writing_state"]["article_review"]["score"] == 88
    assert result["viral_state"]["review"]["score"] == 80


@pytest.mark.asyncio
async def test_hard_structural_failure_cancels_the_virality_review() -> None:
    viral_started = asyncio.Event()
    viral_cancelled = False

    async def fake_article(state: dict) -> dict:
        # Let the virality call start first, then report a hard structural failure.
        await asyncio.wait_for(viral_started.wait(), timeout=1)
        return {
            "writing_state": {
                "article_review": {"passed": False, "score": 40},
                "review_findings": [{"type": "planning_language", "message": "正文暴露了编辑语言"}],
                "revision_guidance": ["删除编辑备注"],
            }
        }

    async def fake_viral(state: dict) -> dict:
        nonlocal viral_cancelled
        viral_started.set()
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            viral_cancelled = True
            raise
        return {"viral_state": {"review": {"score": 99}}}

    with patch("workflow.nodes.parallel_review.review_article_draft_node", side_effect=fake_article):
        with patch("workflow.nodes.parallel_review.review_viral_potential_node", side_effect=fake_viral):
            result = await parallel_review_node(_state())

    assert viral_cancelled, "the wasted virality call was not cancelled"
    assert result["writing_state"]["article_review"]["passed"] is False
    # The short-circuit leaves the previous virality state untouched.
    assert "review" not in result["viral_state"]


@pytest.mark.asyncio
async def test_virality_failure_does_not_break_the_review_branch() -> None:
    async def fake_article(state: dict) -> dict:
        return {
            "writing_state": {
                "article_review": {"passed": True, "score": 85},
                "review_findings": [],
                "revision_guidance": [],
            }
        }

    async def fake_viral(state: dict) -> dict:
        raise RuntimeError("critic unavailable")

    with patch("workflow.nodes.parallel_review.review_article_draft_node", side_effect=fake_article):
        with patch("workflow.nodes.parallel_review.review_viral_potential_node", side_effect=fake_viral):
            result = await parallel_review_node(_state())

    assert result["writing_state"]["article_review"]["score"] == 85
    assert result["viral_state"] == {"strategy": {"core_promise": "给出判断"}}
