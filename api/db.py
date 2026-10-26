"""SQLAlchemy 2.0 database layer (synchronous).

Design note: each persisted entity is stored as a typed identity row
(``id`` / ``status`` / ``created_at`` for indexing and queries) plus a JSON
``payload`` column holding the full Pydantic model dump. That keeps a single
source of truth for the rich nested documents while still providing real tables,
real indexes and real queries — which the JSON files could not offer.

The engine is deliberately synchronous: :mod:`api.store` and every router already
use a synchronous API, the data volume on a single-machine deployment is small,
and it avoids an async driver round trip on the write path. The JSON file backend
remains the zero-configuration default; this module is only imported when
``DATABASE_URL`` is configured.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

ENTITY_KINDS = (
    "tasks",
    "topics",
    "reviews",
    "workflow_run_steps",
    "accounts",
    "users",
    "schedules",
    "article_stats",
)


class Base(DeclarativeBase):
    """Declarative base for all storage tables."""


class _EntityRow:
    """Columns shared by every entity row."""

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class TaskRow(Base, _EntityRow):
    __tablename__ = "tasks"

    status: Mapped[str] = mapped_column(String(32), index=True, default="pending")
    keywords: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)


class TopicRow(Base, _EntityRow):
    __tablename__ = "topics"

    status: Mapped[str] = mapped_column(String(32), index=True, default="pending")
    title: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)


class ReviewRow(Base, _EntityRow):
    __tablename__ = "reviews"

    status: Mapped[str] = mapped_column(String(32), index=True, default="pending")
    target_id: Mapped[str] = mapped_column(String(128), index=True, default="")
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)


class WorkflowRunStepRow(Base, _EntityRow):
    __tablename__ = "workflow_run_steps"

    task_id: Mapped[str] = mapped_column(String(128), index=True, default="")
    run_id: Mapped[str] = mapped_column(String(128), index=True, default="")
    step_name: Mapped[str] = mapped_column(String(100), default="")
    status: Mapped[str] = mapped_column(String(32), index=True, default="pending")
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)


class AccountRow(Base, _EntityRow):
    __tablename__ = "accounts"

    name: Mapped[str] = mapped_column(Text, default="")
    platform: Mapped[str] = mapped_column(String(32), index=True, default="wechat_mp")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)


class UserRow(Base, _EntityRow):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, default="")
    role: Mapped[str] = mapped_column(String(32), index=True, default="operator")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)


class ScheduleRow(Base, _EntityRow):
    __tablename__ = "schedules"

    name: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), index=True, default="stopped")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    cron_expression: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True, nullable=True)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)


class ArticleStatRow(Base, _EntityRow):
    __tablename__ = "article_stats"

    task_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, default="")
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True, nullable=True)
    read_num: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)


TABLE_MODELS: Dict[str, Any] = {
    "tasks": TaskRow,
    "topics": TopicRow,
    "reviews": ReviewRow,
    "workflow_run_steps": WorkflowRunStepRow,
    "accounts": AccountRow,
    "users": UserRow,
    "schedules": ScheduleRow,
    "article_stats": ArticleStatRow,
}

_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker[Session]] = None


def database_url() -> str:
    """Return the configured database URL, or an empty string."""
    return (os.getenv("DATABASE_URL") or "").strip()


def database_enabled() -> bool:
    """Whether a database backend is configured."""
    return bool(database_url())


def is_postgres(url: Optional[str] = None) -> bool:
    """Whether the active URL targets PostgreSQL."""
    return (url or database_url()).startswith(("postgresql", "postgres"))


def normalize_url(url: str) -> str:
    """Translate a plain PostgreSQL DSN into a SQLAlchemy URL.

    ``postgresql://`` defaults to psycopg2 in SQLAlchemy 2.0, so the URL is used
    as-is; this helper only exists to document the accepted forms.
    """
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]
    return url


def get_engine() -> Engine:
    """Return the process-wide engine, creating it on first use."""
    global _engine, _session_factory
    url = database_url()
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")

    if _engine is None:
        kwargs: Dict[str, Any] = {"future": True, "pool_pre_ping": True}
        if is_postgres(url):
            # Small single-machine deployment: keep the pool deliberately tiny.
            kwargs.update({"pool_size": 5, "max_overflow": 5})
        else:
            # SQLite (used by tests) needs a shared connection across threads.
            kwargs.update({"connect_args": {"check_same_thread": False}})
        _engine = create_engine(normalize_url(url), **kwargs)
        _session_factory = sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Return the session factory, creating the engine first if needed."""
    get_engine()
    assert _session_factory is not None
    return _session_factory


def init_db() -> None:
    """Create missing tables. Alembic remains the source of truth for migrations."""
    Base.metadata.create_all(get_engine())


def dispose_engine() -> None:
    """Dispose the engine (used on shutdown and in tests)."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


def database_health() -> str:
    """Return ``ok`` / ``disabled`` / ``error:<reason>`` for the health endpoint."""
    if not database_enabled():
        return "disabled"
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:  # noqa: BLE001
        return f"error:{type(exc).__name__}"
