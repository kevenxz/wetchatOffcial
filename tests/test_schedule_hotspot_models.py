"""Tests for hotspot capture schedule models and legacy compatibility."""
from __future__ import annotations

from api.models import (
    CreateScheduleRequest,
    HotspotCaptureConfig,
    HotspotSource,
    ScheduleConfig,
    ScheduleMode,
    UpdateScheduleRequest,
)


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
    # A config with no explicit source defaults to `newsnow`, the structured multi-platform
    # source the background refresher fills the snapshot from. The field is descriptive only
    # (dispatch is per-platform), so this cannot change how an existing task is fetched.
    assert schedule.hotspot_capture.source == HotspotSource.newsnow
    assert schedule.hotspot_capture.fallback_topics == ["AI", "财经"]


def test_hotspot_capture_defaults_to_the_snapshot_backed_source() -> None:
    """Defaulting to `tophub` misreported what a new task would do, and TopHub is the
    unreliable live-scrape path (429 retries / source unavailable in production)."""
    assert HotspotCaptureConfig().source == HotspotSource.newsnow


def test_an_explicit_source_still_wins() -> None:
    assert HotspotCaptureConfig(source=HotspotSource.tophub).source == HotspotSource.tophub


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


def test_hotspot_platform_config_accepts_rss_provider_endpoint() -> None:
    request = CreateScheduleRequest(
        name="多源榜单任务",
        mode=ScheduleMode.interval,
        interval_minutes=60,
        hotspot_capture={
            "enabled": True,
            "platforms": [
                {
                    "name": "36氪快讯",
                    "path": "https://36kr.com/feed-newsflash",
                    "source": "rss_or_feed",
                    "provider_id": "36kr_newsflash",
                    "category": "科技",
                    "weight": 1.1,
                }
            ],
        },
    )

    platform = request.hotspot_capture.platforms[0]
    assert platform.source == HotspotSource.rss_or_feed
    assert platform.provider_id == "36kr_newsflash"
    assert platform.path == "https://36kr.com/feed-newsflash"


def test_update_schedule_request_builds_hotspot_capture_from_legacy_hot_topics() -> None:
    request = UpdateScheduleRequest(hot_topics=["抖音", " 小红书 ", "抖音"])
    patch = request.model_dump(exclude_unset=True)

    assert request.hot_topics == ["抖音", "小红书"]
    assert request.hotspot_capture is not None
    assert request.hotspot_capture.fallback_topics == ["抖音", "小红书"]
    assert patch["hot_topics"] == ["抖音", "小红书"]
    assert patch["hotspot_capture"]["fallback_topics"] == ["抖音", "小红书"]
