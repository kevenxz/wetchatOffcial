"""Failure alerting for workflow errors.

Disabled by default: alerts are opt-in through ``ALERT_WEBHOOK`` (a 企业微信 or
generic JSON webhook) and ``ALERT_EMAIL`` is reserved for a future SMTP channel.
Alert delivery never raises — a broken webhook must not turn a task failure into a
different failure.
"""
from __future__ import annotations

import os
from typing import Any, Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)

ALERT_TIMEOUT_SECONDS = 8.0
# Avoid alert storms: at most this many alerts per task per process run.
_MAX_ALERTS_PER_TASK = 3
_alert_counts: dict[str, int] = {}


def alert_webhook() -> str:
    """Configured alert webhook URL, or an empty string when disabled."""
    return (os.getenv("ALERT_WEBHOOK") or "").strip()


def emails_enabled() -> bool:
    """Whether email alerting is configured (reserved for a future SMTP channel)."""
    return bool((os.getenv("ALERT_EMAIL") or "").strip())


def reset_state() -> None:
    """Clear per-task alert counters (used by tests)."""
    _alert_counts.clear()


def _should_send(task_id: str) -> bool:
    count = _alert_counts.get(task_id, 0)
    if count >= _MAX_ALERTS_PER_TASK:
        return False
    _alert_counts[task_id] = count + 1
    return True


def _message_text(task_id: str, skill: str, error: str, status: str) -> str:
    return f"[微信公众号内容系统] 任务 {task_id} 在节点 {skill or 'workflow'} {status}：{error or '未知错误'}"


async def send_alert(
    *,
    task_id: str,
    skill: str = "",
    error: str = "",
    status: str = "failed",
    extra: Optional[dict[str, Any]] = None,
) -> bool:
    """Send one alert. Returns True only when it was actually delivered."""
    webhook = alert_webhook()
    if not webhook:
        return False
    if not _should_send(task_id):
        logger.info("alert_suppressed", task_id=task_id, reason="per-task alert budget reached")
        return False

    text = _message_text(task_id, skill, error, status)
    payload: dict[str, Any] = {"msgtype": "text", "text": {"content": text}}
    if extra:
        payload["context"] = extra

    try:
        async with httpx.AsyncClient(timeout=ALERT_TIMEOUT_SECONDS) as client:
            response = await client.post(webhook, json=payload)
            response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.warning("alert_delivery_failed", task_id=task_id, error=str(exc))
        return False

    logger.info("alert_sent", task_id=task_id, skill=skill, status=status)
    return True
