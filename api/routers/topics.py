"""Topic candidate routes."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query

from api.models import (
    ConvertTopicToTaskRequest,
    CreateTopicCandidateRequest,
    TaskResponse,
    TaskStatus,
    TopicCandidate,
    TopicStatus,
    UpdateTopicCandidateRequest,
)
from api.store import (
    create_topic,
    get_topic,
    list_topics,
    save_tasks,
    task_store,
    update_topic,
)

router = APIRouter(prefix="/topics", tags=["topics"])


@router.get("", response_model=list[TopicCandidate])
async def get_topics(
    status: Annotated[TopicStatus | None, Query(description="Filter by topic status")] = None,
) -> list[TopicCandidate]:
    return list_topics(status.value if status else None)


@router.post("", response_model=TopicCandidate, status_code=201)
async def add_topic(body: CreateTopicCandidateRequest) -> TopicCandidate:
    topic = TopicCandidate(
        topic_id=str(uuid.uuid4()),
        title=body.title,
        summary=body.summary,
        source=body.source,
        url=body.url,
        score=body.score,
        tags=body.tags,
        metadata=body.metadata,
        created_at=datetime.now(tz=timezone.utc),
    )
    return create_topic(topic)


@router.get("/{topic_id}", response_model=TopicCandidate)
async def get_topic_detail(
    topic_id: Annotated[str, Path(description="Topic ID")],
) -> TopicCandidate:
    topic = get_topic(topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail=f"topic {topic_id!r} not found")
    return topic


@router.put("/{topic_id}", response_model=TopicCandidate)
async def edit_topic(
    topic_id: Annotated[str, Path(description="Topic ID")],
    body: UpdateTopicCandidateRequest,
) -> TopicCandidate:
    patch = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    patch["updated_at"] = datetime.now(tz=timezone.utc)
    try:
        return update_topic(topic_id, patch)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{topic_id}/ignore", response_model=TopicCandidate)
async def ignore_topic(
    topic_id: Annotated[str, Path(description="Topic ID")],
) -> TopicCandidate:
    try:
        return update_topic(
            topic_id,
            {
                "status": TopicStatus.ignored,
                "updated_at": datetime.now(tz=timezone.utc),
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{topic_id}/convert-to-task", response_model=TaskResponse, status_code=201)
async def convert_topic_to_task(
    topic_id: Annotated[str, Path(description="Topic ID")],
    body: ConvertTopicToTaskRequest,
) -> TaskResponse:
    topic = get_topic(topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail=f"topic {topic_id!r} not found")
    if topic.status == TopicStatus.converted and topic.task_id:
        existing_task = task_store.get(topic.task_id)
        if existing_task is not None:
            return existing_task

    task = TaskResponse(
        task_id=str(uuid.uuid4()),
        keywords=topic.title,
        original_keywords=topic.title,
        generation_config=body.generation_config,
        status=TaskStatus.pending,
        created_at=datetime.now(tz=timezone.utc),
        hotspot_capture_config=body.hotspot_capture_config,
        selected_topic=topic.model_dump(mode="json"),
    )
    task_store[task.task_id] = task
    save_tasks()
    update_topic(
        topic_id,
        {
            "status": TopicStatus.converted,
            "task_id": task.task_id,
            "updated_at": datetime.now(tz=timezone.utc),
        },
    )
    return task
