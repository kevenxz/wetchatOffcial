"""Tests for scheduler integration with hotspot capture flow."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from api.models import ScheduleConfig, ScheduleMode, ScheduleStatus, TaskStatus
from api.scheduler import SchedulerEngine
from api.store import schedule_store, task_store


@pytest.mark.asyncio
async def test_scheduler_run_now_updates_task_with_selected_hotspot() -> None:
    schedule_store_backup = dict(schedule_store)
    task_store_backup = dict(task_store)
    schedule_store.clear()
    task_store.clear()

    now = datetime.now(tz=timezone.utc)
    schedule = ScheduleConfig(
        schedule_id="schedule-hotspot-1",
        name="每日热点追踪",
        mode=ScheduleMode.interval,
        interval_minutes=60,
        hotspot_capture={
            "enabled": True,
            "source": "tophub",
            "categories": ["ai"],
            "platforms": [{"name": "知乎热榜", "path": "/n/mproPpoq6O", "weight": 1.0, "enabled": True}],
            "filters": {
                "top_n_per_platform": 10,
                "min_selection_score": 60,
                "exclude_keywords": [],
                "prefer_keywords": [],
            },
            "fallback_topics": ["人工智能"],
        },
        enabled=True,
        status=ScheduleStatus.running,
        created_at=now,
    )
    schedule_store[schedule.schedule_id] = schedule
    engine = SchedulerEngine()

    async def fake_run_workflow(*, task_id, keywords, generation_config, hotspot_capture_config, progress_callback, skip_auto_push):  # type: ignore[no-untyped-def]
        assert keywords == "每日热点追踪"
        assert hotspot_capture_config.get("enabled") is True
        await progress_callback(
            task_id,
            {
                "task_id": task_id,
                "status": "done",
                "current_skill": "",
                "progress": 100,
                "message": "workflow done",
                "result": {
                    "keywords": "OpenAI 新模型发布",
                    "original_keywords": "每日热点追踪",
                    "hotspot_capture_config": hotspot_capture_config,
                    "hotspot_candidates": [{"title": "OpenAI 新模型发布", "selection_score": 91.2}],
                    "selected_hotspot": {"title": "OpenAI 新模型发布", "platform_name": "知乎热榜"},
                    "generation_config": generation_config,
                    "user_intent": {},
                    "style_profile": {},
                    "article_blueprint": {},
                    "article_plan": {},
                    "generated_article": {"title": "文章标题", "content": "正文"},
                    "draft_info": None,
                },
            },
        )
        return {}

    try:
        with patch("api.scheduler.run_workflow", side_effect=fake_run_workflow), patch("api.scheduler.save_schedules"), patch("api.scheduler.save_tasks"):
            task_id = await engine.run_now(schedule.schedule_id)

        task = task_store[task_id]
        assert task.status == TaskStatus.done
        assert task.keywords == "OpenAI 新模型发布"
        assert task.original_keywords == "每日热点追踪"
        assert task.selected_hotspot is not None
        assert task.selected_hotspot["platform_name"] == "知乎热榜"
    finally:
        schedule_store.clear()
        schedule_store.update(schedule_store_backup)
        task_store.clear()
        task_store.update(task_store_backup)


@pytest.mark.asyncio
async def test_scheduler_progress_callback_persists_agent_state_blocks() -> None:
    schedule_store_backup = dict(schedule_store)
    task_store_backup = dict(task_store)
    schedule_store.clear()
    task_store.clear()

    now = datetime.now(tz=timezone.utc)
    schedule = ScheduleConfig(
        schedule_id="schedule-agent-1",
        name="Agent 重构验证",
        mode=ScheduleMode.interval,
        interval_minutes=60,
        enabled=True,
        status=ScheduleStatus.running,
        created_at=now,
    )
    schedule_store[schedule.schedule_id] = schedule
    engine = SchedulerEngine()

    async def fake_run_workflow(*, task_id, keywords, generation_config, hotspot_capture_config, progress_callback, skip_auto_push):  # type: ignore[no-untyped-def]
        await progress_callback(
            task_id,
            {
                "task_id": task_id,
                "status": "done",
                "current_skill": "",
                "progress": 100,
                "message": "workflow done",
                "result": {
                    "generation_config": generation_config,
                    "task_brief": {"topic": keywords},
                    "planning_state": {"article_type": {"type_id": "trend_analysis"}},
                    "research_state": {"evidence_pack": {"confirmed_facts": [{"claim": "A"}]}},
                    "writing_state": {"draft": {"title": "标题", "content": "正文"}},
                    "visual_state": {"image_briefs": [{"role": "cover"}]},
                    "quality_state": {
                        "next_action": "pass",
                        "ready_to_publish": True,
                        "quality_report": {
                            "article_score": 84,
                            "visual_score": 82,
                            "ready_to_publish": True,
                            "blocking_reasons": [],
                        },
                    },
                    "generated_article": {"title": "标题", "content": "正文"},
                    "draft_info": None,
                },
            },
        )
        return {}

    try:
        with patch("api.scheduler.run_workflow", side_effect=fake_run_workflow), patch("api.scheduler.save_schedules"), patch("api.scheduler.save_tasks"):
            task_id = await engine.run_now(schedule.schedule_id)

        task = task_store[task_id]
        assert task.task_brief == {"topic": "Agent 重构验证"}
        assert task.planning_state == {"article_type": {"type_id": "trend_analysis"}}
        assert task.quality_state["next_action"] == "pass"
        assert task.quality_report["article_score"] == 84
        assert task.quality_report["ready_to_publish"] is True
    finally:
        schedule_store.clear()
        schedule_store.update(schedule_store_backup)
        task_store.clear()
        task_store.update(task_store_backup)
