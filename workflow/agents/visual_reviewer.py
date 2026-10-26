"""Review generated visual assets — structural checks only.

What this module deliberately is NOT
------------------------------------
It cannot see the picture. It has no vision model, so it cannot tell whether an image
matches the article or whether it came back full of text. The previous implementation
nonetheless reported ``score: 82`` and ``passed: true`` unconditionally, which told the
operator that a wall of garbled Chinese text had passed review. Misleading a human is
worse than admitting the check is shallow, so this now says exactly what it did.

It also had a real bug: a failed generation degrades to a placeholder whose
``path`` is ``generated://<role>``. The old presence check treated that truthy path as a
valid asset, so **generation failures passed review**.
"""
from __future__ import annotations

from typing import Any

from workflow.state import WorkflowState
from workflow.utils.source_images import crop_discard_warn_ratio

# Marker written by `image_generation._placeholder_asset` when generation fails.
PLACEHOLDER_PREFIX = "generated://"
PLACEHOLDER_PATH = "generated://"

# Roles that need supporting data in the evidence pack to be meaningful.
DATA_ROLES = frozenset({"data_scene", "infographic", "comparison_graphic", "data_chart"})

CHECK_NOTE = (
    "仅做结构检查：确认图片是否成功生成。本系统没有视觉模型，"
    "无法判断画面内容是否与文章一致、是否包含文字，请人工确认。"
)


def is_source_asset(asset: dict[str, Any]) -> bool:
    """Whether the asset is a real photograph harvested from a reference article."""
    return str(asset.get("provider") or "") == "source"


def has_real_image(asset: dict[str, Any]) -> bool:
    """Whether the asset points at an actual file rather than a failed-generation placeholder.

    A placeholder has a non-empty ``path`` (``generated://<role>``) but no file behind it, so a
    naive "has a path" check counts failures as successes. Covers both model-generated images
    and harvested photographs.
    """
    url = str(asset.get("url") or "").strip()
    path = str(asset.get("path") or "").strip()
    if not url and not path:
        return False
    if url.startswith(PLACEHOLDER_PREFIX) or path.startswith(PLACEHOLDER_PREFIX):
        return False
    return True


def is_generated_asset(asset: dict[str, Any]) -> bool:
    """Whether the asset is a model-generated image (harvested photos are not counted)."""
    if is_source_asset(asset):
        return False
    return has_real_image(asset)


async def review_visual_assets_node(state: WorkflowState) -> dict[str, Any]:
    """Run a structural review over the generated visual assets."""
    visual_state = dict(state.get("visual_state") or {})
    assets = [dict(asset) for asset in list(visual_state.get("assets") or [])]
    evidence_pack = dict(state.get("research_state", {}).get("evidence_pack") or {})
    research_gaps = list(evidence_pack.get("research_gaps") or [])

    findings: list[dict[str, Any]] = []
    missing: list[str] = []

    for asset in assets:
        role = str(asset.get("role") or "visual")
        if not has_real_image(asset):
            reason = "placeholder" if str(asset.get("path") or "").startswith(PLACEHOLDER_PREFIX) else "missing"
            missing.append(role)
            findings.append(
                {
                    "role": role,
                    "type": reason,
                    "message": "图片未生成成功" if reason == "placeholder" else "缺少生成的图片文件",
                }
            )
            continue

        if is_source_asset(asset):
            attribution = dict(asset.get("attribution") or {})
            if not attribution.get("source_url") or not (
                attribution.get("source_title") or attribution.get("source_domain")
            ):
                # Should be impossible: the harvester refuses unattributable images. Reported
                # rather than assumed, because silently using one would break the policy.
                findings.append(
                    {
                        "role": role,
                        "type": "source_attribution",
                        "message": "来源照片缺少出处信息，无法追溯",
                    }
                )
            # A heavy crop is flagged, not rejected: this check has no vision model and cannot
            # tell whether the subject survived the crop.
            discarded = float(asset.get("crop_discarded_ratio") or 0)
            if discarded >= crop_discard_warn_ratio():
                findings.append(
                    {
                        "role": role,
                        "type": "source_crop",
                        "message": (
                            f"封面裁切丢弃了 {discarded:.0%} 的画面，本系统无法判断主体是否被裁掉，请人工确认"
                        ),
                    }
                )
        if role in DATA_ROLES and "missing_data_evidence" in research_gaps:
            findings.append(
                {
                    "role": role,
                    "type": "evidence",
                    "message": "该配图所属小节缺少数据证据支撑",
                }
            )

    requested = len(list(visual_state.get("image_briefs") or []))
    generated_count = len([asset for asset in assets if is_generated_asset(asset)])
    source_count = len([asset for asset in assets if is_source_asset(asset)])
    # Only the model-generated slots can fall short; harvested photos are a bonus on top.
    if requested and generated_count + len(missing) < requested:
        findings.append(
            {
                "type": "count",
                "message": f"计划生成 {requested} 张，实际返回 {generated_count} 张",
            }
        )

    degraded_reason = ""
    if missing:
        degraded_reason = "visual_assets_missing:" + ",".join(missing)
    elif findings:
        degraded_reason = "visual_assets_structural_findings"

    visual_state["visual_review"] = {
        "check": "structural_only",
        "passed": not findings,
        "requested": requested,
        "generated": generated_count,
        "source_photos": source_count,
        "missing": missing,
        "findings": findings,
        "note": CHECK_NOTE,
    }
    if degraded_reason:
        visual_state["visual_degraded_reason"] = degraded_reason

    return {
        "status": "running",
        "current_skill": "review_visual_assets",
        "progress": 78,
        "visual_state": visual_state,
    }
