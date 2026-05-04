"""Hotspot preview routes."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Query

from api.models import (
    HotspotMonitorCaptureRequest,
    HotspotMonitorItem,
    HotspotMonitorResponse,
    HotspotMonitorStats,
    HotspotPreviewRequest,
    HotspotPreviewResponse,
    TopicCandidate,
    TopicStatus,
)
from api.store import create_topic, list_topics, topic_store, update_topic
from workflow.agents.hotspot import capture_hot_topics_node

router = APIRouter(prefix="/hotspots", tags=["hotspots"])
logger = structlog.get_logger(__name__)


def _topic_id_from_hotspot(item: dict) -> str:
    raw_key = str(item.get("url") or item.get("title") or uuid.uuid4()).strip()
    return f"hotspot-{uuid.uuid5(uuid.NAMESPACE_URL, raw_key)}"


def _bounded_score(value: object, fallback: float = 0) -> int:
    try:
        score = float(value if value is not None else fallback)
    except (TypeError, ValueError):
        score = fallback
    return max(0, min(100, round(score)))


def _first_text(*values: object, fallback: str = "") -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback


def _item_score(item: dict) -> float:
    score = item.get("selection_score")
    if score is None:
        score = item.get("hot_score") or item.get("hot_value")
    try:
        return float(score or 0)
    except (TypeError, ValueError):
        return 0


def _hotspot_log_sample(items: list[dict], limit: int = 5) -> list[dict]:
    sample = []
    for item in items[:limit]:
        sample.append(
            {
                "title": item.get("title"),
                "source": item.get("source") or item.get("platform_name"),
                "category": item.get("category"),
                "score": _item_score(item),
                "risk_score": item.get("risk_score") or item.get("risk"),
                "url": item.get("url"),
            }
        )
    return sample


def _monitor_item_log_sample(items: list[HotspotMonitorItem], limit: int = 5) -> list[dict]:
    return [
        {
            "topic_id": item.topic_id,
            "title": item.title,
            "source": item.source,
            "category": item.category,
            "hot_score": item.hot_score,
            "account_fit_score": item.account_fit_score,
            "risk_score": item.risk_score,
            "recommended": item.recommended,
        }
        for item in items[:limit]
    ]


def _persist_hotspot_topics(items: list[dict]) -> dict[str, int]:
    now = datetime.now(tz=timezone.utc)
    stats = {"received": len(items), "created": 0, "updated": 0, "skipped": 0}
    for item in items:
        title = str(item.get("title") or "").strip()
        if not title:
            stats["skipped"] += 1
            continue
        topic_id = _topic_id_from_hotspot(item)
        score = _item_score(item)
        category = str(item.get("category") or "").strip()
        patch = {
            "summary": str(item.get("extra_text") or item.get("summary") or ""),
            "source": str(item.get("source") or item.get("platform_name") or "hotspot"),
            "url": item.get("url"),
            "score": score,
            "tags": [category] if category else [],
            "metadata": dict(item),
            "updated_at": now,
        }
        if topic_id in topic_store:
            try:
                update_topic(topic_id, patch)
                stats["updated"] += 1
            except ValueError:
                stats["skipped"] += 1
            continue
        create_topic(
            TopicCandidate(
                topic_id=topic_id,
                title=title,
                summary=patch["summary"],
                source=patch["source"],
                url=patch["url"],
                score=score,
                tags=patch["tags"],
                metadata=patch["metadata"],
                created_at=now,
            )
        )
        stats["created"] += 1
    return stats


def _monitor_item_from_topic(topic: TopicCandidate) -> HotspotMonitorItem:
    metadata = dict(topic.metadata or {})
    category = _first_text(
        metadata.get("category"),
        topic.tags[0] if topic.tags else "",
        fallback="科技",
    )
    hot_score = _bounded_score(topic.score or metadata.get("hot_score") or metadata.get("hot_value") or metadata.get("selection_score"))
    account_fit_score = _bounded_score(metadata.get("account_fit_score") or metadata.get("fit_score") or metadata.get("selection_score") or topic.score)
    risk_score = _bounded_score(metadata.get("risk_score") or metadata.get("risk") or 0)
    channel_count = max(
        1,
        int(
            metadata.get("channel_count")
            or metadata.get("channelCount")
            or len(metadata.get("source_cluster") or [])
            or 1
        ),
    )
    tags = []
    for item in [*topic.tags, category, *(metadata.get("tags") or []), *(metadata.get("keywords") or [])]:
        cleaned = str(item).strip()
        if cleaned and cleaned not in tags:
            tags.append(cleaned)

    recommended = topic.status == TopicStatus.pending and account_fit_score >= 70 and risk_score < 40
    return HotspotMonitorItem(
        topic_id=topic.topic_id,
        title=topic.title,
        summary=topic.summary,
        source=_first_text(topic.source, metadata.get("platform_name"), metadata.get("source"), fallback="热点源"),
        url=topic.url,
        category=category,
        tags=tags[:8],
        status=topic.status,
        task_id=topic.task_id,
        hot_score=hot_score,
        account_fit_score=account_fit_score,
        risk_score=risk_score,
        channel_count=channel_count,
        recommended=recommended,
        captured_at=topic.created_at,
        updated_at=topic.updated_at,
        metadata=metadata,
    )


def _build_monitor_response(
    *,
    status: TopicStatus | None = TopicStatus.pending,
    category: str | None = None,
    recommended_only: bool = False,
    limit: int = 80,
    capture_error: str | None = None,
) -> HotspotMonitorResponse:
    topics = list_topics(status.value if status else None)
    items = [_monitor_item_from_topic(topic) for topic in topics]
    if category and category != "all":
        items = [item for item in items if item.category == category or category in item.tags]
    if recommended_only:
        items = [item for item in items if item.recommended]
    items = sorted(items, key=lambda item: (item.hot_score, item.captured_at or datetime.min.replace(tzinfo=timezone.utc)), reverse=True)[:limit]
    latest = max((item.updated_at or item.captured_at for item in items if item.updated_at or item.captured_at), default=None)
    stats = HotspotMonitorStats(
        total=len(items),
        recommended=sum(1 for item in items if item.recommended),
        high_risk=sum(1 for item in items if item.risk_score >= 70),
        source_count=len({item.source for item in items if item.source}),
        latest_captured_at=latest,
    )
    return HotspotMonitorResponse(
        items=items,
        stats=stats,
        updated_at=datetime.now(tz=timezone.utc),
        capture_error=capture_error,
    )


@router.get("/monitor", response_model=HotspotMonitorResponse)
async def get_hotspot_monitor(
    status: TopicStatus | None = Query(default=TopicStatus.pending),
    category: str | None = Query(default=None),
    recommended_only: bool = Query(default=False),
    limit: int = Query(default=80, ge=1, le=200),
) -> HotspotMonitorResponse:
    """Return normalized hotspot monitor data for the dashboard page."""
    response = _build_monitor_response(
        status=status,
        category=category,
        recommended_only=recommended_only,
        limit=limit,
    )
    logger.info(
        "hotspot_monitor_list",
        status=status.value if status else "all",
        category=category,
        recommended_only=recommended_only,
        limit=limit,
        returned=len(response.items),
        stats=response.stats.model_dump(mode="json"),
        sample=_monitor_item_log_sample(response.items),
    )
    return response


@router.post("/monitor/capture", response_model=HotspotMonitorResponse)
async def capture_hotspot_monitor(body: HotspotMonitorCaptureRequest) -> HotspotMonitorResponse:
    """Capture fresh hotspots, persist them and return monitor data."""
    original_keywords = body.keywords
    capture_config = body.hotspot_capture.model_dump(mode="python")
    logger.info(
        "hotspot_monitor_capture_start",
        keywords=original_keywords,
        source=capture_config.get("source"),
        categories=capture_config.get("categories"),
        platform_count=len(capture_config.get("platforms") or []),
        filters=capture_config.get("filters"),
    )
    result = await capture_hot_topics_node(
        {
            "task_id": f"monitor-{uuid.uuid4()}",
            "keywords": original_keywords,
            "original_keywords": original_keywords,
            "hotspot_capture_config": capture_config,
        }
    )
    hotspot_candidates = list(result.get("hotspot_candidates") or [])
    candidate_dicts = [item for item in hotspot_candidates if isinstance(item, dict)]
    persist_stats = _persist_hotspot_topics(candidate_dicts)
    response = _build_monitor_response(
        status=TopicStatus.pending,
        limit=80,
        capture_error=result.get("hotspot_capture_error"),
    )
    logger.info(
        "hotspot_monitor_capture_done",
        keywords=str(result.get("keywords") or original_keywords),
        candidate_count=len(candidate_dicts),
        persist_stats=persist_stats,
        returned=len(response.items),
        stats=response.stats.model_dump(mode="json"),
        selected_hotspot=result.get("selected_hotspot"),
        capture_error=result.get("hotspot_capture_error"),
        raw_sample=_hotspot_log_sample(candidate_dicts),
        display_sample=_monitor_item_log_sample(response.items),
    )
    return response


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
    candidate_dicts = [item for item in hotspot_candidates if isinstance(item, dict)]
    persist_stats = _persist_hotspot_topics(candidate_dicts)
    logger.info(
        "hotspot_preview_capture_done",
        keywords=str(result.get("keywords") or original_keywords),
        candidate_count=len(candidate_dicts),
        persist_stats=persist_stats,
        selected_hotspot=result.get("selected_hotspot"),
        capture_error=result.get("hotspot_capture_error"),
        raw_sample=_hotspot_log_sample(candidate_dicts),
    )
    return HotspotPreviewResponse(
        keywords=str(result.get("keywords") or original_keywords),
        original_keywords=original_keywords,
        hotspot_capture_config=dict(result.get("hotspot_capture_config") or {}),
        hotspot_candidates=hotspot_candidates,
        selected_hotspot=result.get("selected_hotspot"),
        hotspot_capture_error=result.get("hotspot_capture_error"),
    )
