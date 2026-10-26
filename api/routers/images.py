"""Generated image assets: listing and style presets.

Why this router exists
----------------------
Roughly ninety generated pictures were sitting in ``artifacts/generated_images/`` with no
API and no UI to review them — the 「图片管理」page was an eleven-line placeholder. The
operator therefore had no way inside the product to check whether an image matched its
article, to read the prompt that produced it, or even to notice that one had failed.

Assets and their prompts live in each task's ``visual_state``, so this aggregates from the
task store rather than scanning the directory (a directory scan would lose the prompt, the
visual spec and the owning task).
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Query

from api.store import task_store
from workflow.agents.visual_reviewer import is_generated_asset
from workflow.utils.image_styles import list_image_styles

router = APIRouter(prefix="/images", tags=["images"])


def _asset_ref(asset: dict[str, Any]) -> str:
    """Public, browser-reachable reference for an asset."""
    url = str(asset.get("url") or "").strip()
    if url:
        return url
    path = str(asset.get("path") or "").strip()
    if not path or path.startswith("generated://"):
        return ""
    # Stored paths are either absolute or relative to the project root; the API mounts
    # ./artifacts at /artifacts, so both forms must become a mounted URL.
    normalized = path.replace("\\", "/")
    marker = "artifacts/"
    if marker in normalized:
        return "/artifacts/" + normalized.split(marker, 1)[1]
    return normalized


def _spec_for_role(briefs: list[dict[str, Any]], index: int) -> dict[str, Any]:
    if 0 <= index < len(briefs):
        return dict(briefs[index].get("visual_spec") or {})
    return {}


def _iter_task_images(task_id: str, task: Any) -> list[dict[str, Any]]:
    """Every asset on one task. Pagination is applied after the full collection."""
    visual_state = dict(getattr(task, "visual_state", None) or {})
    briefs = list(visual_state.get("image_briefs") or [])
    assets = list(visual_state.get("assets") or [])
    review = dict(visual_state.get("visual_review") or {})
    missing = {str(role) for role in list(review.get("missing") or [])}
    article = dict(getattr(task, "final_article", None) or getattr(task, "generated_article", None) or {})
    created_at = getattr(task, "created_at", None)

    items: list[dict[str, Any]] = []
    for index, asset in enumerate(assets):
        asset = dict(asset)
        role = str(asset.get("role") or "")
        generated = is_generated_asset(asset)
        items.append(
            {
                "task_id": task_id,
                "role": role,
                "ref": _asset_ref(asset),
                "prompt": str(asset.get("prompt") or ""),
                "visual_spec": _spec_for_role(briefs, index),
                "generated": generated,
                "degraded": (not generated) or role in missing,
                "style_id": str(visual_state.get("style_id") or ""),
                "article_title": str(article.get("title") or getattr(task, "keywords", "") or ""),
                "created_at": created_at.isoformat() if created_at else "",
            }
        )
    return items


@router.get("/styles")
async def get_image_styles() -> dict[str, Any]:
    """The named style presets the UI offers instead of a free-text style box."""
    return {"items": list_image_styles()}


@router.get("")
async def list_images(
    task_id: Optional[str] = Query(default=None, description="Restrict to one task"),
    limit: int = Query(default=60, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    degraded_only: bool = Query(default=False, description="Only assets that failed or are missing"),
) -> dict[str, Any]:
    """List generated image assets newest-first, with the prompt that produced each one."""
    collected: list[dict[str, Any]] = []

    for current_id, task in task_store.items():
        if task_id and current_id != task_id:
            continue
        collected.extend(_iter_task_images(current_id, task))

    collected.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)

    if degraded_only:
        collected = [item for item in collected if item.get("degraded")]

    total = len(collected)
    return {
        "items": collected[offset : offset + limit],
        "total": total,
        "offset": offset,
        "limit": limit,
    }
