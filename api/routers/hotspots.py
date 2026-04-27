"""Hotspot preview routes."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter

from api.models import HotspotPreviewRequest, HotspotPreviewResponse, TopicCandidate
from api.store import create_topic, topic_store
from workflow.agents.hotspot import capture_hot_topics_node

router = APIRouter(prefix="/hotspots", tags=["hotspots"])


def _topic_id_from_hotspot(item: dict) -> str:
    raw_key = str(item.get("url") or item.get("title") or uuid.uuid4()).strip()
    return f"hotspot-{uuid.uuid5(uuid.NAMESPACE_URL, raw_key)}"


def _persist_hotspot_topics(items: list[dict]) -> None:
    now = datetime.now(tz=timezone.utc)
    for item in items:
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        topic_id = _topic_id_from_hotspot(item)
        if topic_id in topic_store:
            continue
        score = item.get("selection_score")
        if score is None:
            score = item.get("hot_score") or item.get("hot_value")
        create_topic(
            TopicCandidate(
                topic_id=topic_id,
                title=title,
                summary=str(item.get("extra_text") or item.get("summary") or ""),
                source=str(item.get("source") or item.get("platform_name") or "hotspot"),
                url=item.get("url"),
                score=float(score or 0),
                tags=[str(item.get("category") or "").strip()] if item.get("category") else [],
                metadata=dict(item),
                created_at=now,
            )
        )


@router.post("/preview", response_model=HotspotPreviewResponse)
async def preview_hotspots(body: HotspotPreviewRequest) -> HotspotPreviewResponse:
    """Capture and rank hotspots without creating an article task."""
    original_keywords = body.keywords
    result = await capture_hot_topics_node(
        {
            "task_id": f"preview-{uuid.uuid4()}",
            "keywords": original_keywords,
            "original_keywords": original_keywords,
            "hotspot_capture_config": body.hotspot_capture.model_dump(mode="python"),
        }
    )
    hotspot_candidates = list(result.get("hotspot_candidates") or [])
    _persist_hotspot_topics([item for item in hotspot_candidates if isinstance(item, dict)])
    return HotspotPreviewResponse(
        keywords=str(result.get("keywords") or original_keywords),
        original_keywords=original_keywords,
        hotspot_capture_config=dict(result.get("hotspot_capture_config") or {}),
        hotspot_candidates=hotspot_candidates,
        selected_hotspot=result.get("selected_hotspot"),
        hotspot_capture_error=result.get("hotspot_capture_error"),
    )
