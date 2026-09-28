"""Tests for the stage-aware model factory."""
from __future__ import annotations

from unittest.mock import patch

from api.models import ImageModelConfig, ModelConfig, TextModelConfig
from workflow.model_factory import (
    FAST_STAGES,
    STRONG_STAGES,
    build_chat_model,
    model_context,
    resolve_text_config,
)


def _config(*, fast_key: str = "") -> ModelConfig:
    return ModelConfig(
        text=TextModelConfig(api_key="strong-key", base_url="https://strong.example/v1", model="strong-model"),
        text_fast=TextModelConfig(api_key=fast_key, base_url="https://fast.example/v1", model="fast-model"),
        image=ImageModelConfig(),
    )


def test_fast_stage_routes_to_fast_model_when_configured() -> None:
    with patch("workflow.model_factory.get_model_config", return_value=_config(fast_key="fast-key")):
        config, tier = resolve_text_config("review_article_draft")

    assert tier == "fast"
    assert config.model == "fast-model"


def test_fast_stage_falls_back_to_primary_model_without_fast_key() -> None:
    with patch("workflow.model_factory.get_model_config", return_value=_config(fast_key="")):
        config, tier = resolve_text_config("review_article_draft")

    assert tier == "strong"
    assert config.model == "strong-model"


def test_strong_stage_ignores_fast_model() -> None:
    with patch("workflow.model_factory.get_model_config", return_value=_config(fast_key="fast-key")):
        config, tier = resolve_text_config("compose_draft")

    assert tier == "strong"
    assert config.model == "strong-model"


def test_stage_sets_do_not_overlap() -> None:
    assert FAST_STAGES.isdisjoint(STRONG_STAGES)


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
