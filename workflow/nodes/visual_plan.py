"""Plan article-aware visual assets from outline, evidence and draft content."""
from __future__ import annotations

from typing import Any

from workflow.state import WorkflowState
from workflow.utils.visual_briefs import build_visual_brief


def _inline_roles(outline_result: dict[str, Any], inline_count: int) -> list[dict[str, Any]]:
    outline = [dict(item) for item in list(outline_result.get("outline") or []) if isinstance(item, dict)]
    preferred = [
        item
        for item in outline
        if item.get("image_hint") == "inline" or str(item.get("shape") or "") in {"evidence", "case"}
    ]
    selected = (preferred or outline)[: max(0, inline_count)]
    briefs: list[dict[str, Any]] = []
    for item in selected:
        shape = str(item.get("shape") or "").strip()
        role = "infographic" if shape == "evidence" else "contextual_illustration"
        briefs.append(
            {
                "role": role,
                "section": str(item.get("section") or "").strip(),
                "purpose": str(item.get("goal") or "").strip(),
                "source_refs": list(item.get("source_refs") or []),
                "key_points": list(item.get("key_points") or []),
            }
        )
    return briefs


async def plan_visual_assets_node(state: WorkflowState) -> dict[str, Any]:
    """Generate image briefs for each requested visual role."""
    roles = list(state.get("planning_state", {}).get("visual_plan", {}).get("asset_roles") or [])
    visual_plan = dict(state.get("planning_state", {}).get("visual_plan") or {})
    outline_result = dict(state.get("outline_result") or state.get("planning_state", {}).get("outline_result") or {})
    image_policy = dict(state.get("config_snapshot", {}).get("image_policy") or {})
    topic = str(state.get("task_brief", {}).get("topic", ""))
    draft = dict(state.get("writing_state", {}).get("draft") or {})
    briefs = []
    if image_policy.get("enabled", True) is False:
        roles = []
    if outline_result:
        seed = dict(outline_result.get("image_plan_seed") or {})
        inline_count = int(image_policy.get("inline_count") if image_policy.get("inline_count") is not None else seed.get("inline_count") or 1)
        planned_roles = []
        if image_policy.get("cover_enabled", True) and seed.get("cover_needed", True):
            planned_roles.append({"role": "cover", "section": "封面", "purpose": "用文章核心判断吸引点击", "key_points": [outline_result.get("thesis", "")]})
        if image_policy.get("inline_enabled", True):
            planned_roles.extend(_inline_roles(outline_result, inline_count))
    else:
        planned_roles = [{"role": role} for role in roles]

    for planned in planned_roles:
        role = str(planned.get("role") or "").strip()
        if not role:
            continue
        brief = build_visual_brief(role, draft, topic)
        section = str(planned.get("section") or "").strip()
        purpose = str(planned.get("purpose") or "").strip()
        key_points = [str(item).strip() for item in list(planned.get("key_points") or []) if str(item).strip()]
        if section or purpose or key_points:
            brief["section"] = section
            brief["purpose"] = purpose
            brief["source_refs"] = list(planned.get("source_refs") or [])
            brief["key_points"] = key_points
            brief["compressed_prompt"] = (
                f"{brief.get('compressed_prompt', '')}. Article section: {section or 'cover'}. "
                f"Purpose: {purpose or 'support the article argument'}. "
                f"Use these article/data signals: {'; '.join(key_points) or draft.get('summary') or draft.get('title') or topic}. "
                "No fake UI screenshots, no unreadable small text, no watermark."
            )
        style = str(visual_plan.get("style") or "").strip()
        brand_colors = list(visual_plan.get("brand_colors") or [])
        if style or brand_colors:
            brief["compressed_prompt"] = (
                f"{brief.get('compressed_prompt', '')}, style preference: {style or 'brand consistent'}, "
                f"brand colors: {', '.join(str(item) for item in brand_colors) or 'not specified'}"
            )
        brief.update(
            {
                "style": style,
                "brand_colors": brand_colors,
                "title_safe_area": bool(visual_plan.get("title_safe_area", True)),
            }
        )
        briefs.append(brief)
    return {
        "status": "running",
        "current_skill": "plan_visual_assets",
        "progress": 68,
        "visual_state": {
            "image_briefs": briefs,
            "assets": [],
        },
    }
