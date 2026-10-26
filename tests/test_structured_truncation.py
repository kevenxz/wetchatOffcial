"""Tests for truncated structured output handling.

This is the incident that hid everything else: the configured model was a *reasoning*
model, whose hidden reasoning consumed the entire completion budget, so
``with_structured_output`` never received parseable JSON. Every stage then fell back
to its deterministic template, and because the fallback was only a warning the
product looked like it was "generating" articles with a fixed structure.

The contract now: truncation is classified, logged under a dedicated event, retried
once with a larger budget when allowed, and otherwise raised as
``StructuredOutputError(reason="truncated")`` so callers can record a precise reason.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.models import TextModelConfig
from workflow import runtime_settings
from workflow.model_factory import (
    StructuredOutputError,
    classify_llm_error,
    invoke_structured,
)

TRUNCATION_MESSAGE = (
    "Could not parse response content as the length limit was reached - "
    "CompletionUsage(completion_tokens=1800, prompt_tokens=10770, total_tokens=12570)"
)


def _fake_chain(*, raises: Exception | None = None, returns: dict | None = None) -> MagicMock:
    chain = MagicMock()
    if raises is not None:
        chain.ainvoke = AsyncMock(side_effect=raises)
    else:
        chain.ainvoke = AsyncMock(return_value=returns or {"ok": True})
    return chain


def _config() -> TextModelConfig:
    return TextModelConfig(api_key="k", base_url="https://example.com/v1", model="m")


def test_truncation_error_is_classified() -> None:
    assert classify_llm_error(RuntimeError(TRUNCATION_MESSAGE)) == "truncated"
    assert classify_llm_error(RuntimeError("connection reset")) == "other"


@pytest.mark.asyncio
async def test_successful_call_is_returned_unchanged() -> None:
    chain = _fake_chain(returns={"title": "ok"})

    with patch("workflow.model_factory.resolve_text_config", return_value=(_config(), "fast")):
        result = await invoke_structured(chain, {"a": 1}, stage="compose_draft")

    assert result == {"title": "ok"}
    assert chain.ainvoke.await_count == 1


@pytest.mark.asyncio
async def test_truncation_retries_once_with_a_larger_budget() -> None:
    chain = _fake_chain(raises=RuntimeError(TRUNCATION_MESSAGE))
    retry_chain = _fake_chain(returns={"title": "recovered"})
    budgets: list[int] = []

    def retry_factory(new_budget: int) -> MagicMock:
        budgets.append(new_budget)
        return retry_chain

    with patch("workflow.model_factory.resolve_text_config", return_value=(_config(), "fast")):
        result = await invoke_structured(
            chain,
            {"a": 1},
            stage="plan_article_angle",
            build_retry_chain=retry_factory,
        )

    base = runtime_settings.max_tokens_for("plan_article_angle")
    assert result == {"title": "recovered"}
    assert budgets == [int(base * runtime_settings.truncation_retry_factor())]
    assert budgets[0] > base


@pytest.mark.asyncio
async def test_persistent_truncation_raises_a_precise_error() -> None:
    chain = _fake_chain(raises=RuntimeError(TRUNCATION_MESSAGE))
    retry_chain = _fake_chain(raises=RuntimeError(TRUNCATION_MESSAGE))

    with patch("workflow.model_factory.resolve_text_config", return_value=(_config(), "fast")):
        with pytest.raises(StructuredOutputError) as excinfo:
            await invoke_structured(
                chain,
                {"a": 1},
                stage="compose_draft",
                build_retry_chain=lambda budget: retry_chain,
            )

    assert excinfo.value.reason == "truncated"
    assert excinfo.value.stage == "compose_draft"
    assert excinfo.value.max_tokens


@pytest.mark.asyncio
async def test_retry_can_be_disabled_by_configuration() -> None:
    chain = _fake_chain(raises=RuntimeError(TRUNCATION_MESSAGE))
    called = False

    def retry_factory(budget: int) -> MagicMock:  # pragma: no cover - must not run
        nonlocal called
        called = True
        return _fake_chain()

    with patch("workflow.model_factory.resolve_text_config", return_value=(_config(), "fast")):
        with patch.dict("os.environ", {"LLM_TRUNCATION_RETRY_FACTOR": "1"}):
            with pytest.raises(StructuredOutputError):
                await invoke_structured(
                    chain,
                    {"a": 1},
                    stage="compose_draft",
                    build_retry_chain=retry_factory,
                )

    assert called is False


@pytest.mark.asyncio
async def test_non_truncation_errors_are_not_retried() -> None:
    chain = _fake_chain(raises=RuntimeError("connection reset by peer"))

    with patch("workflow.model_factory.resolve_text_config", return_value=(_config(), "fast")):
        with pytest.raises(StructuredOutputError) as excinfo:
            await invoke_structured(
                chain,
                {"a": 1},
                stage="compose_draft",
                build_retry_chain=lambda budget: _fake_chain(),
            )

    assert excinfo.value.reason == "other"
    assert chain.ainvoke.await_count == 1


@pytest.mark.asyncio
async def test_stages_record_a_degraded_reason_when_the_model_is_absent() -> None:
    """A fallback must be visible downstream, not just a log line."""
    from workflow.agents.writer import compose_draft_node

    state = {
        "task_id": "task-1",
        "keywords": "机器人融资潮",
        "task_brief": {"topic": "机器人融资潮"},
        "planning_state": {"article_type": {}, "article_blueprint": {}},
        "research_state": {"evidence_pack": {}},
        "config_snapshot": {"content_template": {"article_length": "short"}},
        "writing_state": {},
    }

    with patch("workflow.nodes.plan_article_angle.structured_chain", return_value=(None, None)):
        with patch("workflow.agents.writer.structured_chain", return_value=(None, None)):
            result = await compose_draft_node(state)

    assert result["writing_state"]["draft_generation_mode"] == "fallback"
    assert result["writing_state"]["draft_degraded_reason"] == "no_model_configured"
