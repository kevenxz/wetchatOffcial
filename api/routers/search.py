"""Unified search across tasks, articles and hotspot topics."""
from __future__ import annotations

from fastapi import APIRouter, Query

from api.models import SearchResponse, TaskResponse
from api.store import task_store, topic_store

router = APIRouter(prefix="/search", tags=["search"])


def _matches(haystack: str, needle: str) -> bool:
    return needle in haystack.lower()


def _task_text(task: TaskResponse) -> str:
    article = dict(task.final_article or task.generated_article or {})
    parts = [
        task.task_id,
        task.keywords,
        task.original_keywords or "",
        str(article.get("title") or ""),
        str(article.get("summary") or ""),
        str((task.selected_hotspot or {}).get("title") or ""),
    ]
    return " ".join(part for part in parts if part)


@router.get("", response_model=SearchResponse)
async def search_all(
    q: str = Query(..., min_length=1, max_length=200, description="Search query"),
    limit: int = Query(default=20, ge=1, le=100),
) -> SearchResponse:
    """Search tasks, generated articles and hotspot topics in one call."""
    needle = q.strip().lower()
    if not needle:
        return SearchResponse()

    matched_tasks: list[TaskResponse] = []
    matched_articles: list[TaskResponse] = []
    for task in sorted(task_store.values(), key=lambda item: item.created_at, reverse=True):
        if not _matches(_task_text(task), needle):
            continue
        matched_tasks.append(task)
        if task.generated_article:
            matched_articles.append(task)

    matched_topics = [
        topic
        for topic in sorted(topic_store.values(), key=lambda item: item.created_at, reverse=True)
        if _matches(f"{topic.topic_id} {topic.title} {topic.summary} {topic.source}", needle)
    ]

    return SearchResponse(
        tasks=matched_tasks[:limit],
        articles=matched_articles[:limit],
        topics=matched_topics[:limit],
    )
