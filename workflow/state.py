"""Workflow state definition shared by all LangGraph skills."""
from __future__ import annotations

from typing import Optional

from typing_extensions import TypedDict


class WorkflowState(TypedDict):
    """Global workflow state."""

    task_id: str
    keywords: str
    generation_config: dict

    user_intent: dict
    style_profile: dict
    article_blueprint: dict
    search_queries: list[dict]
    search_results: list[dict]
    extracted_contents: list[dict]

    article_plan: dict
    generated_article: dict
    draft_info: Optional[dict]

    retry_count: int
    error: Optional[str]
    status: str
    current_skill: str
    progress: int
    skip_auto_push: bool
