"""Global structlog configuration.

Design notes
------------
* **Idempotent and re-entrant.** ``setup_logging()`` may be called more than once — tests
  call it with their own directory — so every handler this module installs is tagged and
  detached before new ones are added. Without that, a second call stacks a second file
  handler and every line is written twice.
* **Test isolation.** ``api.main`` configures logging at *import* time, so any test doing
  ``from api.main import app`` used to install the production rotating file handler and
  write into the real ``logs/app.log`` — 47% of that file was test output. ``LOG_DIR``
  lets ``tests/conftest.py`` redirect file logging to a temp directory.
* **Two renderers.** The file gets JSON (machine-readable, grep/jq friendly, matches the
  project convention); the console gets readable text for humans. ``LOG_FORMAT``
  overrides both.
* **Third-party noise.** ``httpx`` logs every request at INFO, which was 16% of all log
  lines. Library loggers are pinned to WARNING.
* **Model payloads** go to their own rotating file so the main log stays about
  *behaviour* (see :mod:`workflow.model_logging`).
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
from pathlib import Path

import structlog

DEFAULT_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_BACKUP_COUNT = 5
DEFAULT_MODEL_MAX_BYTES = 20 * 1024 * 1024
DEFAULT_MODEL_BACKUP_COUNT = 3
DEFAULT_LEVEL = "INFO"

MODEL_PAYLOAD_LOGGER = "model.payload"

# Libraries whose INFO chatter drowns out the application's own events.
THIRD_PARTY_LOGGERS: tuple[str, ...] = (
    "httpx",
    "httpcore",
    "urllib3",
    "openai",
    "openai._base_client",
    "langchain",
    "langchain_core",
    "langchain_openai",
    "trafilatura",
    "asyncio",
    "multipart",
    "chardet",
)

# Tag applied to handlers we own, so a re-entrant call can remove exactly those.
_OWNED = "_wechat_logging_handler"


def _env_str(name: str, default: str = "") -> str:
    return (os.getenv(name) or "").strip() or default


def _env_int(name: str, default: int, *, minimum: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default


def resolve_level(name: str | None = None) -> int:
    """Resolve a log level name (env ``LOG_LEVEL`` by default) to a numeric level."""
    raw = (name if name is not None else _env_str("LOG_LEVEL", DEFAULT_LEVEL)).upper()
    return logging.getLevelName(raw) if isinstance(logging.getLevelName(raw), int) else logging.INFO


def log_dir() -> Path:
    """Directory holding the rotating log files (``LOG_DIR``, default ``logs/``)."""
    configured = _env_str("LOG_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parent.parent / "logs"


def model_log_enabled() -> bool:
    """Whether full model payloads are written to their own file."""
    return _env_str("MODEL_LOG_PAYLOADS", "true").lower() not in {"0", "false", "no", "off"}


class _HealthCheckFilter(logging.Filter):
    """Drop uvicorn access lines for the health endpoint.

    Orchestrators poll ``/api/health`` far more often than anything else, and those lines
    carry no diagnostic value once the service is up.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001
            return True
        return "/api/health" not in message


def _mark(handler: logging.Handler) -> logging.Handler:
    setattr(handler, _OWNED, True)
    return handler


def _detach_owned_handlers() -> None:
    """Remove and close every handler installed by a previous call."""
    loggers = [logging.getLogger(), logging.getLogger(MODEL_PAYLOAD_LOGGER)]
    loggers += [logging.getLogger(name) for name in (*THIRD_PARTY_LOGGERS, "uvicorn", "uvicorn.error", "uvicorn.access")]
    for logger in loggers:
        for handler in list(logger.handlers):
            if getattr(handler, _OWNED, False):
                logger.removeHandler(handler)
                try:
                    handler.close()
                except Exception:  # noqa: BLE001
                    pass


def _rotating_handler(
    path: Path,
    *,
    max_bytes: int,
    backup_count: int,
    formatter: logging.Formatter,
    level: int,
) -> logging.handlers.RotatingFileHandler:
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = _mark(
        logging.handlers.RotatingFileHandler(
            path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
    )
    handler.setFormatter(formatter)
    handler.setLevel(level)
    return handler


def setup_logging(
    *,
    log_dir_override: str | Path | None = None,
    level: int | str | None = None,
    file_format: str | None = None,
) -> None:
    """Configure console and rotating file logs.

    Rotation is required on a 2C2G single-machine deployment: an unrotated log file would
    eventually fill the disk and take the service down with it.

    ``log_dir_override`` / ``level`` / ``file_format`` exist so tests can redirect logging
    into a temporary directory instead of the repository's ``logs/``.
    """
    root_dir = Path(log_dir_override).expanduser().resolve() if log_dir_override else log_dir()
    numeric_level = level if isinstance(level, int) else resolve_level(level if isinstance(level, str) else None)

    # "json" forces JSON everywhere; "text" forces readable text; anything else keeps the
    # split default (JSON on disk, text on the console).
    requested = (file_format if file_format is not None else _env_str("LOG_FORMAT")).lower()
    if requested in {"json", "structured"}:
        file_json, console_json = True, True
    elif requested in {"text", "plain", "console"}:
        file_json, console_json = False, False
    else:
        file_json, console_json = True, False

    _detach_owned_handlers()

    file_handler = _rotating_handler(
        root_dir / "app.log",
        max_bytes=_env_int("LOG_MAX_BYTES", DEFAULT_MAX_BYTES, minimum=1024 * 64),
        backup_count=_env_int("LOG_BACKUP_COUNT", DEFAULT_BACKUP_COUNT, minimum=1),
        formatter=_processor_formatter(json_output=file_json),
        level=numeric_level,
    )

    console_handler = _mark(logging.StreamHandler(sys.stdout))
    console_handler.setFormatter(_processor_formatter(json_output=console_json))
    console_handler.setLevel(numeric_level)

    # Install onto the root logger explicitly rather than via
    # ``logging.basicConfig(force=True, ...)``. ``force=True`` removes *every* existing root
    # handler, including ones a host application (pytest's log capture, a WSGI runner)
    # installed. We only manage the handlers we created in `_detach_owned_handlers`.
    root = logging.getLogger()
    root.setLevel(numeric_level)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        # Deliberately False: caching on first use makes a later reconfiguration (tests,
        # or a level change) silently ignore the new processors.
        cache_logger_on_first_use=False,
    )

    _configure_third_party_loggers(numeric_level)
    _configure_model_payload_logger(root_dir, numeric_level)


def _processor_formatter(*, json_output: bool) -> structlog.stdlib.ProcessorFormatter:
    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer(ensure_ascii=False)
        if json_output
        else structlog.dev.ConsoleRenderer(colors=False)
    )
    return structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )


def _configure_third_party_loggers(level: int) -> None:
    """Pin library loggers above the application level so their chatter stays out.

    ``httpx`` logs one INFO line per outbound request; on a busy run that was thousands of
    lines with no diagnostic value.
    """
    for name in THIRD_PARTY_LOGGERS:
        logger = logging.getLogger(name)
        logger.setLevel(max(level, logging.WARNING))
        logger.propagate = True


def _configure_model_payload_logger(root_dir: Path, level: int) -> None:
    """Route full model payloads to ``logs/model.log`` on a dedicated logger.

    The handler uses a bare ``%(message)s`` formatter on purpose: callers pass an already
    serialised JSON document, so every line of ``model.log`` is a standalone JSON object
    that ``jq`` can read without a timestamp prefix getting in the way. Keeping this file
    independent of the structlog processor chain also means changing the console format
    can never corrupt recorded payloads.
    """
    logger = logging.getLogger(MODEL_PAYLOAD_LOGGER)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    logger.propagate = False

    if not model_log_enabled():
        logger.setLevel(logging.CRITICAL + 1)
        return

    handler = _mark(
        logging.handlers.RotatingFileHandler(
            root_dir / "model.log",
            maxBytes=_env_int("MODEL_LOG_MAX_BYTES", DEFAULT_MODEL_MAX_BYTES, minimum=1024 * 256),
            backupCount=_env_int("MODEL_LOG_BACKUP_COUNT", DEFAULT_MODEL_BACKUP_COUNT, minimum=1),
            encoding="utf-8",
        )
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.setLevel(level)
    logger.addHandler(handler)
    logger.setLevel(level)
    root_dir.mkdir(parents=True, exist_ok=True)


def install_uvicorn_loggers() -> None:
    """Route uvicorn's own loggers through the already-configured root handlers.

    Called separately from :func:`setup_logging` so a test can configure logging without
    also hijacking uvicorn's propagation.
    """
    root_handlers = list(logging.getLogger().handlers)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = root_handlers
        uvicorn_logger.propagate = False
        if name == "uvicorn.access":
            uvicorn_logger.addFilter(_HealthCheckFilter())


def logging_diagnostics() -> dict[str, object]:
    """Expose the effective logging configuration (used by tests and `/api/logs`)."""
    level_name = logging.getLevelName(logging.getLogger().level)
    return {
        "log_dir": str(log_dir()),
        "level": level_name if isinstance(level_name, str) else str(level_name),
        "model_payloads": model_log_enabled(),
        "files": {
            "app": str(log_dir() / "app.log"),
            "model": str(log_dir() / "model.log") if model_log_enabled() else "",
        },
        "third_party_level": logging.getLevelName(logging.getLogger("httpx").level),
    }


def _json_probe() -> str:
    """Small helper used by the tests to prove the file renderer emits valid JSON."""
    return json.dumps({"ok": True}, ensure_ascii=False)
