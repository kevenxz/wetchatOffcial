"""Workflow-wide configuration normalization."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from workflow.article_generation import normalize_generation_config


DEFAULT_ACCOUNT_PROFILE = {
    "positioning": "",
    "target_readers": [],
    "fit_tags": [],
    "avoid_topics": [],
}

DEFAULT_CONTENT_TEMPLATE = {
    "template_id": "auto",
    "name": "自动选择",
    "preferred_framework": "",
    "article_length": "medium",
    "tone": "",
}

DEFAULT_REVIEW_POLICY = {
    "strictness": "standard",
    "auto_rewrite": True,
    "require_human_review": False,
    "block_high_risk": True,
    "max_revision_rounds": 1,
}

DEFAULT_IMAGE_POLICY = {
    "enabled": True,
    "cover_enabled": True,
    "inline_enabled": True,
    "inline_count": 1,
    "style": "",
    "brand_colors": [],
    "title_safe_area": True,
}

DEFAULT_PUBLISH_POLICY = {
    "auto_publish_to_draft": True,
    "require_manual_confirmation": False,
}

DEFAULT_RESEARCH_POLICY = {
    "search_mode": "standard",
    "auto_deepen_for_sensitive_categories": True,
    "min_sources": 6,
    "min_official_sources": 1,
    "min_cross_sources": 3,
    "require_opposing_view": True,
    "freshness_window_days": 7,
}


def _clean_string_list(value: Any) -> list[str]:
    items: list[str] = []
    if not isinstance(value, list):
        return items
    for item in value:
        if not isinstance(item, str):
            continue
        cleaned = item.strip()
        if cleaned and cleaned not in items:
            items.append(cleaned)
    return items


def _merge_mapping(defaults: dict[str, Any], raw: Any) -> dict[str, Any]:
    payload = dict(defaults)
    if isinstance(raw, Mapping):
        payload.update({key: value for key, value in raw.items() if value is not None})
    return payload


def normalize_account_profile(raw: Any) -> dict[str, Any]:
    profile = _merge_mapping(DEFAULT_ACCOUNT_PROFILE, raw)
    profile["positioning"] = str(profile.get("positioning") or "").strip()
    profile["target_readers"] = _clean_string_list(profile.get("target_readers"))
    profile["fit_tags"] = _clean_string_list(profile.get("fit_tags"))
    profile["avoid_topics"] = _clean_string_list(profile.get("avoid_topics"))
    return profile


def normalize_content_template(raw: Any) -> dict[str, Any]:
    template = _merge_mapping(DEFAULT_CONTENT_TEMPLATE, raw)
    for key in ("template_id", "name", "preferred_framework", "article_length", "tone"):
        template[key] = str(template.get(key) or "").strip() or DEFAULT_CONTENT_TEMPLATE[key]
    return template


def normalize_review_policy(raw: Any) -> dict[str, Any]:
    policy = _merge_mapping(DEFAULT_REVIEW_POLICY, raw)
    strictness = str(policy.get("strictness") or "standard").strip()
    if strictness not in {"lenient", "standard", "strict"}:
        strictness = "standard"
    policy["strictness"] = strictness
    policy["auto_rewrite"] = bool(policy.get("auto_rewrite", True))
    policy["require_human_review"] = bool(policy.get("require_human_review", False))
    policy["block_high_risk"] = bool(policy.get("block_high_risk", True))
    policy["max_revision_rounds"] = max(0, min(int(policy.get("max_revision_rounds") or 1), 3))
    return policy


def normalize_image_policy(raw: Any) -> dict[str, Any]:
    policy = _merge_mapping(DEFAULT_IMAGE_POLICY, raw)
    policy["enabled"] = bool(policy.get("enabled", True))
    policy["cover_enabled"] = bool(policy.get("cover_enabled", True))
    policy["inline_enabled"] = bool(policy.get("inline_enabled", True))
    policy["inline_count"] = max(0, min(int(policy.get("inline_count") or 0), 4))
    policy["style"] = str(policy.get("style") or "").strip()
    policy["brand_colors"] = _clean_string_list(policy.get("brand_colors"))
    policy["title_safe_area"] = bool(policy.get("title_safe_area", True))
    return policy


def normalize_publish_policy(raw: Any, *, skip_auto_push: bool) -> dict[str, Any]:
    policy = _merge_mapping(DEFAULT_PUBLISH_POLICY, raw)
    policy["auto_publish_to_draft"] = bool(policy.get("auto_publish_to_draft", True)) and not skip_auto_push
    policy["require_manual_confirmation"] = bool(policy.get("require_manual_confirmation", False))
    return policy


def normalize_research_policy(raw: Any) -> dict[str, Any]:
    policy = _merge_mapping(DEFAULT_RESEARCH_POLICY, raw)
    search_mode = str(policy.get("search_mode") or "standard").strip()
    if search_mode not in {"quick", "standard", "deep", "strict"}:
        search_mode = "standard"
    policy["search_mode"] = search_mode
    policy["auto_deepen_for_sensitive_categories"] = bool(policy.get("auto_deepen_for_sensitive_categories", True))
    policy["min_sources"] = max(1, min(int(policy.get("min_sources") or 6), 30))
    policy["min_official_sources"] = max(0, min(int(policy.get("min_official_sources") or 1), 10))
    policy["min_cross_sources"] = max(1, min(int(policy.get("min_cross_sources") or 3), 20))
    policy["require_opposing_view"] = bool(policy.get("require_opposing_view", True))
    policy["freshness_window_days"] = max(1, min(int(policy.get("freshness_window_days") or 7), 365))
    return policy


def build_config_snapshot(
    *,
    generation_config: Mapping[str, Any] | None,
    hotspot_capture_config: Mapping[str, Any] | None,
    skip_auto_push: bool,
) -> dict[str, Any]:
    """Build one immutable-ish config snapshot for the workflow run."""
    generation = normalize_generation_config(generation_config)
    raw_generation = generation_config if isinstance(generation_config, Mapping) else {}
    hotspot = dict(hotspot_capture_config or {})
    mode = "auto_hotspot" if hotspot.get("enabled") else "manual"
    return {
        "mode": mode,
        "generation": generation,
        "hotspot": hotspot,
        "account_profile": normalize_account_profile(raw_generation.get("account_profile")),
        "content_template": normalize_content_template(raw_generation.get("content_template")),
        "review_policy": normalize_review_policy(raw_generation.get("review_policy")),
        "image_policy": normalize_image_policy(raw_generation.get("image_policy")),
        "publish_policy": normalize_publish_policy(
            raw_generation.get("publish_policy"),
            skip_auto_push=skip_auto_push,
        ),
        "research_policy": normalize_research_policy(raw_generation.get("research_policy")),
    }
