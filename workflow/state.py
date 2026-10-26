"""Workflow state definition shared by all LangGraph skills."""
from __future__ import annotations

from typing import Annotated, Optional

from typing_extensions import TypedDict


def merge_status(current: Optional[str], incoming: Optional[str]) -> Optional[str]:
    """Merge concurrent status writes, letting a terminal state win.

    The graph fans out in two places, so two nodes can report ``status`` in the
    same step. Without a reducer LangGraph raises ``InvalidUpdateError``; with a
    naive last-wins reducer a failing branch could be masked by a healthy one, so
    failure and cancellation outrank every non-terminal state.
    """
    if current is None:
        return incoming
    if incoming is None:
        return current

    rank = {"failed": 3, "cancelled": 3, "done": 2, "running": 1, "pending": 0, "queued": 0}
    return incoming if rank.get(str(incoming), 1) > rank.get(str(current), 1) else current


def merge_progress(current: Optional[int], incoming: Optional[int]) -> Optional[int]:
    """Keep the furthest progress reported by any concurrent branch."""
    if current is None:
        return incoming
    if incoming is None:
        return current
    return max(int(current), int(incoming))


def merge_current_skill(current: Optional[str], incoming: Optional[str]) -> Optional[str]:
    """Label the running stage.

    Concurrent branches make this inherently ambiguous; the last writer wins and
    the following join node immediately overwrites it with a deterministic value.
    An empty incoming value never erases a known label.
    """
    if incoming in (None, ""):
        return current
    return incoming


def merge_error(current: Optional[str], incoming: Optional[str]) -> Optional[str]:
    """Preserve the first (or any) error message rather than dropping it."""
    if incoming in (None, ""):
        return current
    return incoming


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
    viral_state: dict
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
    # The hotspot's own article, read before deciding the article structure.
    hotspot_sources: list[dict]
    hotspot_source_status: Optional[str]
    hotspot_source_error: Optional[str]
    # Queries derived from the hotspot's own article, fed to the research planner.
    hotspot_source_queries: list[dict]

    article_plan: dict
    outline_result: dict
    generated_article: dict
    final_article: dict
    draft_info: Optional[dict]
    publish_targets: list[dict]
    publish_records: list[dict]
    article_theme: Optional[str]

    retry_count: int
    error: Annotated[Optional[str], merge_error]
    status: Annotated[str, merge_status]
    current_skill: Annotated[str, merge_current_skill]
    progress: Annotated[int, merge_progress]
    skip_auto_push: bool
    revision_count: int
    completed_nodes: list[str]
