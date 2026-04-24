"""Assemble the final article package before publishing or human review."""
from __future__ import annotations

from typing import Any

from workflow.state import WorkflowState


def _asset_ref(asset: dict[str, Any]) -> str:
    return str(asset.get("url") or asset.get("path") or "").strip()


def _merge_visuals(article: dict[str, Any], visual_state: dict[str, Any]) -> dict[str, Any]:
    merged = dict(article)
    assets = [dict(item) for item in list(visual_state.get("assets") or []) if isinstance(item, dict)]
    cover_image = str(merged.get("cover_image") or "").strip()
    illustrations = [
        str(item).strip()
        for item in list(merged.get("illustrations") or [])
        if str(item).strip()
    ]

    for asset in assets:
        ref = _asset_ref(asset)
        if not ref:
            continue
        role = str(asset.get("role") or "").strip()
        if role == "cover" and not cover_image:
            cover_image = ref
            continue
        if ref not in illustrations:
            illustrations.append(ref)

    if cover_image:
        merged["cover_image"] = cover_image
    elif illustrations:
        merged["cover_image"] = illustrations[0]

    merged["illustrations"] = illustrations
    merged["visual_assets"] = assets
    return merged


def _build_publish_decision(
    quality_state: dict[str, Any],
    config_snapshot: dict[str, Any],
    skip_auto_push: bool,
) -> dict[str, Any]:
    quality_report = dict(quality_state.get("quality_report") or {})
    review_policy = dict(config_snapshot.get("review_policy") or {})
    publish_policy = dict(config_snapshot.get("publish_policy") or {})
    blocking_reasons = list(quality_report.get("blocking_reasons") or [])
    require_human = bool(
        review_policy.get("require_human_review")
        or publish_policy.get("require_manual_confirmation")
        or quality_state.get("next_action") == "human_review"
        or quality_state.get("human_review_required")
        or blocking_reasons
    )
    auto_publish_to_draft = bool(publish_policy.get("auto_publish_to_draft", True)) and not skip_auto_push
    return {
        "ready_to_publish": not require_human,
        "human_review_required": require_human,
        "auto_publish_to_draft": auto_publish_to_draft,
        "blocking_reasons": blocking_reasons,
        "next_step": "human_review" if require_human else ("push_to_draft" if auto_publish_to_draft else "manual_push"),
    }


async def assemble_article_node(state: WorkflowState) -> dict[str, Any]:
    """Create a final article package with metadata and publish decision."""
    generated_article = dict(state.get("generated_article") or {})
    visual_state = dict(state.get("visual_state") or {})
    quality_state = dict(state.get("quality_state") or {})
    config_snapshot = dict(state.get("config_snapshot") or {})
    final_article = _merge_visuals(generated_article, visual_state)
    publish_decision = _build_publish_decision(
        quality_state,
        config_snapshot,
        bool(state.get("skip_auto_push")),
    )
    final_article.update(
        {
            "selected_topic": state.get("selected_topic"),
            "selected_hotspot": state.get("selected_hotspot"),
            "quality_report": quality_state.get("quality_report"),
            "publish_decision": publish_decision,
        }
    )
    return {
        "status": "running",
        "current_skill": "assemble_article",
        "progress": 94,
        "final_article": final_article,
        "generated_article": final_article,
        "human_review_required": publish_decision["human_review_required"],
        "quality_state": {
            **quality_state,
            "publish_decision": publish_decision,
            "ready_to_publish": publish_decision["ready_to_publish"],
            "human_review_required": publish_decision["human_review_required"],
        },
    }
