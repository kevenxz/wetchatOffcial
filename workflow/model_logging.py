"""Model request/response logging.

Split by purpose
----------------
* **``logs/app.log``** gets *metadata*: which stage ran, against which model, how big the
  prompt and the response were, and whether the provider truncated it. That is what you
  need when asking "why is this task slow / degraded?".
* **``logs/model.log``** gets the *full payload*. It used to go into the main log, where it
  accounted for **57% of the file** (single lines up to 30,309 characters), because the
  per-string truncation cap allowed a nested request dict with many fields to grow without
  bound. Keeping it in a separate rotating file preserves the debugging ability without
  drowning the operational log.

Every payload written to ``model.log`` is a standalone JSON object, and secrets are masked
in both destinations.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from api.logging_config import MODEL_PAYLOAD_LOGGER

# Cap applied to the *whole* serialised payload, not to each string field in turn.
MODEL_LOG_MAX_CHARS = int((os.getenv("MODEL_LOG_MAX_CHARS") or "12000").strip() or "12000")

# Keys whose values must never be written verbatim.
_SECRET_KEY_MARKERS = ("api_key", "apikey", "secret", "password", "token", "authorization")


def _truncate_text(value: str, max_chars: int = MODEL_LOG_MAX_CHARS) -> str:
    if len(value) <= max_chars:
        return value
    return f"{value[:max_chars]}...(truncated {len(value) - max_chars} chars)"


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, str):
        return _truncate_text(value)
    if isinstance(value, Mapping):
        return {str(key): _sanitize_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_sanitize_value(item) for item in value]
    return value


def mask_secret(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}***{value[-4:]}"


def _scrub_secrets(value: Any) -> Any:
    """Replace values under secret-looking keys, at any depth."""
    if isinstance(value, Mapping):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            name = str(key).lower()
            if any(marker in name for marker in _SECRET_KEY_MARKERS) and isinstance(item, str) and item:
                cleaned[str(key)] = mask_secret(item)
            else:
                cleaned[str(key)] = _scrub_secrets(item)
        return cleaned
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_scrub_secrets(item) for item in value]
    return value


def _summarize(payload: Any) -> tuple[int, str, bool]:
    """Return (char_count, sha256, truncated) for a payload without keeping its text."""
    try:
        text = json.dumps(payload, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        text = str(payload)
    truncated = len(text) > MODEL_LOG_MAX_CHARS
    digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]
    return len(text), digest, truncated


def build_model_context(*, model: str, base_url: str | None, api_key: str | None = None, **extra: Any) -> dict[str, Any]:
    context = {
        "model": model,
        "base_url": base_url or "",
    }
    if api_key is not None:
        context["api_key_masked"] = mask_secret(api_key)
    for key, value in extra.items():
        context[key] = _sanitize_value(value)
    return context


def _write_payload(
    *,
    direction: str,
    task_id: str,
    skill: str,
    context: Mapping[str, Any],
    payload: Any,
) -> None:
    """Append the full payload to ``logs/model.log`` as one JSON line."""
    logger = logging.getLogger(MODEL_PAYLOAD_LOGGER)
    if not logger.isEnabledFor(logging.INFO):
        return
    document = {
        "ts": datetime.now(tz=timezone.utc).isoformat(),
        "event": f"model_{direction}_payload",
        "task_id": task_id,
        "skill": skill,
        "direction": direction,
        "model": str(context.get("model") or ""),
        "model_tier": str(context.get("model_tier") or ""),
        "payload": _scrub_secrets(_sanitize_value(payload)),
    }
    try:
        serialized = json.dumps(document, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        serialized = json.dumps(
            {**document, "payload": _truncate_text(str(document["payload"]))}, ensure_ascii=False
        )
    logger.info(serialized)


def log_model_request(
    logger: Any,
    *,
    event: str = "model_request",
    task_id: str,
    skill: str,
    context: Mapping[str, Any],
    request: Any,
) -> None:
    """Record request metadata in the main log and the full prompt in the payload log."""
    char_count, digest, truncated = _summarize(request)
    logger.info(
        event,
        task_id=task_id,
        skill=skill,
        payload_chars=char_count,
        payload_sha256=digest,
        payload_truncated=truncated,
        **_sanitize_value(dict(context)),
    )
    _write_payload(direction="request", task_id=task_id, skill=skill, context=context, payload=request)


def log_model_response(
    logger: Any,
    *,
    event: str = "model_response",
    task_id: str,
    skill: str,
    context: Mapping[str, Any],
    response: Any,
) -> None:
    """Record response metadata in the main log and the full body in the payload log."""
    char_count, digest, truncated = _summarize(response)
    logger.info(
        event,
        task_id=task_id,
        skill=skill,
        payload_chars=char_count,
        payload_sha256=digest,
        payload_truncated=truncated,
        **_sanitize_value(dict(context)),
    )
    _write_payload(direction="response", task_id=task_id, skill=skill, context=context, payload=response)
