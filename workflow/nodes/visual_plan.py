"""Plan article-aware visual assets from outline, evidence and draft content."""
from __future__ import annotations

from typing import Any

from workflow.state import WorkflowState
from workflow.utils.claim_clean import clean_claims
from workflow.utils.visual_briefs import build_visual_brief

# Outline goals embed their evidence inline as ``... 可用证据：<raw scraped claims>``.
# That raw text used to be copied straight into `purpose` and `key_points`, and from
# there into the image prompt — which is one of the reasons the generated pictures were
# full of text. Split it out so the two fields carry different things.
EVIDENCE_MARKER = "可用证据："


def _split_goal(goal: str) -> tuple[str, list[str]]:
    """Return (purpose, raw_claims) from an outline goal string."""
    text = str(goal or "").strip()
    if EVIDENCE_MARKER not in text:
        return text, []
    head, _, tail = text.partition(EVIDENCE_MARKER)
    claims = [part.strip() for part in tail.split("；") if part.strip()]
    return head.strip(), claims


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
        # Data-ish sections used to become ``infographic``, which literally instructs the
        # image model to draw a diagram — a request for text. They now get a photographic
        # scene with a "data" mood; the numbers stay in the article body where Chinese
        # renders correctly.
        role = "data_scene" if shape == "evidence" else "contextual_illustration"
        purpose, goal_claims = _split_goal(str(item.get("goal") or ""))
        key_points = clean_claims(
            [*list(item.get("key_points") or []), *goal_claims],
            limit=140,
            max_items=3,
        )
        briefs.append(
            {
                "role": role,
                "section": str(item.get("section") or "").strip(),
                "purpose": purpose,
                "source_refs": list(item.get("source_refs") or []),
                "key_points": key_points,
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
        # Structural brief only: which asset, which section, which size. The image
        # prompt is authored later from a model-written visual spec — this node must NOT
        # concatenate prose into a prompt, which is what produced text-filled pictures.
        brief = build_visual_brief(role, draft, topic)
        section = str(planned.get("section") or "").strip()
        purpose = _split_goal(str(planned.get("purpose") or ""))[0]
        key_points = clean_claims(list(planned.get("key_points") or []), limit=140, max_items=3)
        brief.update(
            {
                "section": section,
                "purpose": purpose,
                "source_refs": list(planned.get("source_refs") or []),
                "key_points": key_points,
                "style": str(visual_plan.get("style") or "").strip(),
                "brand_colors": list(visual_plan.get("brand_colors") or []),
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
