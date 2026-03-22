"""Helpers for logging model requests and responses with basic sanitization."""
from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from typing import Any


MODEL_LOG_MAX_CHARS = int((os.getenv("MODEL_LOG_MAX_CHARS") or "12000").strip() or "12000")


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


def log_model_request(logger: Any, *, event: str = "model_request", task_id: str, skill: str, context: Mapping[str, Any], request: Any) -> None:
    logger.info(
        event,
        task_id=task_id,
        skill=skill,
        request=_sanitize_value(request),
        **_sanitize_value(dict(context)),
    )


def log_model_response(logger: Any, *, event: str = "model_response", task_id: str, skill: str, context: Mapping[str, Any], response: Any) -> None:
    logger.info(
        event,
        task_id=task_id,
        skill=skill,
        response=_sanitize_value(response),
        **_sanitize_value(dict(context)),
    )
