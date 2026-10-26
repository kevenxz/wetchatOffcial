"""Capture and select hotspot topics before article generation."""
from __future__ import annotations

import asyncio
import random
import time
from typing import Any
from urllib.parse import urlsplit

import structlog

from workflow.state import WorkflowState
from workflow.utils.hotspot_providers import discover_hotspot_platforms, fetch_hotspot_platform_items
from workflow.utils.hotspot_ranker import pick_best_hotspot, rank_hotspots

logger = structlog.get_logger(__name__)


def _normalize_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        cleaned = item.strip()
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result


def _normalize_platform(platform: Any) -> dict[str, Any] | None:
    if not isinstance(platform, dict):
        return None
    name = str(platform.get("name") or "").strip()
    path = str(platform.get("path") or platform.get("url") or platform.get("feed_url") or "").strip()
    if not name or not path:
        return None
    source = str(platform.get("source") or platform.get("source_type") or "").strip()
    if not source:
        parsed = urlsplit(path) if path.startswith(("http://", "https://")) else None
        if parsed and parsed.netloc == "tophub.today":
            source = "tophub"
        elif parsed:
            source = "rss_or_feed" if "rss" in path.lower() or "feed" in path.lower() else "ranking_page"
        else:
            source = "tophub"
    return {
        "name": name,
        "path": path,
        "source": source,
        "provider_id": str(platform.get("provider_id") or source).strip(),
        "category": str(platform.get("category") or "").strip(),
        "weight": float(platform.get("weight") or 1.0),
        "enabled": bool(platform.get("enabled", True)),
        "parser_options": dict(platform.get("parser_options") or {}),
    }


def _normalize_hotspot_capture_config(raw_config: Any) -> dict[str, Any]:
    if not isinstance(raw_config, dict):
        return {
            "enabled": False,
            "source": "newsnow",
            "categories": [],
            "platforms": [],
            "filters": {
                "top_n_per_platform": 10,
                "min_selection_score": 60,
                "exclude_keywords": [],
                "prefer_keywords": [],
            },
            "fallback_topics": [],
        }

    filters = raw_config.get("filters") if isinstance(raw_config.get("filters"), dict) else {}
    return {
        "enabled": bool(raw_config.get("enabled", False)),
        "source": str(raw_config.get("source", "newsnow") or "newsnow"),
        "categories": _normalize_list(raw_config.get("categories")),
        "platforms": [
            normalized
            for platform in list(raw_config.get("platforms") or [])
            if (normalized := _normalize_platform(platform))
        ],
        "filters": {
            "top_n_per_platform": int(filters.get("top_n_per_platform") or 10),
            "min_selection_score": float(filters.get("min_selection_score") or 60),
            "exclude_keywords": _normalize_list(filters.get("exclude_keywords")),
            "prefer_keywords": _normalize_list(filters.get("prefer_keywords")),
        },
        "fallback_topics": _normalize_list(raw_config.get("fallback_topics")),
    }


def _pick_fallback_keyword(config: dict[str, Any], original_keywords: str) -> str:
    fallback_topics = _normalize_list(config.get("fallback_topics"))
    if fallback_topics:
        return random.choice(fallback_topics)
    return original_keywords


def _platform_category(platform: dict[str, Any], categories: list[str]) -> str:
    platform_category = str(platform.get("category", "")).strip()
    if platform_category:
        return platform_category
    return categories[0] if categories else ""


def _platform_log_sample(platforms: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    return [
        {
            "name": platform.get("name"),
            "path": platform.get("path"),
            "category": platform.get("category"),
            "weight": platform.get("weight"),
            "enabled": platform.get("enabled"),
        }
        for platform in platforms[:limit]
    ]


async def capture_hot_topics_node(state: WorkflowState) -> dict[str, Any]:
    """Capture hotspots, rank candidates and rewrite workflow keywords."""
    task_id = state["task_id"]
    start_time = time.monotonic()
    original_keywords = str(state.get("original_keywords") or state.get("keywords") or "").strip()
    config = _normalize_hotspot_capture_config(state.get("hotspot_capture_config"))

    logger.info(
        "skill_start",
        task_id=task_id,
        skill="capture_hot_topics",
        status="running",
        enabled=config["enabled"],
        source=config["source"],
    )

    if not config["enabled"]:
        duration_ms = round((time.monotonic() - start_time) * 1000)
        logger.info(
            "skill_done",
            task_id=task_id,
            skill="capture_hot_topics",
            status="done",
            duration_ms=duration_ms,
            reason="disabled",
        )
        return {
            "status": "running",
            "current_skill": "capture_hot_topics",
            "progress": 12,
            "keywords": original_keywords,
            "original_keywords": original_keywords,
            "hotspot_capture_config": config,
            "hotspot_candidates": [],
            "selected_hotspot": None,
            "hotspot_capture_error": None,
        }

    try:
        categories = _normalize_list(config.get("categories"))
        filters = dict(config.get("filters") or {})
        top_n_per_platform = max(1, min(int(filters.get("top_n_per_platform") or 10), 50))
        platforms = [
            platform
            for platform in list(config.get("platforms") or [])
            if isinstance(platform, dict)
            and platform.get("enabled", True)
            and str(platform.get("path", "")).strip()
            and str(platform.get("name", "")).strip()
        ]
        if not platforms:
            platforms = await discover_hotspot_platforms(categories)

        if not platforms:
            fallback_keyword = _pick_fallback_keyword(config, original_keywords)
            duration_ms = round((time.monotonic() - start_time) * 1000)
            logger.warning(
                "capture_hot_topics_no_platforms",
                task_id=task_id,
                duration_ms=duration_ms,
            )
            return {
                "status": "running",
                "current_skill": "capture_hot_topics",
                "progress": 12,
                "keywords": fallback_keyword,
                "original_keywords": original_keywords,
                "hotspot_capture_config": config,
                "hotspot_candidates": [],
                "selected_hotspot": None,
                "hotspot_capture_error": "未找到可用热点平台配置，已回退到 fallback_topics",
            }

        logger.info(
            "capture_hot_topics_platforms_resolved",
            task_id=task_id,
            source=config["source"],
            categories=categories,
            platform_count=len(platforms),
            platforms=_platform_log_sample(platforms),
        )

        # Prefer the scheduled snapshot: it is fetched by the background refresher, so a
        # task no longer waits on (or fails with) the upstream. Only platforms the
        # snapshot does not cover are fetched live, so a partially-covered request cannot
        # silently shrink the candidate pool.
        from api.hotspot_snapshot import (
            candidates_for,
            is_fresh,
            recently_failed_platforms,
            split_covered_platforms,
        )

        candidates: list[dict[str, Any]] = []
        snapshot_used = False
        if is_fresh():
            snapshot_candidates = candidates_for(platforms)
            if snapshot_candidates:
                _, still_live = split_covered_platforms(platforms, snapshot_candidates)
                # A platform that returned nothing during the last refresh has no snapshot
                # coverage, so it would be re-fetched here — repeating a failure the refresher
                # just confirmed, and stalling task creation for seconds. The next scheduled
                # refresh still retries it.
                failed = recently_failed_platforms()
                known_down = [
                    platform
                    for platform in still_live
                    if str(platform.get("provider_id") or platform.get("path") or platform.get("name") or "")
                    in failed
                ]
                platforms_to_fetch = [platform for platform in still_live if platform not in known_down]
                candidates.extend(snapshot_candidates)
                snapshot_used = True
                logger.info(
                    "capture_hot_topics_snapshot_used",
                    task_id=task_id,
                    snapshot_candidates=len(snapshot_candidates),
                    live_platforms=len(platforms_to_fetch),
                    skipped_known_failed=[str(item.get("provider_id") or "") for item in known_down],
                )
            else:
                platforms_to_fetch = platforms
        else:
            platforms_to_fetch = platforms
            logger.info("capture_hot_topics_snapshot_stale_or_missing", task_id=task_id)

        if platforms_to_fetch:
            fetch_results = await asyncio.gather(
                *[
                    fetch_hotspot_platform_items(
                        {**platform, "category": _platform_category(platform, categories)},
                        top_n=top_n_per_platform,
                    )
                    for platform in platforms_to_fetch
                ],
                return_exceptions=True,
            )
            for result in fetch_results:
                if isinstance(result, Exception):
                    logger.warning(
                        "capture_hot_topics_platform_failed",
                        task_id=task_id,
                        error=str(result),
                        exc_info=True,
                    )
                    continue
                candidates.extend(result)

        ranked_candidates = rank_hotspots(
            candidates,
            categories=categories,
            filters=filters,
        )
        selected_hotspot = pick_best_hotspot(ranked_candidates)

        if selected_hotspot:
            next_keywords = str(selected_hotspot.get("title") or original_keywords).strip() or original_keywords
            error_message = None
        else:
            next_keywords = _pick_fallback_keyword(config, original_keywords)
            error_message = "热点抓取成功但没有命中过滤条件，已回退到 fallback_topics"

        duration_ms = round((time.monotonic() - start_time) * 1000)
        logger.info(
            "skill_done",
            task_id=task_id,
            skill="capture_hot_topics",
            status="done",
            duration_ms=duration_ms,
            platform_count=len(platforms),
            snapshot_used=snapshot_used,
            live_platform_count=len(platforms_to_fetch),
            candidate_count=len(candidates),
            ranked_count=len(ranked_candidates),
            selected=selected_hotspot.get("title") if selected_hotspot else None,
        )
        return {
            "status": "running",
            "current_skill": "capture_hot_topics",
            "progress": 12,
            "keywords": next_keywords,
            "original_keywords": original_keywords,
            "hotspot_capture_config": config,
            "hotspot_candidates": ranked_candidates,
            "selected_hotspot": selected_hotspot,
            "hotspot_capture_error": error_message,
        }
    except Exception as exc:  # noqa: BLE001
        fallback_keyword = _pick_fallback_keyword(config, original_keywords)
        duration_ms = round((time.monotonic() - start_time) * 1000)
        logger.warning(
            "capture_hot_topics_failed",
            task_id=task_id,
            duration_ms=duration_ms,
            error=str(exc),
            exc_info=True,
        )
        return {
            "status": "running",
            "current_skill": "capture_hot_topics",
            "progress": 12,
            "keywords": fallback_keyword,
            "original_keywords": original_keywords,
            "hotspot_capture_config": config,
            "hotspot_candidates": [],
            "selected_hotspot": None,
            "hotspot_capture_error": str(exc),
        }
