"""Persistence backends for the in-memory stores.

Two backends, selected by configuration:

* **JSON files** (default, zero configuration) — the historical behaviour.
* **PostgreSQL / SQLite** via SQLAlchemy when ``DATABASE_URL`` is set.

The in-memory dicts in :mod:`api.store` stay the read path and the running
process's source of truth, so every router keeps its existing synchronous API.
With a database configured, :func:`persist_kind` diffs the current records against
the last persisted snapshot and only writes rows that actually changed — a task
progress event therefore touches one row rather than the whole table.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)

TASK_KIND = "tasks"
TOPIC_KIND = "topics"
REVIEW_KIND = "reviews"
WORKFLOW_STEP_KIND = "workflow_run_steps"
ACCOUNT_KIND = "accounts"
USER_KIND = "users"
SCHEDULE_KIND = "schedules"
ARTICLE_STAT_KIND = "article_stats"

ALL_KINDS = (
    TASK_KIND,
    TOPIC_KIND,
    REVIEW_KIND,
    WORKFLOW_STEP_KIND,
    ACCOUNT_KIND,
    USER_KIND,
    SCHEDULE_KIND,
    ARTICLE_STAT_KIND,
)

# Last successfully persisted payload per kind/id; used to skip unchanged rows.
_last_flushed: Dict[str, Dict[str, str]] = {}


class TableMissingError(RuntimeError):
    """Raised when the database is configured but the tables are absent."""


def reset_state() -> None:
    """Forget the flush snapshot (used by tests)."""
    _last_flushed.clear()


def _db_enabled() -> bool:
    from api.db import database_enabled

    return database_enabled()


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _serialize(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=_json_default)


def _coerce_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _row_columns(kind: str, record_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the promoted (indexable) columns for one entity row."""
    created = _coerce_datetime(payload.get("created_at")) or datetime.now(tz=timezone.utc)
    base = {
        "id": record_id,
        "created_at": created,
        "updated_at": _coerce_datetime(payload.get("updated_at")),
        "payload": payload,
    }

    if kind == TASK_KIND:
        return {
            **base,
            "status": str(payload.get("status") or "pending"),
            "keywords": str(payload.get("keywords") or ""),
        }
    if kind == TOPIC_KIND:
        return {
            **base,
            "status": str(payload.get("status") or "pending"),
            "title": str(payload.get("title") or ""),
        }
    if kind == REVIEW_KIND:
        return {
            **base,
            "status": str(payload.get("status") or "pending"),
            "target_id": str(payload.get("target_id") or ""),
        }
    if kind == WORKFLOW_STEP_KIND:
        return {
            **base,
            "task_id": str(payload.get("task_id") or ""),
            "run_id": str(payload.get("run_id") or ""),
            "step_name": str(payload.get("step_name") or ""),
            "status": str(payload.get("status") or "pending"),
        }
    if kind == ACCOUNT_KIND:
        return {
            **base,
            "name": str(payload.get("name") or ""),
            "platform": str(payload.get("platform") or "wechat_mp"),
            "enabled": bool(payload.get("enabled", True)),
        }
    if kind == USER_KIND:
        return {
            **base,
            "username": str(payload.get("username") or ""),
            "role": str(payload.get("role") or "operator"),
            "enabled": bool(payload.get("enabled", True)),
        }
    if kind == SCHEDULE_KIND:
        return {
            **base,
            "name": str(payload.get("name") or ""),
            "status": str(payload.get("status") or "stopped"),
            "enabled": bool(payload.get("enabled", True)),
            "cron_expression": payload.get("cron_expression") or None,
            "next_run_at": _coerce_datetime(payload.get("next_run_at")),
        }
    if kind == ARTICLE_STAT_KIND:
        return {
            **base,
            "task_id": str(payload.get("task_id") or ""),
            "published_at": _coerce_datetime(payload.get("published_at")),
            "read_num": int(payload.get("read_num") or 0),
        }
    raise ValueError(f"unknown entity kind {kind!r}")


# --------------------------------------------------------------------------- #
# JSON backend
# --------------------------------------------------------------------------- #


# Retry schedule for the atomic rename. On Windows `Path.replace` maps to MoveFileEx,
# which fails with "Access is denied" whenever another handle (an antivirus scanner, a
# concurrent writer, an open reader) holds the destination open. That is transient, so a
# short backoff is far better than giving up and losing the write.
_REPLACE_RETRY_DELAYS = (0.05, 0.15, 0.4)

# One lock per destination path. Retrying is only the *second* line of defence: two writers
# inside this process should never contend at all, and under six concurrent writers an
# aggressive stress test exhausted the retries and lost the write. Serializing per path
# removes that entire failure mode for in-process writers, leaving the retry to handle only
# external handles (scanners, readers, other processes).
_PATH_LOCKS: dict[str, threading.Lock] = {}
_PATH_LOCKS_GUARD = threading.Lock()


def _path_lock(path: Path) -> threading.Lock:
    """Return the lock guarding writes to ``path``, creating it on first use."""
    key = str(path)
    with _PATH_LOCKS_GUARD:
        lock = _PATH_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _PATH_LOCKS[key] = lock
        return lock


def write_json_file(path: Path, payload: Dict[str, Any]) -> None:
    """Atomically write one JSON document.

    Two details matter here:

    * **The temporary file name is unique per writer.** It used to be
      ``path.with_suffix(".tmp")``, i.e. ``data/workflow_run_steps.tmp`` for *every*
      concurrent writer. Two overlapping writes therefore shared one scratch file, and one
      would rename a file the other was still writing.
    * **The rename is retried.** ``Path.replace`` is not atomic-with-retry on Windows; a
      transient sharing violation used to surface as ``[WinError 5]`` and be swallowed as a
      warning (27 occurrences in one audit window), silently dropping the write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = path.parent / f"{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp"
    try:
        with _path_lock(path):
            with open(temp_file, "w", encoding="utf-8") as file:
                json.dump(payload, file, ensure_ascii=False, indent=2, default=_json_default)
                file.flush()
                # Flush to disk before the rename, so the rename cannot publish a file
                # whose contents are still buffered in the OS.
                os.fsync(file.fileno())
            _replace_with_retry(temp_file, path)
    except Exception:
        # Never leave scratch files behind — they accumulate and confuse the next reader.
        try:
            temp_file.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _replace_with_retry(temp_file: Path, path: Path) -> None:
    """Rename ``temp_file`` over ``path``, retrying transient Windows sharing violations."""
    last_error: OSError | None = None
    for attempt, delay in enumerate((0.0, *_REPLACE_RETRY_DELAYS)):
        if delay:
            time.sleep(delay)
        try:
            temp_file.replace(path)
            return
        except OSError as exc:  # includes PermissionError on Windows
            last_error = exc
            logger.debug(
                "json_write_replace_retry",
                path=str(path),
                attempt=attempt + 1,
                error=str(exc),
            )
    assert last_error is not None  # the loop always runs at least once
    logger.error(
        "json_write_replace_failed",
        path=str(path),
        attempts=len(_REPLACE_RETRY_DELAYS) + 1,
        error=str(last_error),
        exc_info=last_error,
    )
    raise last_error


def read_json_file(path: Path) -> Dict[str, Any]:
    """Read one JSON document, returning an empty dict when absent or invalid.

    ``utf-8-sig`` is used so a file saved with a BOM (common when hand-edited on
    Windows) still loads instead of being silently discarded.
    """
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8-sig") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("json_read_failed", path=str(path), error=str(exc))
        return {}


def persist_json(path: Path, records: Dict[str, Dict[str, Any]]) -> None:
    """Persist all records of one kind to a JSON file."""
    write_json_file(path, records)


# --------------------------------------------------------------------------- #
# Database backend
# --------------------------------------------------------------------------- #


def _iter_rows(kind: str) -> Dict[str, Dict[str, Any]]:
    """Return the current in-memory records for one kind as JSON-safe dicts."""
    from api import store

    container = store.container_for_kind(kind)
    return {record_id: record.model_dump(mode="json") for record_id, record in container.items()}


def persist_db(kind: str) -> int:
    """Upsert changed rows and delete removed ones for one kind.

    Returns the number of affected rows.
    """
    from api.db import TABLE_MODELS, get_session_factory

    model = TABLE_MODELS[kind]
    records = _iter_rows(kind)
    previous = _last_flushed.setdefault(kind, {})
    current: Dict[str, str] = {}
    affected = 0

    session_factory = get_session_factory()
    with session_factory() as session:
        for record_id, payload in records.items():
            serialized = _serialize(payload)
            current[record_id] = serialized
            if previous.get(record_id) == serialized:
                continue
            columns = _row_columns(kind, record_id, payload)
            existing = session.get(model, record_id)
            if existing is None:
                session.add(model(**columns))
            else:
                for key, value in columns.items():
                    setattr(existing, key, value)
            affected += 1

        removed = [record_id for record_id in previous if record_id not in current]
        for record_id in removed:
            existing = session.get(model, record_id)
            if existing is not None:
                session.delete(existing)
                affected += 1

        if affected:
            session.commit()

    _last_flushed[kind] = current
    if affected:
        # DEBUG on purpose: this fires on nearly every progress callback (750 lines in one
        # audit window, almost all `affected=1`) and carries no diagnostic value at INFO.
        # Persistence failures are what matter, and those log at WARNING/ERROR.
        logger.debug("persistence_flushed", kind=kind, affected=affected)
    return affected


def load_db(kind: str) -> Dict[str, Dict[str, Any]]:
    """Load every row of one kind from the database."""
    from api.db import TABLE_MODELS, get_session_factory

    model = TABLE_MODELS[kind]
    session_factory = get_session_factory()
    with session_factory() as session:
        rows = session.query(model).all()
    return {row.id: dict(row.payload or {}) for row in rows}


def table_counts() -> Dict[str, int]:
    """Row counts per entity kind (health endpoint and diagnostics)."""
    from api.db import TABLE_MODELS, get_session_factory

    counts: Dict[str, int] = {}
    session_factory = get_session_factory()
    with session_factory() as session:
        for kind, model in TABLE_MODELS.items():
            counts[kind] = int(session.query(model).count())
    return counts


# --------------------------------------------------------------------------- #
# Unified entry point
# --------------------------------------------------------------------------- #


def persist(
    kind: str,
    records: Dict[str, Dict[str, Any]],
    *,
    json_path: Optional[Path] = None,
) -> None:
    """Persist one entity kind through the configured backend.

    With a database configured the write goes to the database; otherwise it goes
    to the JSON file at ``json_path``.
    """
    if _db_enabled():
        persist_db(kind)
        return
    if json_path is not None:
        persist_json(json_path, records)


def load_all(kind: str, *, json_path: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    """Load one entity kind from the configured backend."""
    if _db_enabled():
        return load_db(kind)
    if json_path is not None:
        return read_json_file(json_path)
    return {}


def import_json_into_db(kind: str, records: Dict[str, Dict[str, Any]]) -> int:
    """One-time import of legacy JSON records into an empty database."""
    if not records:
        return 0
    from api import store

    container = store.container_for_kind(kind)
    # Only import kinds whose in-memory container is still empty.
    if container:
        return 0

    _last_flushed.pop(kind, None)
    imported = 0
    model_container = store.model_for_kind(kind)
    if model_container is None:
        return 0

    for record_id, payload in records.items():
        try:
            container[record_id] = model_container(**payload)
            imported += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("legacy_import_row_failed", kind=kind, record_id=record_id, error=str(exc))

    if imported:
        persist_db(kind)
        logger.info("legacy_import_done", kind=kind, imported=imported)
    return imported


def backup_json(path: Path) -> Optional[Path]:
    """Rename a legacy JSON file to ``*.imported`` after a successful import.

    An existing backup is never overwritten: if ``*.imported`` is already present
    the source file is moved aside with a numeric suffix instead, so a repeated
    migration cannot destroy an earlier snapshot.
    """
    if not path.exists():
        return None

    backup = path.with_suffix(path.suffix + ".imported")
    if backup.exists():
        for suffix in range(1, 100):
            candidate = path.with_suffix(f"{path.suffix}.imported.{suffix}")
            if not candidate.exists():
                backup = candidate
                break
        else:
            logger.warning("legacy_backup_skipped", path=str(path), reason="too many existing backups")
            return None

    try:
        path.replace(backup)
        return backup
    except Exception as exc:  # noqa: BLE001
        logger.warning("legacy_backup_failed", path=str(path), error=str(exc))
        return None


def pending_snapshot() -> Dict[str, int]:
    """Number of tracked rows per kind (diagnostics)."""
    return {kind: len(rows) for kind, rows in _last_flushed.items()}


def known_kinds() -> List[str]:
    """All supported entity kinds."""
    return list(ALL_KINDS)
