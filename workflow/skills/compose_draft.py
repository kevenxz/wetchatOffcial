"""Compose article draft from blueprint and evidence pack."""
from __future__ import annotations

from typing import Any

from workflow.state import WorkflowState


async def compose_draft_node(state: WorkflowState) -> dict[str, Any]:
    """Generate the first article draft from the dynamic blueprint."""
    blueprint = dict(state.get("planning_state", {}).get("article_blueprint") or {})
    sections = blueprint.get("sections") or []
    title = blueprint.get("thesis") or state.get("task_brief", {}).get("topic", "未命名主题")
    content = "\n\n".join([f"## {section['heading']}\n{section['goal']}" for section in sections])
    return {
        "status": "running",
        "current_skill": "compose_draft",
        "progress": 54,
        "writing_state": {
            "draft": {"title": title, "content": content},
            "review_findings": [],
        },
        "generated_article": {"title": title, "content": content},
    }
