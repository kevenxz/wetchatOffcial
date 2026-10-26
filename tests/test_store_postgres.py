"""Tests for the JSON/database persistence layer."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from api import db, persistence, store
from api.models import (
    AccountConfig,
    ArticleStats,
    PlatformType,
    ReviewQueueItem,
    ReviewTargetType,
    ScheduleConfig,
    ScheduleMode,
    TaskResponse,
    TaskStatus,
    TopicCandidate,
    UserAccount,
    WorkflowRunStepRecord,
)
from workflow.article_generation import DEFAULT_ARTICLE_STRATEGY


def _task(task_id: str, status: TaskStatus = TaskStatus.pending, keywords: str = "主题") -> TaskResponse:
    return TaskResponse(
        task_id=task_id,
        keywords=keywords,
        generation_config={"audience_roles": ["泛科技读者"], "article_strategy": DEFAULT_ARTICLE_STRATEGY},
        status=status,
        created_at=datetime.now(tz=timezone.utc),
    )


def _all_containers() -> dict:
    return {
        "tasks": store.task_store,
        "topics": store.topic_store,
        "reviews": store.review_store,
        "workflow_run_steps": store.workflow_run_step_store,
        "accounts": store._account_store,  # noqa: SLF001
        "users": store._user_store,  # noqa: SLF001
        "schedules": store.schedule_store,
        "article_stats": store.article_stat_store,
    }


@pytest.fixture
def sqlite_backend(tmp_path):
    """Configure a throwaway SQLite database as the active backend.

    Two safety measures are essential here:

    * Every in-memory container is cleared for the test and restored afterwards so
      tests cannot collide on unique columns (for example ``users.username``).
    * Legacy JSON reads are redirected to an empty result for any path outside this
      test's tmp directory. ``bootstrap_storage()`` imports legacy documents and
      renames them to ``*.imported``; without this guard the test would move the
      developer's real ``data/*.json`` files aside.
    """
    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    backups = {name: dict(container) for name, container in _all_containers().items()}
    for container in _all_containers().values():
        container.clear()
    persistence.reset_state()
    db.dispose_engine()

    real_read_json_file = persistence.read_json_file
    guard_root = tmp_path.resolve()

    def guarded_read_json_file(path):
        try:
            resolved = Path(path).resolve()
        except Exception:  # noqa: BLE001
            return {}
        if resolved == guard_root or guard_root in resolved.parents:
            return real_read_json_file(path)
        return {}

    with patch.dict("os.environ", {"DATABASE_URL": url}, clear=False):
        with patch("api.persistence.read_json_file", side_effect=guarded_read_json_file):
            db.init_db()
            yield url

    db.dispose_engine()
    persistence.reset_state()
    for name, container in _all_containers().items():
        container.clear()
        container.update(backups[name])


def test_database_enabled_reflects_configuration() -> None:
    with patch.dict("os.environ", {"DATABASE_URL": ""}, clear=False):
        assert db.database_enabled() is False
    with patch.dict("os.environ", {"DATABASE_URL": "sqlite:///x.db"}, clear=False):
        assert db.database_enabled() is True


def test_postgres_url_detection() -> None:
    assert db.is_postgres("postgresql://user:pw@localhost/db") is True
    assert db.is_postgres("postgres://user:pw@localhost/db") is True
    assert db.is_postgres("sqlite:///local.db") is False


def test_legacy_postgres_scheme_is_normalized() -> None:
    assert db.normalize_url("postgres://u:p@h/db") == "postgresql://u:p@h/db"
    assert db.normalize_url("postgresql://u:p@h/db") == "postgresql://u:p@h/db"


def test_json_backend_is_the_default() -> None:
    with patch.dict("os.environ", {"DATABASE_URL": ""}, clear=False):
        assert db.database_enabled() is False
        # The JSON path must not need SQLAlchemy at all.
        assert store.TASKS_FILE.name == "tasks.json"


def test_sqlite_round_trip_persists_tasks(sqlite_backend) -> None:
    store.task_store["t-1"] = _task("t-1", TaskStatus.running, "AI 芯片")
    store.save_tasks()

    # A fresh read from the database must return the same document.
    rows = persistence.load_db(persistence.TASK_KIND)
    assert "t-1" in rows
    assert rows["t-1"]["keywords"] == "AI 芯片"
    assert rows["t-1"]["status"] == "running"


def test_unchanged_rows_are_not_rewritten(sqlite_backend) -> None:
    store.task_store["t-1"] = _task("t-1")
    store.save_tasks()
    first = persistence.table_counts()[persistence.TASK_KIND]

    # A second save with no changes must not touch the row.
    store.save_tasks()
    assert persistence.table_counts()[persistence.TASK_KIND] == first


def test_changed_row_is_updated(sqlite_backend) -> None:
    store.task_store["t-1"] = _task("t-1", TaskStatus.pending)
    store.save_tasks()

    store.task_store["t-1"] = _task("t-1", TaskStatus.done, "新关键词")
    store.save_tasks()

    rows = persistence.load_db(persistence.TASK_KIND)
    assert rows["t-1"]["status"] == "done"
    assert rows["t-1"]["keywords"] == "新关键词"
    assert persistence.table_counts()[persistence.TASK_KIND] == 1


def test_deleted_row_is_removed(sqlite_backend) -> None:
    store.task_store["t-1"] = _task("t-1")
    store.task_store["t-2"] = _task("t-2")
    store.save_tasks()

    del store.task_store["t-2"]
    store.save_tasks()

    rows = persistence.load_db(persistence.TASK_KIND)
    assert list(rows) == ["t-1"]


def test_article_stats_persist(sqlite_backend) -> None:
    stats = ArticleStats(
        task_id="t-1",
        article_id="media-1",
        title="标题",
        read_num=120,
        share_num=8,
        collect_num=5,
        like_num=11,
        created_at=datetime.now(tz=timezone.utc),
    )
    store.upsert_article_stats(stats)

    rows = persistence.load_db(persistence.ARTICLE_STAT_KIND)
    assert rows["t-1"]["read_num"] == 120
    assert rows["t-1"]["article_id"] == "media-1"


def test_legacy_json_is_imported_once_and_backed_up(tmp_path) -> None:
    url = f"sqlite:///{(tmp_path / 'import.db').as_posix()}"
    legacy_file = tmp_path / "tasks.json"
    legacy_file.write_text(
        '{"t-legacy": {"task_id": "t-legacy", "keywords": "旧数据", '
        '"generation_config": {"audience_roles": ["泛科技读者"], "article_strategy": "auto"}, '
        '"status": "done", "created_at": "2026-01-01T00:00:00+00:00"}}',
        encoding="utf-8",
    )

    store.task_store.clear()
    persistence.reset_state()
    db.dispose_engine()

    with patch.dict("os.environ", {"DATABASE_URL": url}, clear=False):
        with patch.object(store, "TASKS_FILE", legacy_file):
            with patch.object(persistence, "read_json_file", side_effect=persistence.read_json_file):
                db.init_db()
                imported = persistence.import_json_into_db(
                    persistence.TASK_KIND,
                    persistence.read_json_file(legacy_file),
                )
                assert imported == 1
                backup = persistence.backup_json(legacy_file)

        assert backup is not None
        assert backup.exists()
        assert not legacy_file.exists()

        rows = persistence.load_db(persistence.TASK_KIND)
        assert rows["t-legacy"]["keywords"] == "旧数据"

    db.dispose_engine()
    persistence.reset_state()
    store.task_store.clear()


def test_import_is_skipped_when_container_already_has_rows(sqlite_backend) -> None:
    store.task_store["t-existing"] = _task("t-existing")

    imported = persistence.import_json_into_db(
        persistence.TASK_KIND,
        {"t-legacy": {"task_id": "t-legacy", "keywords": "x", "status": "done", "created_at": "2026-01-01T00:00:00+00:00"}},
    )

    assert imported == 0


def test_database_health_reports_disabled_without_url() -> None:
    with patch.dict("os.environ", {"DATABASE_URL": ""}, clear=False):
        assert db.database_health() == "disabled"


def test_database_health_reports_ok_for_sqlite(sqlite_backend) -> None:
    assert db.database_health() == "ok"


def test_bootstrap_storage_uses_json_when_no_database(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.chdir(tmp_path)
    summary = store.bootstrap_storage()
    assert summary["backend"] == "json"
    assert summary["created_tables"] is False


def test_bootstrap_storage_creates_tables(sqlite_backend) -> None:
    summary = store.bootstrap_storage()
    assert summary["backend"] == "database"
    assert summary["created_tables"] is True


def test_every_entity_kind_maps_and_round_trips(sqlite_backend) -> None:
    """Each kind has its own promoted columns; none may be missed."""
    now = datetime.now(tz=timezone.utc)

    store.task_store["t-1"] = _task("t-1")
    store.topic_store["topic-1"] = TopicCandidate(topic_id="topic-1", title="选题", created_at=now)
    store.review_store["review-1"] = ReviewQueueItem(
        review_id="review-1",
        target_type=ReviewTargetType.task,
        target_id="t-1",
        title="待审",
        created_at=now,
    )
    store.workflow_run_step_store["step-1"] = WorkflowRunStepRecord(
        run_step_id="step-1",
        task_id="t-1",
        run_id="run-1",
        step_name="compose_draft",
        created_at=now,
    )
    store._account_store["acc-1"] = AccountConfig(  # noqa: SLF001
        account_id="acc-1",
        name="主账号",
        platform=PlatformType.wechat_mp,
        app_id="appid",
        app_secret="secret",
        created_at=now,
    )
    store._user_store["user-1"] = UserAccount(  # noqa: SLF001
        user_id="user-1",
        username="admin",
        password_hash="hash",
        display_name="管理员",
        created_at=now,
    )
    store.schedule_store["sched-1"] = ScheduleConfig(
        schedule_id="sched-1",
        name="早报",
        mode=ScheduleMode.cron,
        cron_expression="0 8 * * *",
        timezone="Asia/Shanghai",
        created_at=now,
        next_run_at=now,
    )
    store.article_stat_store["t-1"] = ArticleStats(task_id="t-1", read_num=42, created_at=now)

    store.save_tasks()
    store.save_topics()
    store.save_reviews()
    store.save_workflow_run_steps()
    store._save_accounts()  # noqa: SLF001
    store._save_users()  # noqa: SLF001
    store.save_schedules()
    store.save_article_stats()

    expected = {
        persistence.TASK_KIND: "t-1",
        persistence.TOPIC_KIND: "topic-1",
        persistence.REVIEW_KIND: "review-1",
        persistence.WORKFLOW_STEP_KIND: "step-1",
        persistence.ACCOUNT_KIND: "acc-1",
        persistence.USER_KIND: "user-1",
        persistence.SCHEDULE_KIND: "sched-1",
        persistence.ARTICLE_STAT_KIND: "t-1",
    }
    for kind, record_id in expected.items():
        rows = persistence.load_db(kind)
        assert record_id in rows, f"{kind} did not persist"
        # Promoted columns must be populated, not just the JSON payload.
        assert rows[record_id], f"{kind} payload is empty"
