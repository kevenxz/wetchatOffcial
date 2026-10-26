"""Tests for task cancellation and the workflow concurrency gate."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api import task_control
from api.models import GenerationConfig, TaskResponse, TaskStatus
from api.routers.tasks import cancel_task, retry_task
from api.store import task_store


def _task(task_id: str = "task-cancel", status: TaskStatus = TaskStatus.running) -> TaskResponse:
    return TaskResponse(
        task_id=task_id,
        keywords="机器人商业化",
        original_keywords="机器人商业化",
        generation_config=GenerationConfig(),
        status=status,
        created_at=datetime.now(tz=timezone.utc),
    )


@pytest.fixture(autouse=True)
def _clean_state():
    backup = dict(task_store)
    task_store.clear()
    task_control.reset_state()
    yield
    task_store.clear()
    task_store.update(backup)
    task_control.reset_state()


@pytest.mark.asyncio
async def test_cancel_marks_a_running_task_cancelled() -> None:
    task_store["task-cancel"] = _task()

    with patch("api.routers.tasks.save_tasks"), patch("api.routers.tasks.manager.broadcast", new=AsyncMock()):
        result = await cancel_task("task-cancel")

    assert result.status == TaskStatus.cancelled
    assert task_control.is_cancelled("task-cancel") is True


@pytest.mark.asyncio
async def test_cancel_rejects_finished_tasks() -> None:
    task_store["task-cancel"] = _task(status=TaskStatus.done)

    with pytest.raises(HTTPException) as excinfo:
        await cancel_task("task-cancel")

    assert excinfo.value.status_code == 400


@pytest.mark.asyncio
async def test_cancel_unknown_task_returns_404() -> None:
    with pytest.raises(HTTPException) as excinfo:
        await cancel_task("missing")
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_request_cancel_stops_the_running_asyncio_task() -> None:
    async def long_running() -> None:
        await asyncio.sleep(30)

    running = asyncio.create_task(long_running())
    task_control.register_running("task-x", running)

    with patch("api.task_control.get_redis", new_callable=AsyncMock, return_value=None):
        stopped = await task_control.request_cancel("task-x")

    assert stopped is True
    await asyncio.sleep(0)
    assert running.cancelled() or running.done()
    running.cancel()


@pytest.mark.asyncio
async def test_cancelled_task_aborts_before_starting() -> None:
    task_control.mark_cancelled("task-y")

    async def work() -> str:
        return "should not run"

    coro = work()
    try:
        with pytest.raises(task_control.TaskCancelledError):
            await task_control.run_gated("task-y", coro)
    finally:
        coro.close()


@pytest.mark.asyncio
async def test_retry_clears_a_previous_cancellation() -> None:
    task_control.mark_cancelled("task-cancel")
    task_store["task-cancel"] = _task(status=TaskStatus.cancelled)

    with patch("api.routers.tasks.save_tasks"):
        with patch("api.routers.tasks.asyncio.create_task") as mock_create_task:
            result = await retry_task("task-cancel")

    assert result.status == TaskStatus.pending
    assert task_control.is_cancelled("task-cancel") is False
    mock_create_task.assert_called_once()


@pytest.mark.asyncio
async def test_retry_is_rejected_while_running() -> None:
    task_store["task-cancel"] = _task(status=TaskStatus.running)

    with pytest.raises(HTTPException) as excinfo:
        await retry_task("task-cancel")

    assert excinfo.value.status_code == 400


@pytest.mark.asyncio
async def test_concurrency_gate_serializes_workflows() -> None:
    """With a limit of 1, the second workflow must wait for the first."""
    order: list[str] = []

    async def work(name: str, delay: float) -> str:
        order.append(f"start-{name}")
        await asyncio.sleep(delay)
        order.append(f"end-{name}")
        return name

    with patch.dict("os.environ", {"WORKFLOW_MAX_CONCURRENCY": "1"}, clear=False):
        task_control.reset_state()
        first = asyncio.create_task(task_control.run_gated("t1", work("first", 0.05)))
        await asyncio.sleep(0.01)
        second = asyncio.create_task(task_control.run_gated("t2", work("second", 0.01)))
        await asyncio.gather(first, second)

    assert order == ["start-first", "end-first", "start-second", "end-second"]


@pytest.mark.asyncio
async def test_queue_notification_fires_when_gate_is_busy() -> None:
    queued_calls: list[str] = []

    async def on_queued() -> None:
        queued_calls.append("queued")

    async def work() -> str:
        await asyncio.sleep(0.03)
        return "done"

    with patch.dict("os.environ", {"WORKFLOW_MAX_CONCURRENCY": "1"}, clear=False):
        task_control.reset_state()
        first = asyncio.create_task(task_control.run_gated("t1", work()))
        await asyncio.sleep(0.005)
        second = asyncio.create_task(task_control.run_gated("t2", work(), on_queued=on_queued))
        await asyncio.gather(first, second)

    assert queued_calls == ["queued"]
