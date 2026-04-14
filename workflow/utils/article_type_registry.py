"""Strategy registry for planner-driven article types."""
from __future__ import annotations

from typing import Any


def get_article_type_registry() -> dict[str, dict[str, Any]]:
    """Return the initial built-in article type strategies."""
    return {
        "quick_news": {
            "type_id": "quick_news",
            "activation_signals": ["breaking", "announcement", "latest"],
            "recommended_section_shapes": ["what_happened", "why_it_matters", "who_is_affected"],
            "evidence_mix": {"fact": 0.5, "news": 0.3, "opinion": 0.1, "case": 0.05, "data": 0.05},
            "title_style": "fast_and_clear",
            "visual_preferences": ["cover", "contextual_illustration"],
            "quality_rules": ["must_answer_what_happened", "must_anchor_timeline"],
            "forbidden_patterns": ["generic_opener", "empty_summary"],
        },
        "hotspot_interpretation": {
            "type_id": "hotspot_interpretation",
            "activation_signals": ["hotspot", "controversy", "viral"],
            "recommended_section_shapes": ["hook", "context", "interpretation", "impact", "watch_next"],
            "evidence_mix": {"fact": 0.25, "news": 0.25, "opinion": 0.2, "case": 0.15, "data": 0.15},
            "title_style": "angle_driven",
            "visual_preferences": ["cover", "infographic"],
            "quality_rules": ["must_connect_hotspot_naturally", "must_show_reader_value"],
            "forbidden_patterns": ["forced_trend_hijack"],
        },
        "trend_analysis": {
            "type_id": "trend_analysis",
            "activation_signals": ["trend", "market", "signal", "outlook"],
            "recommended_section_shapes": ["hook", "drivers", "evidence", "risks", "next_steps"],
            "evidence_mix": {"fact": 0.2, "news": 0.15, "opinion": 0.15, "case": 0.2, "data": 0.3},
            "title_style": "insight_first",
            "visual_preferences": ["cover", "infographic", "comparison_graphic"],
            "quality_rules": ["must_explain_drivers", "must_include_risk_boundary"],
            "forbidden_patterns": ["unsupported_prediction"],
        },
    }
