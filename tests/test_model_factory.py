"""Tests for stage-aware model routing in the model factory.

The routing rule changed after a production incident: every stage in this pipeline
requests a structured payload, and a *reasoning* model spent its whole completion
budget on hidden reasoning before emitting any JSON, so every stage silently fell
back to a deterministic template. Structured stages therefore default to the
``text_fast`` tier, which is expected to hold a non-reasoning model.
"""
from __future__ import annotations

from unittest.mock import patch

from api.models import ImageModelConfig, ModelConfig, TextModelConfig
from workflow import runtime_settings
from workflow.model_factory import (
    STRUCTURED_STAGES,
    build_chat_model,
    effective_routing,
    model_context,
    resolve_text_config,
)


def _config(*, fast_key: str = "") -> ModelConfig:
    return ModelConfig(
        text=TextModelConfig(api_key="strong-key", base_url="https://strong.example/v1", model="strong-model"),
        text_fast=TextModelConfig(api_key=fast_key, base_url="https://fast.example/v1", model="fast-model"),
        image=ImageModelConfig(),
    )


def test_structured_stage_routes_to_fast_tier_when_configured() -> None:
    with patch("workflow.model_factory.get_model_config", return_value=_config(fast_key="fast-key")):
        config, tier = resolve_text_config("review_article_draft")

    assert tier == "fast"
    assert config.model == "fast-model"


def test_structured_stage_falls_back_to_primary_without_fast_key() -> None:
    with patch("workflow.model_factory.get_model_config", return_value=_config(fast_key="")):
        config, tier = resolve_text_config("review_article_draft")

    assert tier == "strong"
    assert config.model == "strong-model"


def test_every_structured_stage_defaults_to_the_fast_tier() -> None:
    """All stages emit structured output, so none should be pinned to the primary."""
    with patch("workflow.model_factory.get_model_config", return_value=_config(fast_key="fast-key")):
        for stage in sorted(STRUCTURED_STAGES):
            _config_obj, tier = resolve_text_config(stage)
            assert tier == "fast", f"{stage} did not route to the structured tier"


def test_structured_tier_strong_routes_everything_to_the_primary_model() -> None:
    with patch("workflow.model_factory.get_model_config", return_value=_config(fast_key="fast-key")):
        with patch.dict("os.environ", {"LLM_STRUCTURED_TIER": "strong"}):
            config, tier = resolve_text_config("compose_draft")

    assert tier == "strong"
    assert config.model == "strong-model"


def test_invalid_structured_tier_falls_back_to_fast() -> None:
    with patch.dict("os.environ", {"LLM_STRUCTURED_TIER": "nonsense"}):
        assert runtime_settings.structured_tier() == "fast"


def test_strong_stages_pins_individual_stages_to_the_primary_model() -> None:
    with patch("workflow.model_factory.get_model_config", return_value=_config(fast_key="fast-key")):
        with patch.dict("os.environ", {"LLM_STRONG_STAGES": "compose_draft, design_viral_strategy"}):
            pinned, pinned_tier = resolve_text_config("compose_draft")
            other, other_tier = resolve_text_config("review_article_draft")

    assert pinned_tier == "strong"
    assert pinned.model == "strong-model"
    # Stages not listed keep using the structured tier.
    assert other_tier == "fast"
    assert other.model == "fast-model"


def test_build_chat_model_applies_timeout_and_retry_budget() -> None:
    with patch("workflow.model_factory.get_model_config", return_value=_config(fast_key="fast-key")):
        with patch("workflow.model_factory.ChatOpenAI") as mock_chat_openai:
            build_chat_model(stage="design_viral_strategy", max_tokens=700, temperature=0.4)

    kwargs = mock_chat_openai.call_args.kwargs
    assert kwargs["model"] == "fast-model"
    assert kwargs["api_key"] == "fast-key"
    assert kwargs["max_tokens"] == 700
    assert kwargs["temperature"] == 0.4
    # A bounded timeout prevents the SDK default of 600s from stalling a workflow.
    assert kwargs["timeout"] > 0
    assert kwargs["max_retries"] <= 3


def test_build_chat_model_returns_none_without_api_key() -> None:
    empty = ModelConfig(text=TextModelConfig(api_key=""), image=ImageModelConfig())
    with patch("workflow.model_factory.get_model_config", return_value=empty):
        assert build_chat_model(stage="compose_draft") is None


def test_model_context_records_tier_and_stage() -> None:
    with patch("workflow.model_factory.get_model_config", return_value=_config(fast_key="fast-key")):
        context = model_context("review_viral_potential", structured_output="ViralReviewOutput")

    assert context["model_tier"] == "fast"
    assert context["stage"] == "review_viral_potential"
    assert context["structured_output"] == "ViralReviewOutput"
    # Secrets are masked before they reach the structured log.
    assert "fast-key" not in str(context)


def test_effective_routing_reports_model_and_budget_per_stage() -> None:
    """A misrouted tier must be visible instead of only surfacing as a templated article."""
    with patch("workflow.model_factory.get_model_config", return_value=_config(fast_key="fast-key")):
        rows = effective_routing()

    assert {row["stage"] for row in rows} == set(STRUCTURED_STAGES)
    for row in rows:
        assert row["tier"] == "fast"
        assert row["model"] == "fast-model"
        assert row["key_configured"] is True
        assert row["fast_tier_configured"] is True
        assert row["max_tokens"] == runtime_settings.max_tokens_for(row["stage"])


def test_effective_routing_flags_missing_fast_tier() -> None:
    with patch("workflow.model_factory.get_model_config", return_value=_config(fast_key="")):
        rows = effective_routing()

    assert all(row["fast_tier_configured"] is False for row in rows)
    assert all(row["tier"] == "strong" for row in rows)


def test_max_tokens_defaults_leave_room_for_a_reasoning_model() -> None:
    """The pre-incident budgets were too small for reasoning models."""
    assert runtime_settings.max_tokens_for("plan_article_angle") >= 3000
    assert runtime_settings.max_tokens_for("compose_draft") >= 4000
    assert runtime_settings.max_tokens_for("compose_draft_revision") < runtime_settings.max_tokens_for("compose_draft")
    assert runtime_settings.max_tokens_for("review_article_draft") >= 1200
