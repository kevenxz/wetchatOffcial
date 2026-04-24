"""Helpers for syncing workflow result payloads onto persisted tasks."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from api.models import TaskResponse, TaskStatus


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
    task.human_review_required = bool(
        result.get("human_review_required")
        or (task.quality_report and not task.quality_report.get("ready_to_publish"))
    )
