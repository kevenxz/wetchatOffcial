"""Tests for the logging system.

The audit that prompted this found, with measurements:

* **47% of ``logs/app.log`` was test output** — ``setup_logging()`` runs at import time of
  ``api.main``, so any ``TestClient(app)`` test installed the production file handler.
* **Model payloads were 57% of the file**, single lines up to 30,309 characters, because
  ``MODEL_LOG_MAX_CHARS`` truncated each string field separately instead of the payload.
* **``httpx`` logged one INFO line per request** — 2,208 lines, 16% of all lines, since
  nothing set the library's level.
* **A second ``setup_logging()`` call stacked a second file handler**, duplicating lines.
* **No line carried a correlation id**, although ``merge_contextvars`` was configured.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
import structlog

from api.logging_config import (
    MODEL_PAYLOAD_LOGGER,
    log_dir,
    logging_diagnostics,
    setup_logging,
)
from workflow.model_logging import log_model_request, log_model_response

REQUIRED_JSON_KEYS = ("event", "level", "logger", "timestamp")


@pytest.fixture()
def log_dir_fixture(tmp_path) -> Path:
    """A throwaway log directory with logging pointed at it."""
    target = tmp_path / "logs"
    setup_logging(log_dir_override=target)
    yield target
    setup_logging(log_dir_override=target)


def _lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# --------------------------------------------------------------------------- #
# configuration hygiene
# --------------------------------------------------------------------------- #


def test_setup_logging_is_idempotent(log_dir_fixture: Path) -> None:
    """A second call must not stack a second file handler and duplicate every line."""
    before = len(logging.getLogger().handlers)
    setup_logging(log_dir_override=log_dir_fixture)
    setup_logging(log_dir_override=log_dir_fixture)

    assert len(logging.getLogger().handlers) == before

    structlog.get_logger("probe").info("once_only")
    app_lines = [line for line in _lines(log_dir_fixture / "app.log") if "once_only" in line]
    assert len(app_lines) == 1, f"event written {len(app_lines)} times"


def test_setup_logging_leaves_foreign_root_handlers_alone(log_dir_fixture: Path) -> None:
    """It must not clobber handlers installed by the host process.

    ``logging.basicConfig(force=True)`` removes *every* root handler, which silently
    detached pytest's own log capture.
    """
    foreign = logging.NullHandler()
    root = logging.getLogger()
    root.addHandler(foreign)
    try:
        setup_logging(log_dir_override=log_dir_fixture)
        assert foreign in root.handlers
    finally:
        root.removeHandler(foreign)


def test_log_level_is_honoured(tmp_path) -> None:
    target = tmp_path / "logs"
    setup_logging(log_dir_override=target, level="WARNING")
    try:
        log = structlog.get_logger("probe.level")
        log.info("info_should_be_filtered")
        log.warning("warning_should_appear")

        app_log = (target / "app.log").read_text(encoding="utf-8")
        assert "info_should_be_filtered" not in app_log
        assert "warning_should_appear" in app_log
    finally:
        setup_logging(log_dir_override=target, level="INFO")


@pytest.mark.parametrize("library", ["httpx", "httpcore", "urllib3", "openai"])
def test_third_party_loggers_are_pinned_to_warning(log_dir_fixture: Path, library: str) -> None:
    """httpx logs one INFO line per outbound request; that was 16% of all log lines."""
    assert logging.getLogger(library).level >= logging.WARNING


def test_third_party_info_is_suppressed_but_warnings_pass(log_dir_fixture: Path) -> None:
    logging.getLogger("httpx").info('HTTP Request: GET https://example.com "200 OK"')
    logging.getLogger("httpx").warning("httpx_problem_visible")

    app_log = (log_dir_fixture / "app.log").read_text(encoding="utf-8")
    assert "HTTP Request" not in app_log
    assert "httpx_problem_visible" in app_log


def test_diagnostics_report_the_effective_configuration(log_dir_fixture: Path) -> None:
    info = logging_diagnostics()

    assert info["level"] == "INFO"
    assert info["model_payloads"] is True
    assert logging.getLevelName(logging.getLogger("httpx").level) == "WARNING"


# --------------------------------------------------------------------------- #
# machine-readable output
# --------------------------------------------------------------------------- #


def test_file_output_is_valid_json_lines(log_dir_fixture: Path) -> None:
    structlog.get_logger("probe.json").info("json_event", task_id="t-1", nested={"a": 1})

    lines = _lines(log_dir_fixture / "app.log")
    assert lines
    for line in lines:
        document = json.loads(line)
        assert isinstance(document, dict)


def test_every_line_carries_the_fields_needed_to_filter_it(log_dir_fixture: Path) -> None:
    """Without these four keys a log line cannot be filtered by level or time."""
    structlog.get_logger("probe.keys").info("keyed_event")

    document = json.loads(_lines(log_dir_fixture / "app.log")[-1])
    for key in REQUIRED_JSON_KEYS:
        assert key in document, f"missing {key!r}"


# --------------------------------------------------------------------------- #
# model payload separation
# --------------------------------------------------------------------------- #


def test_main_log_keeps_metadata_and_the_payload_file_keeps_the_content(
    log_dir_fixture: Path,
) -> None:
    """The split that took model payloads out of the operational log."""
    big_prompt = {"topic": "x" * 800, "sources": [{"claim": "y" * 400} for _ in range(20)]}
    context = {"model": "deepseek/x", "base_url": "https://api.example.com/v1"}

    log_model_request(
        structlog.get_logger("probe.model"),
        task_id="t-payload",
        skill="compose_draft",
        context=context,
        request=big_prompt,
    )

    app_log = (log_dir_fixture / "app.log").read_text(encoding="utf-8")
    model_log = (log_dir_fixture / "model.log").read_text(encoding="utf-8")

    # Main log: metadata only.
    assert "xxxx" not in app_log
    assert "payload_chars" in app_log
    assert "payload_sha256" in app_log

    # Payload log: the real content, one JSON object per line.
    assert "xxxx" in model_log
    document = json.loads(model_log.splitlines()[0])
    assert document["task_id"] == "t-payload"
    assert document["direction"] == "request"
    assert isinstance(document["payload"], dict)


def test_payload_cap_applies_to_the_whole_payload_not_each_field(
    log_dir_fixture: Path, monkeypatch
) -> None:
    """The old per-string cap let a many-field dict grow without bound (30k-char lines)."""
    import workflow.model_logging as model_logging

    monkeypatch.setattr(model_logging, "MODEL_LOG_MAX_CHARS", 200)
    wide = {f"field_{index}": "z" * 100 for index in range(50)}

    log_model_response(
        structlog.get_logger("probe.model"),
        task_id="t-cap",
        skill="compose_draft",
        context={"model": "m", "base_url": ""},
        response=wide,
    )

    app_log = (log_dir_fixture / "app.log").read_text(encoding="utf-8")
    document = json.loads([line for line in app_log.splitlines() if "payload_chars" in line][-1])
    # `payload_chars` reports the true size; the flag tells a reader it was clipped.
    assert document["payload_chars"] > 200
    assert document["payload_truncated"] is True


def test_secrets_are_masked_in_both_destinations(log_dir_fixture: Path) -> None:
    secret = "sk-realsecretvalue1234567890"
    log_model_request(
        structlog.get_logger("probe.secret"),
        task_id="t-secret",
        skill="compose_draft",
        context={"model": "m", "base_url": "", "api_key_masked": "sk-r***7890"},
        request={"api_key": secret, "topic": "hello"},
    )

    app_log = (log_dir_fixture / "app.log").read_text(encoding="utf-8")
    model_log = (log_dir_fixture / "model.log").read_text(encoding="utf-8")

    assert secret not in app_log
    assert secret not in model_log
    assert "***" in model_log


def test_payload_file_can_be_switched_off(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MODEL_LOG_PAYLOADS", "false")
    # A subdirectory the autouse isolation fixture has not already populated — it ran
    # setup_logging with payloads enabled and created model.log in tmp_path/logs.
    target = tmp_path / "disabled" / "logs"
    setup_logging(log_dir_override=target)
    try:
        log_model_request(
            structlog.get_logger("probe.off"),
            task_id="t-off",
            skill="s",
            context={"model": "m", "base_url": ""},
            request={"topic": "should not be written"},
        )
        assert not (target / "model.log").exists()
        assert "should not be written" not in (target / "app.log").read_text(encoding="utf-8")
    finally:
        monkeypatch.delenv("MODEL_LOG_PAYLOADS", raising=False)
        setup_logging(log_dir_override=target)


# --------------------------------------------------------------------------- #
# correlation
# --------------------------------------------------------------------------- #


def test_contextvars_flow_into_the_log_line(log_dir_fixture: Path) -> None:
    """`merge_contextvars` was configured but nothing ever bound an id."""
    structlog.contextvars.bind_contextvars(request_id="req-abc123")
    try:
        structlog.get_logger("probe.ctx").info("correlated_event")
    finally:
        structlog.contextvars.unbind_contextvars("request_id")

    document = json.loads(_lines(log_dir_fixture / "app.log")[-1])
    assert document["request_id"] == "req-abc123"


def test_unbound_contextvars_do_not_leak_into_later_lines(log_dir_fixture: Path) -> None:
    structlog.contextvars.bind_contextvars(request_id="req-temp")
    structlog.contextvars.unbind_contextvars("request_id")
    structlog.get_logger("probe.ctx").info("after_unbind")

    document = json.loads(_lines(log_dir_fixture / "app.log")[-1])
    assert "request_id" not in document


# --------------------------------------------------------------------------- #
# the isolation guarantee that keeps tests out of the production log
# --------------------------------------------------------------------------- #


def test_tests_do_not_write_into_the_repository_log_directory() -> None:
    """The autouse fixture must keep file logging inside pytest's tmp directory.

    Before the fix, running one test module added lines to the real ``logs/app.log`` and
    47% of that file ended up being test output.
    """
    repository_log_dir = (Path(__file__).resolve().parent.parent / "logs").resolve()
    active = log_dir()

    assert active != repository_log_dir, "tests are configured to write to the real logs dir"
    assert "pytest-of-" in str(active) or "tmp" in str(active).lower()


def test_repository_log_directory_is_not_written_by_this_suite() -> None:
    repository_log = Path(__file__).resolve().parent.parent / "logs" / "app.log"
    if not repository_log.exists():
        pytest.skip("no repository log present")
    size_before = repository_log.stat().st_size

    structlog.get_logger("probe.isolation").warning("isolation_canary_event")

    assert "isolation_canary_event" not in repository_log.read_text(encoding="utf-8", errors="replace")
    assert repository_log.stat().st_size == size_before
