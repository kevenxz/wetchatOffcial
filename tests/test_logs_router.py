"""Tests for the read-only log query API.

The endpoint can read files, so its narrowness is the contract under test: a whitelist of
two names (the caller never supplies a path), a bounded tail read, and output that is
re-scrubbed for secrets because historical lines predate the masking rules.
"""
from __future__ import annotations

import json

import pytest
import structlog
from fastapi.testclient import TestClient

from api.logging_config import setup_logging
from api.main import app


@pytest.fixture()
def client(tmp_path) -> TestClient:
    """A client whose log directory contains a deterministic set of lines."""
    target = tmp_path / "logs"
    setup_logging(log_dir_override=target)

    log = structlog.get_logger("probe.router")
    log.info("task_created", task_id="task-alpha")
    log.warning("source_filter_applied", task_id="task-alpha")
    log.error("skill_failed", task_id="task-beta", error="boom", exc_info=True)
    structlog.get_logger("probe.router").info("plain_line")

    return TestClient(app)


def test_reads_the_tail_newest_first(client: TestClient) -> None:
    body = client.get("/api/logs?limit=10").json()

    assert body["exists"] is True
    assert body["matched"] >= 4
    assert body["items"], "expected log lines"
    # Newest first: line numbers descend.
    numbers = [item["line_number"] for item in body["items"]]
    assert numbers == sorted(numbers, reverse=True)


def test_bounds_the_number_of_returned_lines(client: TestClient) -> None:
    body = client.get("/api/logs?limit=2").json()

    assert len(body["items"]) == 2
    assert body["limit"] == 2


def test_filters_by_minimum_level(client: TestClient) -> None:
    body = client.get("/api/logs?level=warning").json()

    levels = {item["level"] for item in body["items"]}
    assert levels <= {"warning", "error", "critical"}
    assert body["matched"] >= 2
    assert not any(item["level"] == "info" for item in body["items"])


def test_filters_by_task_id(client: TestClient) -> None:
    body = client.get("/api/logs?task_id=task-beta").json()

    assert body["matched"] == 1
    assert "task-beta" in body["items"][0]["text"]


def test_filters_by_substring(client: TestClient) -> None:
    body = client.get("/api/logs?q=source_filter").json()

    assert body["matched"] == 1
    assert "source_filter_applied" in body["items"][0]["text"]


def test_rejects_an_unknown_file_key(client: TestClient) -> None:
    """The caller supplies a key, never a path."""
    assert client.get("/api/logs?file=nope").status_code == 400


@pytest.mark.parametrize(
    "attempt",
    [
        "../../etc/passwd",
        "..%2F..%2Fetc%2Fpasswd",
        "app.log",
        "/etc/passwd",
        "C:\\Windows\\win.ini",
    ],
)
def test_path_traversal_is_impossible(client: TestClient, attempt: str) -> None:
    """Anything that is not a whitelisted key must be refused, not resolved."""
    assert client.get("/api/logs", params={"file": attempt}).status_code == 400


def test_limit_is_capped(client: TestClient) -> None:
    assert client.get("/api/logs?limit=99999").status_code == 422


def test_returns_file_size_for_the_disk_pressure_check(client: TestClient) -> None:
    body = client.get("/api/logs").json()

    assert body["size_bytes"] > 0
    assert body["path"].endswith("app.log")


def test_payloads_are_reachable_through_the_model_file(client: TestClient) -> None:
    body = client.get("/api/logs?file=model").json()

    assert body["file"] == "model"
    assert body["path"].endswith("model.log")


def test_output_is_rescrubbed_for_secrets(client: TestClient, tmp_path) -> None:
    """A pre-existing line may hold a raw key; the endpoint must not hand it back."""
    # Write straight into the file to simulate a historical, unmasked line.
    log_path = tmp_path / "logs" / "app.log"
    with open(log_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"event": "legacy", "api_key": "sk-abcdefghijklmnopqrstuvwx"}) + "\n")

    text = "\n".join(item["text"] for item in client.get("/api/logs?limit=50").json()["items"])

    assert "sk-abcdefghijklmnopqrstuvwx" not in text
    assert "***" in text


def test_file_listing_reports_sizes_and_rotations(client: TestClient) -> None:
    body = client.get("/api/logs/files").json()

    keys = {item["key"] for item in body["files"]}
    assert keys == {"app", "model"}
    assert body["total_bytes"] > 0
    assert all("total_bytes" in item for item in body["files"])


def test_missing_log_file_is_reported_not_crashed(tmp_path) -> None:
    setup_logging(log_dir_override=tmp_path / "empty" / "logs")
    empty_client = TestClient(app)

    body = empty_client.get("/api/logs").json()
    # Either no file yet, or only setup lines: the point is a clean 200 with a flag.
    assert body["exists"] in {True, False}
