"""Tests for capture_hot_topics workflow skill."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from workflow.agents.hotspot import capture_hot_topics_node


@pytest.mark.asyncio
async def test_capture_hot_topics_passthrough_when_disabled() -> None:
    state = {
        "task_id": "task-1",
        "keywords": "原始主题",
        "original_keywords": "原始主题",
        "hotspot_capture_config": {"enabled": False},
    }

    result = await capture_hot_topics_node(state)  # type: ignore[arg-type]

    assert result["status"] == "running"
    assert result["keywords"] == "原始主题"
    assert result["selected_hotspot"] is None


@pytest.mark.asyncio
async def test_capture_hot_topics_selects_high_score_item() -> None:
    state = {
        "task_id": "task-2",
        "keywords": "调度任务名称",
        "original_keywords": "调度任务名称",
        "hotspot_capture_config": {
            "enabled": True,
            "source": "tophub",
            "categories": ["ai"],
            "platforms": [
                {"name": "知乎热榜", "path": "/n/mproPpoq6O", "weight": 1.0, "enabled": True},
            ],
            "filters": {
                "top_n_per_platform": 10,
                "min_selection_score": 10,
                "exclude_keywords": [],
                "prefer_keywords": [],
            },
            "fallback_topics": ["回退主题"],
        },
    }

    async def fake_fetch_platform_hot_items(*args, **kwargs):
        return [
            {
                "source": "tophub",
                "category": "ai",
                "platform_name": "知乎热榜",
                "platform_path": "/n/mproPpoq6O",
                "platform_weight": 1.0,
                "title": "OpenAI 新模型发布",
                "url": "https://example.com/a",
                "rank": 1,
                "extra_text": "12000",
                "hot_value": 12000,
                "captured_at": "2026-04-07T00:00:00+00:00",
            }
        ]

    with patch(
        "workflow.agents.hotspot.TopHubClient.fetch_platform_hot_items",
        side_effect=fake_fetch_platform_hot_items,
    ):
        result = await capture_hot_topics_node(state)  # type: ignore[arg-type]

    assert result["keywords"] == "OpenAI 新模型发布"
    assert result["selected_hotspot"] is not None
    assert result["selected_hotspot"]["platform_name"] == "知乎热榜"
