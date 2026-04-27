"""Human review queue routes."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query

from api.models import (
    CreateReviewQueueItemRequest,
    ReviewDecisionRequest,
    ReviewQueueItem,
    ReviewStatus,
    ReviewTargetType,
)
from api.store import create_review, get_review, list_reviews, save_tasks, task_store, update_review

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.get("", response_model=list[ReviewQueueItem])
async def get_reviews(
    status: Annotated[ReviewStatus | None, Query(description="Filter by review status")] = None,
) -> list[ReviewQueueItem]:
    return list_reviews(status.value if status else None)


@router.get("/pending", response_model=list[ReviewQueueItem])
async def get_pending_reviews() -> list[ReviewQueueItem]:
    return list_reviews(ReviewStatus.pending.value)


@router.post("", response_model=ReviewQueueItem, status_code=201)
async def add_review(body: CreateReviewQueueItemRequest) -> ReviewQueueItem:
    review = ReviewQueueItem(
        review_id=str(uuid.uuid4()),
        target_type=body.target_type,
        target_id=body.target_id,
        title=body.title,
        payload=body.payload,
        created_at=datetime.now(tz=timezone.utc),
    )
    return create_review(review)


@router.get("/{review_id}", response_model=ReviewQueueItem)
async def get_review_detail(
    review_id: Annotated[str, Path(description="Review ID")],
) -> ReviewQueueItem:
    review = get_review(review_id)
    if review is None:
        raise HTTPException(status_code=404, detail=f"review {review_id!r} not found")
    return review


def _decide_review(
    review_id: str,
    body: ReviewDecisionRequest,
    status: ReviewStatus,
) -> ReviewQueueItem:
    if get_review(review_id) is None:
        raise HTTPException(status_code=404, detail=f"review {review_id!r} not found")
    now = datetime.now(tz=timezone.utc)
    updated = update_review(
        review_id,
        {
            "status": status,
            "decision": status,
            "comment": body.comment,
            "reviewer_id": body.reviewer_id,
            "decided_at": now,
            "updated_at": now,
        },
    )
    if status == ReviewStatus.approved and updated.target_type in {ReviewTargetType.task, ReviewTargetType.article}:
        task = task_store.get(updated.target_id)
        if task is not None:
            task.human_review_required = False
            if task.quality_report:
                task.quality_report["ready_to_publish"] = True
            if task.quality_state:
                task.quality_state["human_review_required"] = False
                task.quality_state["ready_to_publish"] = True
                publish_decision = dict(task.quality_state.get("publish_decision") or {})
                publish_decision["human_review_required"] = False
                publish_decision["ready_to_publish"] = True
                publish_decision["next_step"] = "manual_push"
                task.quality_state["publish_decision"] = publish_decision
            save_tasks()
    return updated


@router.post("/{review_id}/approve", response_model=ReviewQueueItem)
async def approve_review(
    review_id: Annotated[str, Path(description="Review ID")],
    body: ReviewDecisionRequest,
) -> ReviewQueueItem:
    return _decide_review(review_id, body, ReviewStatus.approved)


@router.post("/{review_id}/reject", response_model=ReviewQueueItem)
async def reject_review(
    review_id: Annotated[str, Path(description="Review ID")],
    body: ReviewDecisionRequest,
) -> ReviewQueueItem:
    return _decide_review(review_id, body, ReviewStatus.rejected)


@router.post("/{review_id}/request-revision", response_model=ReviewQueueItem)
async def request_review_revision(
    review_id: Annotated[str, Path(description="Review ID")],
    body: ReviewDecisionRequest,
) -> ReviewQueueItem:
    return _decide_review(review_id, body, ReviewStatus.revision_requested)
