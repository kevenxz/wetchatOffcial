"""Article statistics: overview, trend, top articles and WeChat datacube sync.

Two data sources, in order of preference:

1. **Automatic** — the WeChat ``datacube`` article-total endpoint, available to
   verified accounts. ``POST /api/stats/sync`` pulls the last N days and matches
   results back onto tasks by published title.
2. **Manual** — ``PUT /api/stats/{task_id}`` lets an operator enter the numbers,
   which is the fallback when datacube is unavailable for the account.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
import structlog
from fastapi import APIRouter, HTTPException, Query

from api.models import (
    ArticleStats,
    PlatformType,
    StatsArticlesResponse,
    StatsOverview,
    StatsSyncResponse,
    StatsTopArticle,
    StatsTrendPoint,
    TaskResponse,
    UpdateArticleStatsRequest,
)
from api.store import (
    get_account,
    get_article_stats,
    list_accounts,
    list_article_stats,
    save_article_stats,
    task_store,
    update_article_stats,
    upsert_article_stats,
)
from workflow.utils.wechat_token import get_access_token

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/stats", tags=["stats"])

DATACUBE_ARTICLE_TOTAL_URL = "https://api.weixin.qq.com/datacube/getarticletotal"
MAX_SYNC_DAYS = 30


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _article_title(task: TaskResponse) -> str:
    article = dict(task.final_article or task.generated_article or {})
    return str(article.get("title") or task.keywords or "").strip()


def _published_task_ids() -> set[str]:
    """Tasks with at least one successful publish record."""
    published: set[str] = set()
    for task in task_store.values():
        for record in task.push_records:
            status = (record.draft_info or {}).get("publish_status") or record.publish_status
            if status == "published":
                published.add(task.task_id)
                break
    return published


def _published_at(task: TaskResponse) -> datetime | None:
    """Timestamp of the first successful publish for one task."""
    timestamps = [
        record.pushed_at
        for record in task.push_records
        if (record.draft_info or {}).get("publish_status") == "published" or record.publish_status == "published"
    ]
    return min(timestamps) if timestamps else None


def _overview() -> StatsOverview:
    tasks = list(task_store.values())
    published_ids = _published_task_ids()
    stats = list_article_stats()

    return StatsOverview(
        total_articles=sum(1 for task in tasks if task.generated_article),
        total_published=len(published_ids),
        total_drafts=sum(1 for task in tasks if task.draft_info),
        total_reads=sum(item.read_num for item in stats),
        total_shares=sum(item.share_num for item in stats),
        total_collects=sum(item.collect_num for item in stats),
        total_likes=sum(item.like_num + item.fav_num for item in stats),
    )


@router.get("/overview", response_model=StatsOverview)
async def stats_overview() -> StatsOverview:
    """Aggregate dashboard counters."""
    return _overview()


@router.get("/articles", response_model=StatsArticlesResponse)
async def stats_articles(
    range_days: int = Query(default=7, ge=1, le=90, alias="range"),
) -> StatsArticlesResponse:
    """Publishing trend and the best performing articles."""
    now = _utc_now()
    window_start = now - timedelta(days=range_days)

    # Daily buckets keyed by ISO date so the frontend can chart them directly.
    buckets: dict[str, StatsTrendPoint] = {}
    for offset in range(range_days + 1):
        day = (window_start + timedelta(days=offset)).date().isoformat()
        buckets[day] = StatsTrendPoint(date=day)

    # Publishing counts come from push records; reads come from stats rows.
    for task in task_store.values():
        published_at = _published_at(task)
        if published_at is None or published_at < window_start:
            continue
        key = published_at.date().isoformat()
        if key in buckets:
            buckets[key].published += 1

    stats_rows = list_article_stats()
    for item in stats_rows:
        published_at = item.published_at or item.created_at
        if published_at < window_start:
            continue
        key = published_at.date().isoformat()
        if key in buckets:
            buckets[key].reads += item.read_num

    top_articles: list[StatsTopArticle] = []
    for item in stats_rows:
        task = task_store.get(item.task_id)
        top_articles.append(
            StatsTopArticle(
                task_id=item.task_id,
                title=item.title or (_article_title(task) if task else ""),
                reads=item.read_num,
                shares=item.share_num,
                collects=item.collect_num,
                likes=item.like_num + item.fav_num,
                published_at=item.published_at,
            )
        )
    top_articles.sort(key=lambda item: item.reads, reverse=True)

    return StatsArticlesResponse(
        range_days=range_days,
        trend=[buckets[key] for key in sorted(buckets)],
        top_articles=top_articles[:20],
    )


@router.get("/{task_id}", response_model=ArticleStats)
async def get_stats(task_id: str) -> ArticleStats:
    """One article's metrics."""
    stats = get_article_stats(task_id)
    if stats is None:
        raise HTTPException(status_code=404, detail=f"article stats for {task_id!r} not found")
    return stats


@router.put("/{task_id}", response_model=ArticleStats)
async def put_stats(task_id: str, body: UpdateArticleStatsRequest) -> ArticleStats:
    """Create or update one article's metrics (manual entry fallback)."""
    if task_id not in task_store:
        raise HTTPException(status_code=404, detail=f"task {task_id!r} not found")

    patch = {key: value for key, value in body.model_dump(exclude_unset=True).items() if value is not None}
    patch["source"] = "manual"
    patch["updated_at"] = _utc_now()

    existing = get_article_stats(task_id)
    if existing is None:
        task = task_store[task_id]
        created = ArticleStats(
            task_id=task_id,
            title=str(patch.pop("title", None) or _article_title(task)),
            article_id=str(patch.pop("article_id", None) or (task.draft_info or {}).get("media_id") or ""),
            published_at=patch.pop("published_at", None) or _published_at(task),
            created_at=_utc_now(),
            **patch,
        )
        return upsert_article_stats(created)

    return update_article_stats(task_id, patch)


def _extract_article_metrics(payload: dict[str, Any]) -> dict[str, dict[str, int]]:
    """Normalize a datacube response into ``{title: metrics}``."""
    results: dict[str, dict[str, int]] = {}
    for entry in payload.get("list") or []:
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("title") or "").strip()
        if not title:
            continue
        # WeChat reports cumulative totals under ``details``.
        details = entry.get("details") or []
        read_num = int(entry.get("int_page_read_count") or 0)
        share_num = int(entry.get("share_count") or 0)
        collect_num = int(entry.get("add_to_fav_count") or 0)
        like_num = int(entry.get("like_count") or 0)
        if isinstance(details, list) and details:
            last = details[-1]
            if isinstance(last, dict):
                read_num = int(last.get("int_page_read_count") or read_num)
                share_num = int(last.get("share_count") or share_num)
                collect_num = int(last.get("add_to_fav_count") or collect_num)
                like_num = int(last.get("like_count") or like_num)
        results[title] = {
            "read_num": read_num,
            "share_num": share_num,
            "collect_num": collect_num,
            "like_num": like_num,
        }
    return results


async def _sync_account(account_id: str, days: int) -> tuple[int, int, str]:
    """Pull datacube totals for one account. Returns (synced, failed, message)."""
    account = get_account(account_id)
    if account is None:
        return 0, 0, f"账号 {account_id!r} 不存在"
    if account.platform != PlatformType.wechat_mp:
        return 0, 0, f"账号 {account.name!r} 不是微信公众号"
    if not account.enabled:
        return 0, 0, f"账号 {account.name!r} 已停用"

    now = _utc_now()
    begin = (now - timedelta(days=days)).date().isoformat()
    end = (now - timedelta(days=1)).date().isoformat()

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            token = await get_access_token(account.app_id, account.app_secret, client)
            response = await client.post(
                f"{DATACUBE_ARTICLE_TOTAL_URL}?access_token={token}",
                json={"begin_date": begin, "end_date": end},
            )
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("stats_datacube_failed", account_id=account_id, error=str(exc))
        return 0, 0, f"账号 {account.name!r} 同步失败：{exc}"

    errcode = int(payload.get("errcode", 0) or 0)
    if errcode != 0:
        message = f"账号 {account.name!r} 同步失败：{payload.get('errmsg') or payload}"
        logger.warning("stats_datacube_error", account_id=account_id, payload=payload)
        return 0, 0, message

    metrics_by_title = _extract_article_metrics(payload)
    if not metrics_by_title:
        return 0, 0, f"账号 {account.name!r} 在 {begin} ~ {end} 没有可同步的文章数据"

    # Match datacube rows back to tasks by published title.
    synced = 0
    failed = 0
    for task in task_store.values():
        title = _article_title(task)
        if not title or title not in metrics_by_title:
            continue
        metrics = metrics_by_title[title]
        published_at = _published_at(task)
        existing = get_article_stats(task.task_id)
        try:
            if existing is None:
                upsert_article_stats(
                    ArticleStats(
                        task_id=task.task_id,
                        article_id=str((task.draft_info or {}).get("media_id") or ""),
                        title=title,
                        published_at=published_at,
                        source="datacube",
                        created_at=_utc_now(),
                        updated_at=_utc_now(),
                        **metrics,
                    )
                )
            else:
                update_article_stats(
                    task.task_id,
                    {**metrics, "source": "datacube", "updated_at": _utc_now()},
                )
            synced += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            logger.warning("stats_match_failed", task_id=task.task_id, error=str(exc))

    return synced, failed, f"账号 {account.name!r} 同步完成，匹配 {synced} 篇"


@router.post("/sync", response_model=StatsSyncResponse)
async def sync_stats(
    account_id: Optional[str] = Query(
        default=None,
        description="Sync one account; omit for all enabled WeChat accounts",
    ),
    days: int = Query(default=7, ge=1, le=MAX_SYNC_DAYS),
) -> StatsSyncResponse:
    """Pull WeChat datacube metrics and attach them to matching articles."""
    if account_id:
        candidates = [account_id]
    else:
        candidates = [item.account_id for item in list_accounts() if item.enabled]

    if not candidates:
        return StatsSyncResponse(synced=0, failed=0, message="没有可同步的已启用微信公众号账号")

    total_synced = 0
    total_failed = 0
    messages: list[str] = []
    for candidate in candidates:
        synced, failed, message = await _sync_account(candidate, days)
        total_synced += synced
        total_failed += failed
        messages.append(message)

    save_article_stats()
    return StatsSyncResponse(synced=total_synced, failed=total_failed, message="；".join(messages))
