"""Workflow step tracing helpers."""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

SENSITIVE_KEYWORDS = (
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "authorization",
    "password",
    "secret",
    "cookie",
    "credential",
    "appsecret",
    "token",
)
MAX_STRING_LENGTH = 5000
MAX_LIST_ITEMS = 80
MAX_DICT_ITEMS = 160
MAX_DEPTH = 8


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(token in lowered for token in SENSITIVE_KEYWORDS)


def sanitize_step_payload(value: Any, *, depth: int = 0) -> Any:
    """Convert workflow data to a JSON-safe, redacted payload."""
    if depth > MAX_DEPTH:
        return {"truncated": True, "reason": "max_depth"}
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        if len(value) <= MAX_STRING_LENGTH:
            return value
        return {
            "truncated": True,
            "length": len(value),
            "preview": value[:MAX_STRING_LENGTH],
        }
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "model_dump"):
        try:
            return sanitize_step_payload(value.model_dump(mode="json"), depth=depth + 1)
        except Exception:  # noqa: BLE001
            return str(value)
    if isinstance(value, dict):
        items = list(value.items())
        payload: dict[str, Any] = {}
        for raw_key, raw_item in items[:MAX_DICT_ITEMS]:
            key = str(raw_key)
            if _is_sensitive_key(key):
                payload[key] = "[REDACTED]"
                continue
            payload[key] = sanitize_step_payload(raw_item, depth=depth + 1)
        if len(items) > MAX_DICT_ITEMS:
            payload["_truncated_items"] = len(items) - MAX_DICT_ITEMS
        return payload
    if isinstance(value, list | tuple | set):
        items = list(value)
        payload = [sanitize_step_payload(item, depth=depth + 1) for item in items[:MAX_LIST_ITEMS]]
        if len(items) > MAX_LIST_ITEMS:
            payload.append({"truncated": True, "remaining_items": len(items) - MAX_LIST_ITEMS})
        return payload
    return str(value)
