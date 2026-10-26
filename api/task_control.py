"""Run-control for workflow tasks: concurrency gating, cancellation, resumption.

Single-process deployment notes: the cancellation registry and the concurrency
gate live in process memory. Redis is used only to broadcast a cancellation so a
second process (if ever started) also stops, never as the source of truth.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

import structlog

from workflow import runtime_settings
from workflow.utils.redis_client import get_redis

logger = structlog.get_logger(__name__)

CANCEL_CHANNEL = "workflow:cancel"

_cancelled: set[str] = set()
_running: dict[str, asyncio.Task] = {}
_gate: Optional[asyncio.Semaphore] = None


def workflow_gate() -> asyncio.Semaphore:
    """Process-wide gate limiting how many workflows run at once."""
    global _gate
    limit = runtime_settings.workflow_max_concurrency()
    if _gate is None or getattr(_gate, "_dsh_limit", None) != limit:
        _gate = asyncio.Semaphore(limit)
        setattr(_gate, "_dsh_limit", limit)
    return _gate


def available_slots() -> int:
    """Approximate number of free workflow slots (diagnostics)."""
    return runtime_settings.workflow_max_concurrency() - len(_running)


def register_running(task_id: str, task: asyncio.Task) -> None:
    """Track the asyncio task executing one workflow."""
    _running[task_id] = task


def unregister_running(task_id: str) -> None:
    """Forget a finished workflow."""
    _running.pop(task_id, None)


def running_task_ids() -> list[str]:
    """Task ids currently executing in this process."""
    return sorted(_running)


def is_cancelled(task_id: str) -> bool:
    """Whether cancellation was requested for one task."""
    return task_id in _cancelled


def mark_cancelled(task_id: str) -> None:
    """Record a local cancellation request."""
    _cancelled.add(task_id)


def clear_cancelled(task_id: str) -> None:
    """Forget a cancellation request (used when a task is retried)."""
    _cancelled.discard(task_id)


def reset_state() -> None:
    """Clear all run-control state (used by tests)."""
    global _gate
    _cancelled.clear()
    _running.clear()
    _gate = None


async def request_cancel(task_id: str) -> bool:
    """Request cancellation and stop the local asyncio task when present.

    Returns True when a running workflow was actively stopped.
    """
    mark_cancelled(task_id)

    client = await get_redis()
    if client is not None:
        try:
            await client.publish(CANCEL_CHANNEL, task_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("cancel_publish_failed", task_id=task_id, error=str(exc))

    task = _running.get(task_id)
    if task is None or task.done():
        return False
    task.cancel()
    return True


class TaskCancelledError(RuntimeError):
    """Raised inside a node when the enclosing task was cancelled."""


def raise_if_cancelled(task_id: str) -> None:
    """Abort the current node when the task has been cancelled."""
    if is_cancelled(task_id):
        raise TaskCancelledError(f"task {task_id} was cancelled")


async def run_gated(
    task_id: str,
    coro: Any,
    *,
    progress_callback: Any = None,
    on_queued: Any = None,
) -> Any:
    """Run one workflow coroutine under the concurrency gate.

    While waiting for a slot the task is reported as ``queued`` so the UI can show
    an honest state instead of an indefinite "pending".
    """
    gate = workflow_gate()
    if gate.locked() and on_queued is not None:
        await on_queued()

    async with gate:
        if is_cancelled(task_id):
            raise TaskCancelledError(f"task {task_id} was cancelled before it started")
        return await coro
