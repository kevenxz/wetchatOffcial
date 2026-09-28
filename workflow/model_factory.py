"""Centralized chat-model construction for every workflow LLM call.

Responsibilities:
- Route each stage to the strong or fast text model.
- Apply a bounded request timeout and retry budget so a stalled provider call
  cannot hold a workflow for the SDK default of 600 seconds.
- Serialize concurrent calls through a process-wide semaphore.
- Provide a uniform structured-logging context.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from typing import Any

from langchain_openai import ChatOpenAI

from api.models import TextModelConfig
from api.store import get_model_config
from workflow import runtime_settings
from workflow.model_logging import build_model_context

# Stages that shape the final artifact and therefore deserve the strong model.
STRONG_STAGES = frozenset({"plan_article_angle", "compose_draft"})

# Stages that produce bounded structured output and tolerate a faster model.
FAST_STAGES = frozenset(
    {
        "planner_agent",
        "design_viral_strategy",
        "review_article_draft",
        "review_viral_potential",
    }
)


def resolve_text_config(stage: str) -> tuple[TextModelConfig, str]:
    """Return the text model config and tier for one workflow stage.

    Falls back to the primary text model whenever the fast model is not
    configured, so existing installations keep working unchanged.
    """
    config = get_model_config()
    if stage in FAST_STAGES:
        fast_config = getattr(config, "text_fast", None)
        fast_key = getattr(fast_config, "api_key", "") if fast_config is not None else ""
        # Only a real, non-empty string key enables the fast tier; this keeps the
        # fallback explicit and avoids routing on unexpected config shapes.
        if isinstance(fast_key, str) and fast_key.strip():
            return fast_config, "fast"
    return config.text, "strong"


def build_chat_model(
    *,
    stage: str,
    max_tokens: int | None = None,
    temperature: float = 0.2,
) -> ChatOpenAI | None:
    """Build a chat model for one stage, or ``None`` when no key is configured."""
    text_config, _tier = resolve_text_config(stage)
    if not text_config.api_key:
        return None

    kwargs: dict[str, Any] = {
        "model": text_config.model,
        "api_key": text_config.api_key,
        "base_url": text_config.base_url or None,
        "temperature": temperature,
        "timeout": runtime_settings.llm_timeout_seconds(),
        "max_retries": runtime_settings.llm_max_retries(),
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    return ChatOpenAI(**kwargs)


def model_context(stage: str, *, structured_output: str | None = None) -> dict[str, Any]:
    """Build the structured-logging context for one stage."""
    text_config, tier = resolve_text_config(stage)
    return build_model_context(
        model=text_config.model,
        base_url=text_config.base_url,
        api_key=text_config.api_key,
        model_tier=tier,
        stage=stage,
        **({"structured_output": structured_output} if structured_output else {}),
    )


@asynccontextmanager
async def llm_slot() -> AsyncIterator[None]:
    """Bound concurrent LLM calls to protect the provider quota and memory."""
    semaphore = runtime_settings.get_semaphore("llm", runtime_settings.llm_concurrency())
    async with semaphore:
        yield
