"""Workflow state definition shared by all LangGraph skills."""
from __future__ import annotations

from typing import Optional

from typing_extensions import TypedDict


class WorkflowState(TypedDict, total=False):
    """Global workflow state."""

    task_id: str
    mode: str
    keywords: str
    original_keywords: str
    generation_config: dict
    config_snapshot: dict
    hotspot_capture_config: dict
    task_brief: dict
    planning_state: dict
    research_state: dict
    writing_state: dict
    visual_state: dict
    quality_state: dict
    quality_report: dict
    human_review_required: bool

    user_intent: dict
    style_profile: dict
    article_blueprint: dict
    search_queries: list[dict]
    search_results: list[dict]
    extracted_contents: list[dict]
    hotspot_candidates: list[dict]
    selected_hotspot: Optional[dict]
    selected_topic: Optional[dict]
    hotspot_capture_error: Optional[str]

    article_plan: dict
    outline_result: dict
    generated_article: dict
    final_article: dict
    draft_info: Optional[dict]

    retry_count: int
    error: Optional[str]
    status: str
    current_skill: str
    progress: int
    skip_auto_push: bool
    revision_count: int
