"""Centralized chat-model construction for every workflow LLM call.

Responsibilities:
- Route each stage to the model tier that suits it (see :func:`resolve_text_config`).
- Apply a bounded request timeout and retry budget so a stalled provider call
  cannot hold a workflow for the SDK default of 600 seconds.
- Detect truncated structured output and report it loudly instead of letting every
  stage silently degrade to a deterministic template.
- Serialize concurrent calls through a process-wide semaphore.
- Provide a uniform structured-logging context.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from langchain_openai import ChatOpenAI

from api.models import TextModelConfig
from api.store import get_model_config
from workflow import runtime_settings
from workflow.model_logging import build_model_context

logger = structlog.get_logger(__name__)

# Every stage in this pipeline requests a structured (schema-validated) payload.
STRUCTURED_STAGES = frozenset(
    {
        "planner_agent",
        "plan_article_angle",
        "design_viral_strategy",
        "compose_draft",
        "review_article_draft",
        "review_viral_potential",
        "describe_visual",
    }
)

# Markers that identify a response cut off by the completion-token limit.
_TRUNCATION_MARKERS = (
    "length limit was reached",
    "finish_reason",
    "max_tokens",
    "maximum context length",
)


class StructuredOutputError(RuntimeError):
    """A structured-output call failed.

    ``reason`` is ``truncated`` when the model ran out of completion budget, which
    on a reasoning model means the hidden reasoning consumed the whole allowance
    before any JSON was emitted.
    """

    def __init__(
        self,
        message: str,
        *,
        stage: str,
        reason: str,
        model: str = "",
        max_tokens: int | None = None,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.reason = reason
        self.model = model
        self.max_tokens = max_tokens


def classify_llm_error(exc: Exception) -> str:
    """Classify a structured-output failure as ``truncated`` or ``other``."""
    message = str(exc).lower()
    if any(marker in message for marker in _TRUNCATION_MARKERS):
        return "truncated"
    return "other"


def _has_usable_key(config: Any) -> bool:
    """Only a real, non-empty string key counts as configured."""
    key = getattr(config, "api_key", "") if config is not None else ""
    return isinstance(key, str) and bool(key.strip())


def resolve_text_config(stage: str) -> tuple[TextModelConfig, str]:
    """Return the text model config and tier for one workflow stage.

    Structured-output stages default to the ``text_fast`` tier, which is meant to
    hold a **non-reasoning** model: a reasoning model spends its completion budget
    on hidden reasoning and returns no parseable JSON. Set ``LLM_STRUCTURED_TIER``
    to ``strong`` to route them back to the primary model, or pin individual stages
    with ``LLM_STRONG_STAGES``.

    Falls back to the primary model whenever the fast tier is not configured, so
    existing installations keep working unchanged.
    """
    config = get_model_config()
    want_fast = (
        stage in STRUCTURED_STAGES
        and runtime_settings.structured_tier() == "fast"
        and stage not in runtime_settings.strong_stages()
    )
    if want_fast:
        fast_config = getattr(config, "text_fast", None)
        if _has_usable_key(fast_config):
            return fast_config, "fast"
    return config.text, "strong"


def build_chat_model(
    *,
    stage: str,
    max_tokens: int | None = None,
    temperature: float = 0.2,
) -> ChatOpenAI | None:
    """Build a chat model for one stage, or ``None`` when no key is configured."""
    stage_config, _tier = resolve_text_config(stage)
    if not stage_config.api_key:
        return None

    kwargs: dict[str, Any] = {
        "model": stage_config.model,
        "api_key": stage_config.api_key,
        "base_url": stage_config.base_url or None,
        "temperature": temperature,
        "timeout": runtime_settings.llm_timeout_seconds(),
        "max_retries": runtime_settings.llm_max_retries(),
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    return ChatOpenAI(**kwargs)


def model_context(stage: str, *, structured_output: str | None = None) -> dict[str, Any]:
    """Build the structured-logging context for one stage."""
    stage_config, tier = resolve_text_config(stage)
    return build_model_context(
        model=stage_config.model,
        base_url=stage_config.base_url,
        api_key=stage_config.api_key,
        model_tier=tier,
        stage=stage,
        **({"structured_output": structured_output} if structured_output else {}),
    )


def effective_routing() -> list[dict[str, Any]]:
    """Describe the resolved model and budget for every structured stage.

    Exposed through the API so a misrouted tier (for example a reasoning model on
    the structured stages) is visible instead of only surfacing as an article that
    quietly looks templated.
    """
    config = get_model_config()
    rows: list[dict[str, Any]] = []
    for stage in sorted(STRUCTURED_STAGES):
        stage_config, tier = resolve_text_config(stage)
        rows.append(
            {
                "stage": stage,
                "tier": tier,
                "model": str(getattr(stage_config, "model", "") or ""),
                "base_url": str(getattr(stage_config, "base_url", "") or ""),
                "max_tokens": runtime_settings.max_tokens_for(stage),
                "key_configured": _has_usable_key(stage_config),
                "fast_tier_configured": _has_usable_key(getattr(config, "text_fast", None)),
            }
        )
    return rows


@asynccontextmanager
async def llm_slot() -> AsyncIterator[None]:
    """Bound concurrent LLM calls to protect the provider quota and memory."""
    semaphore = runtime_settings.get_semaphore("llm", runtime_settings.llm_concurrency())
    async with semaphore:
        yield


def structured_chain(
    prompt: Any,
    *,
    stage: str,
    schema: Any,
    temperature: float = 0.2,
    max_tokens: int | None = None,
) -> tuple[Any | None, Any | None]:
    """Build a ``prompt | llm.with_structured_output(schema)`` chain for a stage.

    Returns ``(chain, retry_factory)``. ``chain`` is ``None`` when no API key is
    configured, so callers keep their existing "no model" fallback. ``retry_factory``
    rebuilds the chain with a larger token budget for the truncation retry.

    When no explicit ``max_tokens`` is given the budget is widened for the ``strong``
    tier, because a reasoning model spends its completion budget on hidden reasoning
    before emitting any JSON — the cause of the truncated blueprints and drafts.
    """
    if max_tokens is None:
        _stage_config, tier = resolve_text_config(stage)
        budget = runtime_settings.budget_for_tier(stage, tier)
    else:
        budget = max_tokens
    llm = build_chat_model(stage=stage, max_tokens=budget, temperature=temperature)
    if llm is None:
        return None, None

    chain = prompt | llm.with_structured_output(schema)

    def retry_factory(new_budget: int) -> Any:
        retry_llm = build_chat_model(stage=stage, max_tokens=new_budget, temperature=temperature)
        return prompt | retry_llm.with_structured_output(schema)

    return chain, retry_factory


async def invoke_structured(
    chain: Any,
    payload: dict[str, Any],
    *,
    stage: str,
    build_retry_chain: Any = None,
) -> Any:
    """Invoke a structured-output chain, retrying once when the output truncates.

    Raises :class:`StructuredOutputError` (never a bare parser error) so callers can
    record a precise degraded reason instead of silently producing a template.

    ``build_retry_chain`` is optional: when supplied it is called with the enlarged
    token budget and must return a new chain to retry against.
    """
    stage_config, tier = resolve_text_config(stage)
    budget = runtime_settings.budget_for_tier(stage, tier)

    try:
        async with llm_slot():
            return await chain.ainvoke(payload)
    except Exception as exc:  # noqa: BLE001
        reason = classify_llm_error(exc)
        if reason != "truncated":
            raise StructuredOutputError(
                str(exc),
                stage=stage,
                reason=reason,
                model=str(getattr(stage_config, "model", "") or ""),
                max_tokens=budget,
            ) from exc

        factor = runtime_settings.truncation_retry_factor()
        retry_budget = int(budget * factor)
        logger.warning(
            "llm_structured_truncated",
            stage=stage,
            model=getattr(stage_config, "model", ""),
            model_tier=tier,
            max_tokens=budget,
            retry_budget=retry_budget if factor > 1 else None,
            error=str(exc)[:400],
            exc_info=True,
        )

        if factor <= 1 or build_retry_chain is None:
            raise StructuredOutputError(
                str(exc),
                stage=stage,
                reason="truncated",
                model=str(getattr(stage_config, "model", "") or ""),
                max_tokens=budget,
            ) from exc

        try:
            retry_chain = build_retry_chain(retry_budget)
            async with llm_slot():
                result = await retry_chain.ainvoke(payload)
        except Exception as retry_exc:  # noqa: BLE001
            raise StructuredOutputError(
                str(retry_exc),
                stage=stage,
                reason=classify_llm_error(retry_exc),
                model=str(getattr(stage_config, "model", "") or ""),
                max_tokens=retry_budget,
            ) from retry_exc

        logger.info(
            "llm_structured_truncation_recovered",
            stage=stage,
            model=getattr(stage_config, "model", ""),
            retry_budget=retry_budget,
            exc_info=True,
        )
        return result
