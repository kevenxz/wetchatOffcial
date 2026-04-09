"""Tests for hotspot capture schedule models and legacy compatibility."""
from __future__ import annotations

from api.models import CreateScheduleRequest, HotspotSource, ScheduleConfig, ScheduleMode, UpdateScheduleRequest


def test_schedule_config_hydrates_legacy_hot_topics_into_hotspot_capture() -> None:
    schedule = ScheduleConfig(
        schedule_id="schedule-1",
        name="财经热点任务",
        mode=ScheduleMode.interval,
        interval_minutes=30,
        hot_topics=[" AI ", "财经", "AI"],
        created_at="2026-04-03T00:00:00+00:00",
    )

    assert schedule.hot_topics == ["AI", "财经"]
    assert schedule.hotspot_capture.enabled is False
    assert schedule.hotspot_capture.source == HotspotSource.tophub
    assert schedule.hotspot_capture.fallback_topics == ["AI", "财经"]


def test_create_schedule_request_prefers_structured_hotspot_capture_and_normalizes_path() -> None:
    request = CreateScheduleRequest(
        name="综合热点任务",
        mode=ScheduleMode.interval,
        interval_minutes=60,
        hotspot_capture={
            "enabled": True,
            "categories": [" finance ", "AI", "finance"],
            "platforms": [
                {
                    "name": "知乎热榜",
                    "path": "https://tophub.today/n/mproPpoq6O",
                    "weight": 1.2,
                }
            ],
            "fallback_topics": ["大模型", " AI "],
        },
    )

    assert request.hot_topics == ["大模型", "AI"]
    assert request.hotspot_capture.enabled is True
    assert request.hotspot_capture.categories == ["finance", "AI"]
    assert request.hotspot_capture.platforms[0].path == "/n/mproPpoq6O"


def test_update_schedule_request_builds_hotspot_capture_from_legacy_hot_topics() -> None:
    request = UpdateScheduleRequest(hot_topics=["抖音", " 小红书 ", "抖音"])
    patch = request.model_dump(exclude_unset=True)

    assert request.hot_topics == ["抖音", "小红书"]
    assert request.hotspot_capture is not None
    assert request.hotspot_capture.fallback_topics == ["抖音", "小红书"]
    assert patch["hot_topics"] == ["抖音", "小红书"]
    assert patch["hotspot_capture"]["fallback_topics"] == ["抖音", "小红书"]
