"""Read-only access to the rotating log files.

Why this exists
---------------
Diagnosing a failed task previously meant SSH-ing to the host and grepping by hand. Since
every log line now carries ``task_id`` and ``request_id``, a small read-only endpoint makes
those traces reachable from the console.

Safety
------
This endpoint can read files, so it is deliberately narrow:

* only two whitelisted names (``app`` / ``model``) — the caller never supplies a path;
* read **newest-first from the tail** with a hard line budget, rather than loading a 10 MB
  file into memory on a 2C2G box;
* output is re-scrubbed for secrets, because historical lines predate the masking rules;
* Token auth is inherited from the app's normal dependencies.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import structlog
from fastapi import APIRouter, HTTPException, Query

from api.logging_config import log_dir, model_log_enabled

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/logs", tags=["logs"])

# Logical name -> file name. A whitelist, so no request can influence the path.
LOG_FILES: dict[str, str] = {
    "app": "app.log",
    "model": "model.log",
}

MAX_LIMIT = 2000
DEFAULT_LIMIT = 200
# Read at most this many bytes while scanning for matches, so a query cannot read a whole
# 10 MB file (or several rotations) into memory.
MAX_SCAN_BYTES = 4 * 1024 * 1024
LEVEL_ORDER = {"debug": 10, "info": 20, "warning": 30, "error": 40, "critical": 50}


def _resolve(file_key: str) -> Path:
    name = LOG_FILES.get(str(file_key or "app").lower())
    if not name:
        raise HTTPException(status_code=400, detail=f"unknown log file {file_key!r}")
    if name == "model.log" and not model_log_enabled():
        raise HTTPException(status_code=409, detail="model payload logging is disabled")
    return log_dir() / name


def _read_tail(path: Path, *, max_bytes: int = MAX_SCAN_BYTES) -> list[str]:
    """Return the last ``max_bytes`` worth of lines, oldest-first within that window."""
    if not path.exists():
        return []
    size = path.stat().st_size
    with open(path, "rb") as handle:
        if size > max_bytes:
            handle.seek(size - max_bytes)
            handle.readline()  # discard the partial first line
        data = handle.read()
    return data.decode("utf-8", errors="replace").splitlines()


def _line_level(line: str) -> str:
    """Best-effort level extraction from either renderer."""
    try:
        document = json.loads(line)
        if isinstance(document, dict):
            level = document.get("level")
            if isinstance(level, str):
                return level.lower()
    except Exception:  # noqa: BLE001
        pass
    lowered = line.lower()
    for level in ("critical", "error", "warning", "info", "debug"):
        if f"[{level}" in lowered or f'"level": "{level}"' in lowered:
            return level
    return ""


def _scrub(line: str) -> str:
    """Mask anything that looks like a provider key, even in historical lines."""
    import re

    return re.sub(r"\bsk-[A-Za-z0-9_-]{12,}\b", lambda m: f"{m.group(0)[:4]}***{m.group(0)[-4:]}", line)


@router.get("")
async def read_logs(
    file: str = Query(default="app", description="Which log file: app | model"),
    level: Optional[str] = Query(default=None, description="Minimum level: debug|info|warning|error"),
    task_id: Optional[str] = Query(default=None),
    request_id: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None, description="Case-insensitive substring match"),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Return the most recent matching log lines, newest first."""
    path = _resolve(file)
    lines = _read_tail(path)
    total_scanned = len(lines)

    minimum = LEVEL_ORDER.get(str(level or "").lower(), 0)
    needle = str(q or "").lower()
    matched: list[dict[str, Any]] = []

    # Walk backwards so `limit` returns the newest entries first.
    for index in range(len(lines) - 1, -1, -1):
        line = lines[index]
        if minimum and LEVEL_ORDER.get(_line_level(line), 0) < minimum:
            continue
        if task_id and task_id not in line:
            continue
        if request_id and request_id not in line:
            continue
        if needle and needle not in line.lower():
            continue
        matched.append({"line_number": index + 1, "level": _line_level(line), "text": _scrub(line)})

    window = matched[offset : offset + limit]
    return {
        "file": file,
        "path": str(path),
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() else 0,
        "scanned_lines": total_scanned,
        "matched": len(matched),
        "offset": offset,
        "limit": limit,
        "items": window,
    }


@router.get("/files")
async def list_log_files() -> dict[str, Any]:
    """Report the configured log files and their sizes, for the disk-pressure check."""
    base = log_dir()
    files = []
    for key, name in LOG_FILES.items():
        if key == "model" and not model_log_enabled():
            continue
        path = base / name
        rotations = sorted(base.glob(f"{name}.*"))
        total = sum(p.stat().st_size for p in [path, *rotations] if p.exists())
        files.append(
            {
                "key": key,
                "name": name,
                "exists": path.exists(),
                "size_bytes": path.stat().st_size if path.exists() else 0,
                "rotations": len(rotations),
                "total_bytes": total,
            }
        )
    return {
        "dir": str(base),
        "files": files,
        "total_bytes": sum(item["total_bytes"] for item in files),
    }
