"""Helpers for syncing workflow result payloads onto persisted tasks."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from api.models import PushRecord, ReviewQueueItem, ReviewTargetType, TaskResponse, TaskStatus
from api.store import create_review, get_review


def sync_task_from_workflow_event(task: TaskResponse, data: dict[str, Any]) -> None:
    """Apply a workflow progress event to a TaskResponse in-place."""
    new_status = data.get("status", task.status)
    task.status = TaskStatus(new_status)
    task.updated_at = datetime.now(tz=timezone.utc)
    if new_status == "failed":
        task.error = data.get("message")

    if new_status not in ("done", "failed") or not data.get("result"):
        return

    result = data["result"]
    if not isinstance(result, dict):
        return

    next_mode = result.get("mode")
    if isinstance(next_mode, str):
        task.mode = next_mode

    config_snapshot = result.get("config_snapshot")
    if isinstance(config_snapshot, dict):
        task.config_snapshot = config_snapshot

    next_generation_config = result.get("generation_config")
    if isinstance(next_generation_config, dict):
        task.generation_config = task.generation_config.model_copy(update=next_generation_config)

    next_keywords = result.get("keywords")
    if isinstance(next_keywords, str) and next_keywords.strip():
        task.keywords = next_keywords.strip()

    next_original_keywords = result.get("original_keywords")
    if isinstance(next_original_keywords, str) and next_original_keywords.strip():
        task.original_keywords = next_original_keywords.strip()

    hotspot_capture_config = result.get("hotspot_capture_config")
    if isinstance(hotspot_capture_config, dict):
        task.hotspot_capture_config = hotspot_capture_config

    hotspot_candidates = result.get("hotspot_candidates")
    if isinstance(hotspot_candidates, list):
        task.hotspot_candidates = hotspot_candidates

    selected_hotspot = result.get("selected_hotspot")
    if isinstance(selected_hotspot, dict) or selected_hotspot is None:
        task.selected_hotspot = selected_hotspot

    selected_topic = result.get("selected_topic")
    if isinstance(selected_topic, dict) or selected_topic is None:
        task.selected_topic = selected_topic

    hotspot_capture_error = result.get("hotspot_capture_error")
    if isinstance(hotspot_capture_error, str) or hotspot_capture_error is None:
        task.hotspot_capture_error = hotspot_capture_error

    for field_name in (
        "task_brief",
        "planning_state",
        "research_state",
        "writing_state",
        "visual_state",
        "quality_state",
        "user_intent",
        "style_profile",
        "article_blueprint",
        "article_plan",
        "outline_result",
        "generated_article",
        "final_article",
        "draft_info",
    ):
        setattr(task, field_name, result.get(field_name))

    task.quality_report = (
        result.get("quality_report")
        or dict(task.quality_state or {}).get("quality_report")
        or None
    )
    _sync_push_records(task, result)

    completed_nodes = result.get("completed_nodes")
    if isinstance(completed_nodes, list):
        task.completed_nodes = [str(item) for item in completed_nodes]

    task.human_review_required = bool(
        result.get("human_review_required")
        or (task.quality_report and not task.quality_report.get("ready_to_publish"))
    )
    if task.human_review_required:
        _ensure_review_queue_item(task)


def _sync_push_records(task: TaskResponse, result: dict[str, Any]) -> None:
    """Append push records produced by the workflow's own push node.

    Records are de-duplicated by push id so a resumed run never doubles them.
    """
    raw_records = result.get("publish_records")
    if not isinstance(raw_records, list) or not raw_records:
        return

    existing_ids = {record.push_id for record in task.push_records}
    for raw in raw_records:
        if not isinstance(raw, dict):
            continue
        push_id = str(raw.get("push_id") or "")
        if not push_id or push_id in existing_ids:
            continue
        try:
            task.push_records.append(PushRecord(**raw))
        except Exception:  # noqa: BLE001
            # A malformed record must never break task persistence.
            continue
        existing_ids.add(push_id)

    theme_name = result.get("article_theme")
    if isinstance(theme_name, str) and theme_name.strip():
        task.article_theme = theme_name.strip()


def _ensure_review_queue_item(task: TaskResponse) -> None:
    review_id = f"task-review-{task.task_id}"
    if get_review(review_id) is not None:
        return
    quality_report = task.quality_report or {}
    final_article = task.final_article or task.generated_article or {}
    title = (
        str(final_article.get("title") or "").strip()
        or str(task.keywords or "").strip()
        or f"任务 {task.task_id} 人工审核"
    )
    create_review(
        ReviewQueueItem(
            review_id=review_id,
            target_type=ReviewTargetType.task,
            target_id=task.task_id,
            title=title,
            payload={
                "task_id": task.task_id,
                "quality_report": quality_report,
                "quality_state": task.quality_state or {},
                "final_article": final_article,
                "risk_summary": "、".join(list(quality_report.get("blocking_reasons") or [])),
                "article_score": quality_report.get("article_score"),
                "visual_score": quality_report.get("visual_score"),
                "blocking_reasons": list(quality_report.get("blocking_reasons") or []),
            },
            created_at=datetime.now(tz=timezone.utc),
        )
    )
