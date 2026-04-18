"""Generate visual assets from planned briefs."""
from __future__ import annotations

from typing import Any

import structlog

from api.store import get_model_config
from workflow.state import WorkflowState

logger = structlog.get_logger(__name__)


def _apply_visual_revision_brief(brief: dict[str, Any], revision_brief: dict[str, Any]) -> dict[str, Any]:
    guidance = [str(item).strip() for item in revision_brief.get("guidance", []) if str(item).strip()]
    if not guidance:
        return dict(brief)

    updated_brief = dict(brief)
    updated_brief["compressed_prompt"] = (
        f"{str(brief.get('compressed_prompt') or '').strip()}\n"
        f"Revision focus: {'; '.join(guidance)}"
    ).strip()
    return updated_brief


async def _generate_image_asset(
    task_id: str,
    brief: dict[str, Any],
    *,
    model: str,
    api_key: str,
    base_url: str | None,
) -> dict[str, str]:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    response = await client.images.generate(
        model=model,
        prompt=str(brief.get("compressed_prompt") or ""),
        size=str(brief.get("provider_size") or "1024x1024"),
    )

    data = getattr(response, "data", None) or response.get("data", [])  # type: ignore[union-attr]
    if not data:
        return {"url": "", "path": "", "mime_type": ""}

    first = data[0]
    if isinstance(first, dict):
        image_url = str(first.get("url") or "")
    else:
        image_url = str(getattr(first, "url", "") or "")
    return {"url": image_url, "path": "", "mime_type": "image/png" if image_url else ""}


def _placeholder_asset(brief: dict[str, Any]) -> dict[str, str]:
    role = str(brief.get("role") or "visual")
    return {
        "role": role,
        "prompt": str(brief.get("compressed_prompt") or ""),
        "path": f"generated://{role}",
        "url": "",
        "mime_type": "",
        "target_aspect_ratio": str(brief.get("target_aspect_ratio") or ""),
        "provider_size": str(brief.get("provider_size") or ""),
    }


async def generate_visual_assets_node(state: WorkflowState) -> dict[str, Any]:
    """Generate or fall back visual assets from image briefs."""
    visual_state = dict(state.get("visual_state") or {})
    briefs = list(visual_state.get("image_briefs") or [])
    revision_brief = dict(visual_state.get("revision_brief") or {})
    image_model_config = get_model_config().image
    assets: list[dict[str, str]] = []

    use_real_generation = bool(image_model_config.enabled and image_model_config.api_key)
    for brief in briefs:
        effective_brief = _apply_visual_revision_brief(brief, revision_brief)
        if not use_real_generation:
            assets.append(_placeholder_asset(effective_brief))
            continue

        try:
            generated = await _generate_image_asset(
                str(state.get("task_id") or ""),
                effective_brief,
                model=image_model_config.model,
                api_key=image_model_config.api_key,
                base_url=image_model_config.base_url,
            )
            assets.append(
                {
                    "role": str(effective_brief.get("role") or ""),
                    "prompt": str(effective_brief.get("compressed_prompt") or ""),
                    "url": generated.get("url", ""),
                    "path": generated.get("path", ""),
                    "mime_type": generated.get("mime_type", ""),
                    "target_aspect_ratio": str(effective_brief.get("target_aspect_ratio") or ""),
                    "provider_size": str(effective_brief.get("provider_size") or ""),
                }
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "generate_visual_asset_fallback",
                task_id=str(state.get("task_id") or ""),
                role=str(effective_brief.get("role") or ""),
                error=str(exc),
            )
            assets.append(_placeholder_asset(effective_brief))

    visual_state["assets"] = assets
    visual_state["revision_brief"] = {}
    return {
        "status": "running",
        "current_skill": "generate_visual_assets",
        "progress": 74,
        "visual_state": visual_state,
    }
