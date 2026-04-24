"""Normalize workflow input into a task brief for planner-led execution."""
from __future__ import annotations

from typing import Any

from workflow.article_generation import normalize_generation_config
from workflow.state import WorkflowState


async def intake_task_brief_node(state: WorkflowState) -> dict[str, Any]:
    """Create the normalized task brief used by the redesigned workflow."""
    config = normalize_generation_config(state.get("generation_config"))
    config_snapshot = dict(state.get("config_snapshot") or {})
    account_profile = dict(config_snapshot.get("account_profile") or {})
    content_template = dict(config_snapshot.get("content_template") or {})
    review_policy = dict(config_snapshot.get("review_policy") or {})
    image_policy = dict(config_snapshot.get("image_policy") or {})
    publish_policy = dict(config_snapshot.get("publish_policy") or {})
    brief = {
        "topic": str(state.get("keywords") or "").strip(),
        "original_topic": str(state.get("original_keywords") or state.get("keywords") or "").strip(),
        "mode": str(state.get("mode") or config_snapshot.get("mode") or "manual"),
        "audience_roles": list(config.get("audience_roles") or []),
        "article_goal": str(config.get("article_goal") or "").strip(),
        "runtime_profile": str(config.get("runtime_profile") or "quality_first"),
        "account_profile": account_profile,
        "content_template": content_template,
        "review_policy": review_policy,
        "image_policy": image_policy,
        "publish_policy": publish_policy,
        "hotspot_policy": dict(state.get("hotspot_capture_config") or {}),
        "selected_hotspot": state.get("selected_hotspot"),
        "hotspot_candidates_count": len(list(state.get("hotspot_candidates") or [])),
        "hotspot_capture_error": state.get("hotspot_capture_error"),
        "fallback_used": bool(state.get("hotspot_capture_error")),
    }
    return {
        "status": "running",
        "current_skill": "intake_task_brief",
        "progress": 6,
        "generation_config": config,
        "task_brief": brief,
        "config_snapshot": {
            **config_snapshot,
            "generation": config,
        },
    }
