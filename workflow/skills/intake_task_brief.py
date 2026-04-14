"""Normalize workflow input into a task brief for planner-led execution."""
from __future__ import annotations

from typing import Any

from workflow.article_generation import normalize_generation_config
from workflow.state import WorkflowState


async def intake_task_brief_node(state: WorkflowState) -> dict[str, Any]:
    """Create the normalized task brief used by the redesigned workflow."""
    config = normalize_generation_config(state.get("generation_config"))
    brief = {
        "topic": str(state.get("keywords") or "").strip(),
        "original_topic": str(state.get("original_keywords") or state.get("keywords") or "").strip(),
        "audience_roles": list(config.get("audience_roles") or []),
        "article_goal": str(config.get("article_goal") or "").strip(),
        "runtime_profile": str(config.get("runtime_profile") or "quality_first"),
        "image_policy": dict(config.get("image_policy") or {}),
        "hotspot_policy": dict(state.get("hotspot_capture_config") or {}),
    }
    return {
        "status": "running",
        "current_skill": "intake_task_brief",
        "progress": 6,
        "generation_config": config,
        "task_brief": brief,
    }
