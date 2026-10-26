"""Tests for the atomic JSON write.

The production log carried 27 occurrences of::

    workflow_step_trace_create_failed error=[WinError 5] 拒绝访问。:
      'data\\workflow_run_steps.tmp' -> 'data\\workflow_run_steps.json'

Two defects produced that:

1. the temporary file was ``path.with_suffix(".tmp")`` — **the same name for every
   concurrent writer**, so overlapping writes shared one scratch file;
2. ``Path.replace`` was called once, with no retry. On Windows it maps to ``MoveFileEx``,
   which fails with "Access is denied" whenever another handle holds the destination, and
   the failure was downgraded to a warning and swallowed.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from api import persistence
from api.persistence import write_json_file


def test_writes_the_document(tmp_path) -> None:
    target = tmp_path / "store.json"

    write_json_file(target, {"a": 1, "中文": "值"})

    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1, "中文": "值"}


def test_leaves_no_temporary_files_behind(tmp_path) -> None:
    target = tmp_path / "store.json"

    write_json_file(target, {"a": 1})

    assert [p.name for p in tmp_path.glob("*.tmp")] == []


def test_temporary_names_are_unique_per_write(tmp_path, monkeypatch) -> None:
    """The old ``store.json.tmp`` was shared by every concurrent writer."""
    seen: list[str] = []
    real_replace = Path.replace

    def spy(self: Path, other: Path):  # noqa: ANN001
        seen.append(self.name)
        return real_replace(self, other)

    monkeypatch.setattr(Path, "replace", spy)

    for index in range(5):
        write_json_file(tmp_path / "store.json", {"i": index})

    assert len(set(seen)) == len(seen), f"temporary names collided: {seen}"
    assert all(name != "store.json.tmp" for name in seen)


def test_concurrent_writers_produce_a_valid_file_and_no_collisions(tmp_path) -> None:
    """Six threads hammering one file must not corrupt it or leave scratch files."""
    target = tmp_path / "store.json"
    errors: list[str] = []

    def worker(worker_id: int) -> None:
        try:
            for index in range(15):
                write_json_file(target, {"writer": worker_id, "i": index})
        except Exception as exc:  # noqa: BLE001
            errors.append(repr(exc))

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    document = json.loads(target.read_text(encoding="utf-8"))
    assert set(document) == {"writer", "i"}
    assert [p.name for p in tmp_path.glob("*.tmp")] == []


def test_retries_a_transient_sharing_violation(tmp_path, monkeypatch) -> None:
    """A single ``WinError 5`` must not lose the write."""
    target = tmp_path / "store.json"
    attempts = {"count": 0}
    real_replace = Path.replace

    def flaky(self: Path, other: Path):  # noqa: ANN001
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise PermissionError("[WinError 5] simulated sharing violation")
        return real_replace(self, other)

    monkeypatch.setattr(Path, "replace", flaky)
    write_json_file(target, {"recovered": True})

    assert json.loads(target.read_text(encoding="utf-8")) == {"recovered": True}
    assert attempts["count"] == 2


def test_gives_up_loudly_and_cleans_up_after_persistent_failure(tmp_path, monkeypatch) -> None:
    """After exhausting retries it must raise and leave no scratch file behind."""
    target = tmp_path / "store.json"

    def always_locked(self: Path, other: Path):  # noqa: ANN001
        raise PermissionError("[WinError 5] permanently locked")

    monkeypatch.setattr(Path, "replace", always_locked)
    monkeypatch.setattr(persistence, "_REPLACE_RETRY_DELAYS", (0.0, 0.0))

    with pytest.raises(PermissionError):
        write_json_file(target, {"lost": True})

    assert [p.name for p in tmp_path.glob("*.tmp")] == []


def test_retry_schedule_is_short_enough_for_a_request_path() -> None:
    """This runs inline on the persistence path, so the backoff must stay modest."""
    assert sum(persistence._REPLACE_RETRY_DELAYS) < 1.0
    assert len(persistence._REPLACE_RETRY_DELAYS) >= 2
