"""Generate visual assets from planned briefs."""
from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Any

import structlog

from api.store import get_model_config
from workflow.state import WorkflowState

logger = structlog.get_logger(__name__)
GENERATED_IMAGES_DIR = Path("artifacts/generated_images")

_EVIDENCE_HEADING_KEYWORDS = (
    "数据",
    "证据",
    "事实",
    "指标",
    "图",
    "趋势",
    "数字",
    "信号",
    "验证",
)
_CASE_HEADING_KEYWORDS = (
    "案例",
    "公司",
    "玩家",
    "场景",
    "做法",
    "产品",
    "落地",
    "怎么做",
    "谁在",
)
_RISK_HEADING_KEYWORDS = (
    "风险",
    "边界",
    "挑战",
    "不确定",
    "变量",
    "误判",
)


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
        b64_json = str(first.get("b64_json") or first.get("image_base64") or "")
    else:
        image_url = str(getattr(first, "url", "") or "")
        b64_json = str(getattr(first, "b64_json", "") or getattr(first, "image_base64", "") or "")
    return {
        "url": image_url,
        "path": "",
        "mime_type": "image/png" if image_url or b64_json else "",
        "b64_json": b64_json,
        "output_format": str(getattr(response, "output_format", "") or (response.get("output_format", "") if isinstance(response, dict) else "") or ""),
    }


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


def _decode_base64_image(encoded: str) -> bytes:
    try:
        return base64.b64decode(encoded)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("image response contains invalid base64 content") from exc


def _sanitize_output_format(output_format: str | None) -> str:
    cleaned = "".join(ch for ch in str(output_format or "png").lower() if ch.isalnum())
    if cleaned == "jpeg":
        return "jpg"
    return cleaned or "png"


def _save_generated_image_bytes(
    image_bytes: bytes,
    *,
    task_id: str,
    image_kind: str,
    output_format: str | None = None,
) -> str:
    suffix = _sanitize_output_format(output_format)
    GENERATED_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    file_name = f"{task_id}_{image_kind}_{int(time.time() * 1000)}.{suffix}"
    path = (GENERATED_IMAGES_DIR / file_name).resolve()
    path.write_bytes(image_bytes)
    return str(path)


def _normalize_generated_asset_payload(
    generated: dict[str, Any],
    *,
    task_id: str,
    role: str,
) -> dict[str, str]:
    image_url = str(generated.get("url") or "").strip()
    image_path = str(generated.get("path") or "").strip()
    b64_json = str(generated.get("b64_json") or generated.get("image_base64") or "").strip()
    if not image_url and not image_path and b64_json:
        image_path = _save_generated_image_bytes(
            _decode_base64_image(b64_json),
            task_id=task_id,
            image_kind=role or "visual",
            output_format=str(generated.get("output_format") or "png"),
        )
    return {
        "url": image_url,
        "path": image_path,
        "mime_type": str(generated.get("mime_type") or ("image/png" if image_url or image_path else "")).strip(),
    }


def _asset_ref(asset: dict[str, Any]) -> str:
    return str(asset.get("url") or asset.get("path") or "").strip()


def _extract_h2_headings(lines: list[str]) -> list[tuple[int, str]]:
    return [
        (index, line[3:].strip())
        for index, line in enumerate(lines)
        if line.startswith("## ")
    ]


def _detect_heading_kind(heading: str) -> str:
    normalized = heading.strip()
    if any(keyword in normalized for keyword in _EVIDENCE_HEADING_KEYWORDS):
        return "evidence"
    if any(keyword in normalized for keyword in _CASE_HEADING_KEYWORDS):
        return "case"
    if any(keyword in normalized for keyword in _RISK_HEADING_KEYWORDS):
        return "risk"
    return "general"


def _target_kind_for_asset(asset: dict[str, Any]) -> str:
    role = str(asset.get("role") or "").strip().lower()
    prompt = str(asset.get("prompt") or "").strip().lower()
    if role in {"infographic", "comparison_graphic", "data_chart"}:
        return "evidence"
    if role in {"contextual_illustration", "scene_illustration", "case_illustration"}:
        return "case"
    if any(keyword in prompt for keyword in ("data", "evidence", "metric", "chart", "infographic")):
        return "evidence"
    if any(keyword in prompt for keyword in ("scene", "case", "company", "product")):
        return "case"
    return "general"


def _select_heading_slot(
    headings: list[tuple[int, str]],
    target_kind: str,
    assigned_counts: dict[int, int],
    fallback_cursor: int,
) -> int:
    if not headings:
        return -1

    matching_indexes = [
        index
        for index, (_, heading) in enumerate(headings)
        if _detect_heading_kind(heading) == target_kind
    ]
    if matching_indexes:
        return min(matching_indexes, key=lambda index: (assigned_counts.get(index, 0), index))
    return min(fallback_cursor, len(headings) - 1)


def _plan_illustration_assets(
    content: str,
    illustration_assets: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[int]]:
    if not illustration_assets:
        return [], []

    headings = _extract_h2_headings(content.splitlines())
    if not headings:
        return list(illustration_assets), [-1] * len(illustration_assets)

    planned: list[tuple[int, int, dict[str, Any]]] = []
    assigned_counts: dict[int, int] = {}
    fallback_cursor = 0
    for original_index, asset in enumerate(illustration_assets):
        slot = _select_heading_slot(headings, _target_kind_for_asset(asset), assigned_counts, fallback_cursor)
        if slot >= 0:
            assigned_counts[slot] = assigned_counts.get(slot, 0) + 1
            fallback_cursor = min(slot + 1, len(headings) - 1)
        planned.append((slot, original_index, asset))

    planned.sort(key=lambda item: ((item[0] if item[0] >= 0 else 10**6), item[1]))
    return [asset for _, _, asset in planned], [slot for slot, _, _ in planned]


def _insert_illustration_placeholders(content: str, illustration_assets: list[dict[str, Any]]) -> str:
    if not illustration_assets:
        return content

    lines = content.splitlines()
    ordered_assets, slots = _plan_illustration_assets(content, illustration_assets)
    headings = _extract_h2_headings(lines)
    if not headings:
        suffix = "\n\n" if content.strip() else ""
        placeholders = "\n\n".join(f"[插图{index}]" for index in range(1, len(ordered_assets) + 1))
        return f"{content}{suffix}{placeholders}".strip()

    inserts: list[tuple[int, str]] = []
    for idx, slot in enumerate(slots):
        heading_index = headings[slot][0] if slot >= 0 else headings[min(idx, len(headings) - 1)][0]
        insert_at = heading_index + 2 if heading_index + 1 < len(lines) else heading_index + 1
        inserts.append((insert_at, f"[插图{idx + 1}]"))

    offset = 0
    next_lines = list(lines)
    for insert_at, placeholder in inserts:
        next_lines.insert(insert_at + offset, "")
        next_lines.insert(insert_at + offset + 1, placeholder)
        offset += 2
    return "\n".join(next_lines)


def _merge_assets_into_article(article: dict[str, Any], assets: list[dict[str, str]]) -> dict[str, Any]:
    merged_article = dict(article)
    cover_image = ""
    illustration_assets: list[dict[str, Any]] = []
    for asset in assets:
        image_ref = _asset_ref(asset)
        if not image_ref:
            continue
        role = str(asset.get("role") or "").strip()
        if not cover_image and role == "cover":
            cover_image = image_ref
            continue
        illustration_assets.append(dict(asset))

    ordered_illustration_assets, _ = _plan_illustration_assets(
        str(merged_article.get("content") or ""),
        illustration_assets,
    )
    illustrations = [_asset_ref(asset) for asset in ordered_illustration_assets if _asset_ref(asset)]

    if cover_image:
        merged_article["cover_image"] = cover_image
    elif illustrations:
        merged_article["cover_image"] = illustrations[0]

    if illustrations:
        merged_article["illustrations"] = illustrations
    else:
        merged_article.setdefault("illustrations", [])

    merged_article["content"] = _insert_illustration_placeholders(
        str(merged_article.get("content") or ""),
        ordered_illustration_assets,
    )
    merged_article["visual_assets"] = assets
    return merged_article


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
            normalized = _normalize_generated_asset_payload(
                generated,
                task_id=str(state.get("task_id") or ""),
                role=str(effective_brief.get("role") or ""),
            )
            assets.append(
                {
                    "role": str(effective_brief.get("role") or ""),
                    "prompt": str(effective_brief.get("compressed_prompt") or ""),
                    "url": normalized.get("url", ""),
                    "path": normalized.get("path", ""),
                    "mime_type": normalized.get("mime_type", ""),
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
    generated_article = _merge_assets_into_article(dict(state.get("generated_article") or {}), assets)
    return {
        "status": "running",
        "current_skill": "generate_visual_assets",
        "progress": 74,
        "visual_state": visual_state,
        "generated_article": generated_article,
    }
