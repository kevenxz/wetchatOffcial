"""Tests for the statistics API, health endpoint and alerting."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api import alerts
from api.main import health
from api.models import (
    ArticleStats,
    PlatformType,
    PushRecord,
    PushStatus,
    TaskResponse,
    TaskStatus,
    UpdateArticleStatsRequest,
)
from api.routers.stats import get_stats, put_stats, stats_articles, stats_overview
from api.store import article_stat_store, task_store

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)


def _task(task_id: str, *, published: bool = False, days_ago: int = 0) -> TaskResponse:
    pushed_at = NOW - timedelta(days=days_ago)
    records = []
    if published:
        records.append(
            PushRecord(
                push_id=f"push-{task_id}",
                account_id="acc-1",
                account_name="主账号",
                platform=PlatformType.wechat_mp,
                pushed_at=pushed_at,
                status=PushStatus.success,
                draft_info={"media_id": f"media-{task_id}", "publish_status": "published"},
                publish_status="published",
            )
        )
    return TaskResponse(
        task_id=task_id,
        keywords=f"主题 {task_id}",
        generation_config={},
        status=TaskStatus.done,
        created_at=pushed_at,
        generated_article={"title": f"标题 {task_id}", "content": "正文"},
        final_article={"title": f"标题 {task_id}", "content": "正文"},
        draft_info={"media_id": f"media-{task_id}"},
        push_records=records,
    )


@pytest.fixture(autouse=True)
def _clean_stores():
    task_backup = dict(task_store)
    stats_backup = dict(article_stat_store)
    task_store.clear()
    article_stat_store.clear()
    alerts.reset_state()
    yield
    task_store.clear()
    task_store.update(task_backup)
    article_stat_store.clear()
    article_stat_store.update(stats_backup)
    alerts.reset_state()


@pytest.mark.asyncio
async def test_overview_aggregates_articles_publishes_and_metrics() -> None:
    task_store["t-1"] = _task("t-1", published=True)
    task_store["t-2"] = _task("t-2")
    article_stat_store["t-1"] = ArticleStats(
        task_id="t-1",
        title="标题 t-1",
        read_num=500,
        share_num=20,
        collect_num=10,
        like_num=30,
        fav_num=5,
        created_at=NOW,
    )

    overview = await stats_overview()

    assert overview.total_articles == 2
    assert overview.total_published == 1
    assert overview.total_drafts == 2
    assert overview.total_reads == 500
    assert overview.total_shares == 20
    assert overview.total_collects == 10
    assert overview.total_likes == 35


@pytest.mark.asyncio
async def test_trend_buckets_publishes_and_reads_by_day() -> None:
    task_store["t-1"] = _task("t-1", published=True, days_ago=1)
    article_stat_store["t-1"] = ArticleStats(
        task_id="t-1",
        title="标题 t-1",
        read_num=120,
        published_at=NOW - timedelta(days=1),
        created_at=NOW - timedelta(days=1),
    )

    with patch("api.routers.stats._utc_now", return_value=NOW):
        response = await stats_articles(range_days=7)

    assert response.range_days == 7
    assert len(response.trend) == 8
    published_days = {point.date: point.published for point in response.trend}
    read_days = {point.date: point.reads for point in response.trend}
    target = (NOW - timedelta(days=1)).date().isoformat()
    assert published_days[target] == 1
    assert read_days[target] == 120


@pytest.mark.asyncio
async def test_top_articles_are_sorted_by_reads() -> None:
    for index, reads in enumerate([10, 900, 300], start=1):
        task = _task(f"t-{index}", published=True)
        task_store[task.task_id] = task
        article_stat_store[task.task_id] = ArticleStats(
            task_id=task.task_id,
            title=f"标题 {index}",
            read_num=reads,
            created_at=NOW,
        )

    with patch("api.routers.stats._utc_now", return_value=NOW):
        response = await stats_articles(range_days=30)

    assert [item.reads for item in response.top_articles] == [900, 300, 10]


@pytest.mark.asyncio
async def test_manual_stats_entry_creates_a_row() -> None:
    task_store["t-1"] = _task("t-1", published=True)

    stats = await put_stats("t-1", UpdateArticleStatsRequest(read_num=321, share_num=7))

    assert stats.task_id == "t-1"
    assert stats.read_num == 321
    assert stats.source == "manual"
    assert stats.title == "标题 t-1"
    assert stats.article_id == "media-t-1"


@pytest.mark.asyncio
async def test_manual_stats_entry_updates_an_existing_row() -> None:
    task_store["t-1"] = _task("t-1", published=True)
    article_stat_store["t-1"] = ArticleStats(task_id="t-1", read_num=100, created_at=NOW)

    stats = await put_stats("t-1", UpdateArticleStatsRequest(read_num=250))

    assert stats.read_num == 250
    assert stats.source == "manual"


@pytest.mark.asyncio
async def test_manual_stats_entry_rejects_unknown_task() -> None:
    with pytest.raises(HTTPException) as excinfo:
        await put_stats("missing", UpdateArticleStatsRequest(read_num=1))
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_get_stats_returns_404_when_absent() -> None:
    task_store["t-1"] = _task("t-1")
    with pytest.raises(HTTPException) as excinfo:
        await get_stats("t-1")
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_health_reports_storage_cache_and_scheduler() -> None:
    with patch("api.main.get_redis", new_callable=AsyncMock, return_value=None):
        with patch("api.main.database_health", return_value="disabled"):
            with patch("api.main.scheduler_engine") as mock_engine:
                mock_engine.status.return_value = "running"
                response = await health()

    assert response.status == "ok"
    assert response.database == "disabled"
    assert response.redis == "disabled"
    assert response.scheduler == "running"
    assert response.version


@pytest.mark.asyncio
async def test_health_degrades_when_the_database_errors() -> None:
    with patch("api.main.get_redis", new_callable=AsyncMock, return_value=None):
        with patch("api.main.database_health", return_value="error:OperationalError"):
            response = await health()

    assert response.status == "degraded"


@pytest.mark.asyncio
async def test_alert_is_a_noop_without_a_webhook() -> None:
    with patch.dict("os.environ", {"ALERT_WEBHOOK": ""}, clear=False):
        assert await alerts.send_alert(task_id="t-1", error="boom") is False


@pytest.mark.asyncio
async def test_alert_is_sent_when_a_webhook_is_configured() -> None:
    with patch.dict("os.environ", {"ALERT_WEBHOOK": "https://example.com/hook"}, clear=False):
        with patch("api.alerts.httpx.AsyncClient") as mock_client_cls:
            client = mock_client_cls.return_value.__aenter__.return_value
            client.post = AsyncMock()
            sent = await alerts.send_alert(task_id="t-1", skill="compose_draft", error="boom")

    assert sent is True
    payload = client.post.await_args.kwargs["json"]
    assert payload["msgtype"] == "text"
    assert "t-1" in payload["text"]["content"]


@pytest.mark.asyncio
async def test_alert_failure_never_raises() -> None:
    with patch.dict("os.environ", {"ALERT_WEBHOOK": "https://example.com/hook"}, clear=False):
        with patch("api.alerts.httpx.AsyncClient") as mock_client_cls:
            client = mock_client_cls.return_value.__aenter__.return_value
            client.post = AsyncMock(side_effect=RuntimeError("webhook down"))
            sent = await alerts.send_alert(task_id="t-1", error="boom")

    assert sent is False


@pytest.mark.asyncio
async def test_alert_budget_suppresses_a_storm() -> None:
    with patch.dict("os.environ", {"ALERT_WEBHOOK": "https://example.com/hook"}, clear=False):
        with patch("api.alerts.httpx.AsyncClient") as mock_client_cls:
            client = mock_client_cls.return_value.__aenter__.return_value
            client.post = AsyncMock()
            client.post.return_value.raise_for_status = MagicMock()
            results = [await alerts.send_alert(task_id="t-storm", error="boom") for _ in range(6)]

    # Three delivered, the rest suppressed.
    assert results == [True, True, True, False, False, False]
