"""Author a concrete visual description for each planned illustration.

This is the step the pipeline never had. Previously the image prompt was assembled by
concatenating an internal role token, the topic and a wall of scraped prose, so the
model was never told what picture to draw and fell back to rendering the text it was
handed.

The description is authored **once per task** — a single structured call covering every
asset — so a cover and its inline illustrations stay stylistically coherent and the cost
is one call rather than one per image.
"""
from __future__ import annotations

from typing import Any

import structlog
from langchain_core.prompts import ChatPromptTemplate

from workflow.model_factory import invoke_structured, model_context, structured_chain
from workflow.model_logging import log_model_request, log_model_response
from workflow.state import WorkflowState
from workflow.utils.claim_clean import clean_claim, clean_claims
from workflow.utils.image_styles import forbidden_concepts_in, get_preset, resolve_style_id
from workflow.utils.visual_spec import (
    VisualSpec,
    VisualSpecBatch,
    assemble_image_prompt,
    build_fallback_spec,
    describe_spec,
    resolve_prompt_settings,
)

logger = structlog.get_logger(__name__)

STAGE = "describe_visual"

SYSTEM_PROMPT = (
    "You are an art director for a Chinese WeChat public-account article. "
    "For every requested illustration you describe ONE concrete photograph that could run "
    "beside that section of the article. "
    "A photographer will shoot exactly what you describe, so use physical nouns: objects, "
    "materials, surfaces, light and camera framing. "
    "Hard rules: "
    "(1) Never describe text, letters, numbers, words, captions, charts, graphs, diagrams, "
    "infographics, posters, screenshots, user interfaces, logos or watermarks appearing in the "
    "picture. Only if text_allowed is true may at most one short English word appear. "
    "(2) Describe scenes and objects instead of abstract concepts: do not write 'growth', "
    "'competition' or 'open access' as the subject; show the physical thing that stands for it. "
    "(3) Do not depict brand logos or recognisable product interfaces. "
    "(4) Keep every field short: subject under 18 words, setting under 18 words, composition "
    "under 14 words. "
    "(5) Write all fields in English. "
    "(6) section_link is one short sentence explaining how the picture relates to that "
    "section's argument; it is an audit note and is never sent to the image model. "
    "Return one entry per requested asset, echoing its asset_index."
)


def _asset_input(brief: dict[str, Any], index: int) -> dict[str, Any]:
    """Compact, cleaned description of what one asset has to illustrate."""
    return {
        "asset_index": index + 1,
        "role": str(brief.get("role") or ""),
        "section": str(brief.get("section") or "封面"),
        "argument": clean_claim(str(brief.get("purpose") or ""), limit=160),
        "key_points": clean_claims(list(brief.get("key_points") or []), limit=120, max_items=2),
        "aspect_ratio": str(brief.get("target_aspect_ratio") or "16:9"),
    }


def render_assets(assets: list[dict[str, Any]]) -> str:
    """Render the asset list as compact lines rather than nested JSON.

    Keeps the call cheap and stops the model from treating long prose as content to
    reproduce.
    """
    lines: list[str] = []
    for asset in assets:
        points = "; ".join(asset.get("key_points") or [])
        line = (
            f"- asset_index={asset.get('asset_index')} role={asset.get('role')} "
            f"aspect={asset.get('aspect_ratio')} section={asset.get('section')}"
        )
        if asset.get("argument"):
            line += f" argument={asset['argument']}"
        if points:
            line += f" points={points}"
        lines.append(line)
    return "\n".join(lines)


def _fallback_for(brief: dict[str, Any], role: str, article_anchor: str) -> VisualSpec:
    """Fallback spec anchored on the article, so two articles differ."""
    return build_fallback_spec(
        role,
        topic=article_anchor,
        section=str(brief.get("section") or ""),
        claim=str(brief.get("purpose") or ""),
    )


def resolve_specs(
    items: list[VisualSpec],
    briefs: list[dict[str, Any]],
    *,
    article_anchor: str = "",
) -> tuple[list[VisualSpec], list[str]]:
    """Map model output back onto briefs, falling back per asset.

    Matching is by the echoed ``asset_index`` first, then by position; otherwise the asset
    gets the safe fallback spec. A spec asking for text or a chart is rejected outright —
    that request is precisely what produced text-filled pictures.

    ``article_anchor`` (title + thesis) is passed to the fallback so a degraded run still
    produces article-relevant, per-article scenes instead of one global stock picture.
    """
    by_index: dict[int, VisualSpec] = {}
    for item in items:
        if item.asset_index and item.asset_index not in by_index:
            by_index[item.asset_index] = item

    specs: list[VisualSpec] = []
    reasons: list[str] = []
    for position, brief in enumerate(briefs):
        role = str(brief.get("role") or "")
        candidate = by_index.get(position + 1)
        if candidate is None and position < len(items):
            candidate = items[position]

        if candidate is None:
            specs.append(_fallback_for(brief, role, article_anchor))
            reasons.append(f"{role}:no_spec_returned")
            continue

        candidate.role = candidate.role or role
        if not candidate.is_usable():
            forbidden = forbidden_concepts_in(
                f"{candidate.subject} {candidate.setting} {candidate.composition}"
            )
            reason = f"{role}:forbidden_concept({','.join(forbidden)})" if forbidden else f"{role}:empty_spec"
            logger.warning(
                "visual_spec_rejected", role=role, reason=reason, subject=candidate.subject[:80]
            )
            specs.append(_fallback_for(brief, role, article_anchor))
            reasons.append(reason)
            continue

        specs.append(candidate)

    return specs, reasons


async def describe_visual_assets_node(state: WorkflowState) -> dict[str, Any]:
    """Fill each brief with a visual spec and the final, short image prompt."""
    visual_state = dict(state.get("visual_state") or {})
    briefs = [dict(brief) for brief in list(visual_state.get("image_briefs") or [])]
    image_policy = dict(state.get("config_snapshot", {}).get("image_policy") or {})
    draft = dict(state.get("writing_state", {}).get("draft") or {})
    blueprint = dict(state.get("planning_state", {}).get("article_blueprint") or {})
    topic = str(state.get("task_brief", {}).get("topic") or state.get("keywords") or "")

    style_id, max_chars = resolve_prompt_settings(image_policy)
    allow_text = bool(image_policy.get("allow_text_overlay"))
    brand_colors = [
        str(item).strip() for item in list(image_policy.get("brand_colors") or []) if str(item).strip()
    ]

    def finish(degraded_reason: str) -> dict[str, Any]:
        visual_state["image_briefs"] = briefs
        visual_state["visual_specs"] = [dict(brief.get("visual_spec") or {}) for brief in briefs]
        visual_state["style_id"] = style_id
        if degraded_reason:
            visual_state["describe_degraded_reason"] = degraded_reason
        return {
            "status": "running",
            "current_skill": STAGE,
            "progress": 70,
            "visual_state": visual_state,
        }

    if not briefs:
        return finish("")

    asset_inputs = [_asset_input(brief, index) for index, brief in enumerate(briefs)]

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            (
                "human",
                "article_title:\n{article_title}\n\narticle_thesis:\n{article_thesis}\n\n"
                "style:\n{style}\n\ntext_allowed:\n{text_allowed}\n\nassets:\n{assets}\n",
            ),
        ]
    )
    chain, retry_factory = structured_chain(
        prompt,
        stage=STAGE,
        schema=VisualSpecBatch,
        temperature=0.6,
    )

    degraded_reason = ""
    specs: list[VisualSpec] = []

    if chain is None:
        degraded_reason = "no_model_configured"
    else:
        request = {
            "article_title": clean_claim(str(draft.get("title") or topic), limit=80),
            "article_thesis": clean_claim(
                str(blueprint.get("thesis") or draft.get("summary") or ""), limit=160
            ),
            "style": str(get_preset(style_id).get("name") or ""),
            "text_allowed": "true" if allow_text else "false",
            "assets": render_assets(asset_inputs),
        }
        context = model_context(STAGE, structured_output="VisualSpecBatch")
        log_model_request(
            logger,
            task_id=str(state.get("task_id") or ""),
            skill=STAGE,
            context=context,
            request=request,
        )
        try:
            result = await invoke_structured(
                chain,
                request,
                stage=STAGE,
                build_retry_chain=retry_factory,
            )
            batch = result if isinstance(result, VisualSpecBatch) else VisualSpecBatch(**dict(result))
            specs, rejections = resolve_specs(
                list(batch.items),
                briefs,
                article_anchor=f"{request['article_title']} {request['article_thesis']}",
            )
            if rejections:
                degraded_reason = "spec_rejected:" + ",".join(rejections)
            log_model_response(
                logger,
                task_id=str(state.get("task_id") or ""),
                skill=STAGE,
                context=context,
                response={"items": [describe_spec(spec) for spec in specs]},
            )
        except Exception as exc:  # noqa: BLE001
            degraded_reason = getattr(exc, "reason", "") or "error"
            logger.warning(
                "describe_visual_fallback",
                task_id=str(state.get("task_id") or ""),
                degraded_reason=degraded_reason,
                error=str(exc),
                exc_info=True,
            )

    if not specs:
        anchor = f"{topic} {str(blueprint.get('thesis') or draft.get('summary') or '')}"
        specs = [
            build_fallback_spec(
                str(brief.get("role") or ""),
                topic=anchor,
                section=str(brief.get("section") or ""),
                claim=str(brief.get("purpose") or ""),
            )
            for brief in briefs
        ]
        degraded_reason = degraded_reason or "no_model_configured"

    for brief, spec in zip(briefs, specs):
        role = str(brief.get("role") or "")
        brief["visual_spec"] = describe_spec(spec)
        brief["compressed_prompt"] = assemble_image_prompt(
            spec=spec,
            style_id=style_id,
            role=role,
            brand_colors=brand_colors,
            max_chars=max_chars,
            allow_text=allow_text,
        )
        brief["style_id"] = style_id
        brief["prompt_max_chars"] = max_chars
        brief["allow_text_overlay"] = allow_text

    logger.info(
        "describe_visual_done",
        task_id=str(state.get("task_id") or ""),
        assets=len(briefs),
        style_id=style_id,
        degraded_reason=degraded_reason or None,
        prompt_chars=[len(str(brief.get("compressed_prompt") or "")) for brief in briefs],
    )
    return finish(degraded_reason)
