"""Hotspot preview routes."""
from __future__ import annotations

import uuid

from fastapi import APIRouter

from api.models import HotspotPreviewRequest, HotspotPreviewResponse
from workflow.agents.hotspot import capture_hot_topics_node

router = APIRouter(prefix="/hotspots", tags=["hotspots"])


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
    return HotspotPreviewResponse(
        keywords=str(result.get("keywords") or original_keywords),
        original_keywords=original_keywords,
        hotspot_capture_config=dict(result.get("hotspot_capture_config") or {}),
        hotspot_candidates=list(result.get("hotspot_candidates") or []),
        selected_hotspot=result.get("selected_hotspot"),
        hotspot_capture_error=result.get("hotspot_capture_error"),
    )
