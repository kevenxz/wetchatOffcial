from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from api.models import GenerationConfig, TaskResponse, TaskStatus
from api.routers.tasks import _progress_callback
from api.store import review_store, task_store


@pytest.mark.asyncio
async def test_tasks_progress_callback_persists_quality_report() -> None:
    task_store_backup = dict(task_store)
    task_store.clear()
    task = TaskResponse(
        task_id="task-progress-1",
        keywords="机器人商业化",
        original_keywords="机器人商业化",
        generation_config=GenerationConfig(),
        status=TaskStatus.pending,
        created_at=datetime.now(tz=timezone.utc),
    )
    task_store[task.task_id] = task

    payload = {
        "task_id": task.task_id,
        "status": "done",
        "current_skill": "",
        "progress": 100,
        "message": "workflow done",
        "result": {
            "quality_state": {
                "next_action": "pass",
                "ready_to_publish": True,
                "quality_report": {
                    "article_score": 86,
                    "visual_score": 83,
                    "ready_to_publish": True,
                    "blocking_reasons": [],
                },
            },
            "generated_article": {"title": "标题", "content": "正文"},
        },
    }

    try:
        with patch("api.routers.tasks.save_tasks"), patch("api.routers.tasks.manager.broadcast", new=AsyncMock()):
            await _progress_callback(task.task_id, payload)

        saved_task = task_store[task.task_id]
        assert saved_task.status == TaskStatus.done
        assert saved_task.quality_state["next_action"] == "pass"
        assert saved_task.quality_report["article_score"] == 86
    finally:
        task_store.clear()
        task_store.update(task_store_backup)


@pytest.mark.asyncio
async def test_tasks_progress_callback_creates_review_queue_item() -> None:
    task_store_backup = dict(task_store)
    review_store_backup = dict(review_store)
    task_store.clear()
    review_store.clear()
    task = TaskResponse(
        task_id="task-review-required",
        keywords="高风险财经选题",
        original_keywords="高风险财经选题",
        generation_config=GenerationConfig(),
        status=TaskStatus.pending,
        created_at=datetime.now(tz=timezone.utc),
    )
    task_store[task.task_id] = task

    payload = {
        "task_id": task.task_id,
        "status": "done",
        "current_skill": "",
        "progress": 100,
        "message": "workflow done",
        "result": {
            "human_review_required": True,
            "quality_state": {
                "next_action": "human_review",
                "ready_to_publish": False,
                "quality_report": {
                    "article_score": 60,
                    "visual_score": 80,
                    "ready_to_publish": False,
                    "blocking_reasons": ["article_score_below_threshold"],
                },
            },
            "final_article": {"title": "高风险财经选题", "content": "正文"},
        },
    }

    try:
        with (
            patch("api.routers.tasks.save_tasks"),
            patch("api.workflow_sync.create_review") as create_review_mock,
            patch("api.routers.tasks.manager.broadcast", new=AsyncMock()),
        ):
            await _progress_callback(task.task_id, payload)

        saved_task = task_store[task.task_id]
        assert saved_task.human_review_required is True
        create_review_mock.assert_called_once()
        review_item = create_review_mock.call_args.args[0]
        assert review_item.target_id == task.task_id
        assert review_item.payload["blocking_reasons"] == ["article_score_below_threshold"]
    finally:
        task_store.clear()
        task_store.update(task_store_backup)
        review_store.clear()
        review_store.update(review_store_backup)
