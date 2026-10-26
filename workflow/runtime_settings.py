"""Centralized runtime tuning knobs for the article generation chain.

All values are environment driven so that the single-machine 2C2G deployment can
trade latency against resource pressure without code changes.
"""
from __future__ import annotations

import asyncio
import os
import weakref

_DEFAULT_RESEARCH_CONCURRENCY = 4
_DEFAULT_IMAGE_CONCURRENCY = 2
_DEFAULT_LLM_CONCURRENCY = 3
_DEFAULT_LLM_TIMEOUT_SECONDS = 90.0
_DEFAULT_LLM_MAX_RETRIES = 1
_DEFAULT_SEARCH_CACHE_TTL_SECONDS = 21600
_DEFAULT_PLANNER_MODE = "rules"

# Per-stage structured-output token budgets.  A reasoning model spends its whole
# completion budget on hidden reasoning and then emits no parseable JSON, so these
# are sized for a non-reasoning model while still leaving room for the payload.
_DEFAULT_MAX_TOKENS = {
    "planner_agent": 1200,
    "plan_article_angle": 3000,
    "design_viral_strategy": 1200,
    "compose_draft": 4000,
    "compose_draft_revision": 2500,
    "review_article_draft": 1200,
    "review_viral_potential": 1200,
    "describe_visual": 1200,
}

_ENV_MAX_TOKENS = {
    "planner_agent": "LLM_MAX_TOKENS_PLANNER",
    "plan_article_angle": "LLM_MAX_TOKENS_BLUEPRINT",
    "design_viral_strategy": "LLM_MAX_TOKENS_STRATEGY",
    "compose_draft": "LLM_MAX_TOKENS_DRAFT",
    "compose_draft_revision": "LLM_MAX_TOKENS_DRAFT_REVISION",
    "review_article_draft": "LLM_MAX_TOKENS_REVIEW",
    "review_viral_potential": "LLM_MAX_TOKENS_REVIEW",
    "describe_visual": "LLM_MAX_TOKENS_VISUAL_SPEC",
}

PLANNER_MODES = {"rules", "llm", "auto"}
STRUCTURED_TIERS = {"fast", "strong"}


def _env_str(name: str, default: str) -> str:
    raw = (os.getenv(name) or "").strip()
    return raw or default


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, min(value, maximum))


def _env_float(name: str, default: float, *, minimum: float, maximum: float) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return max(minimum, min(value, maximum))


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def research_concurrency() -> int:
    """Concurrent research queries per workflow run."""
    return _env_int("RESEARCH_CONCURRENCY", _DEFAULT_RESEARCH_CONCURRENCY, minimum=1, maximum=8)


def image_concurrency() -> int:
    """Concurrent image generation calls per workflow run."""
    return _env_int("IMAGE_CONCURRENCY", _DEFAULT_IMAGE_CONCURRENCY, minimum=1, maximum=4)


def llm_concurrency() -> int:
    """Process-wide concurrent LLM call ceiling."""
    return _env_int("LLM_CONCURRENCY", _DEFAULT_LLM_CONCURRENCY, minimum=1, maximum=8)


def llm_timeout_seconds() -> float:
    """Per-request LLM timeout; prevents the SDK 600s default long tail."""
    return _env_float("LLM_TIMEOUT_SECONDS", _DEFAULT_LLM_TIMEOUT_SECONDS, minimum=10.0, maximum=600.0)


def llm_max_retries() -> int:
    """LLM retry budget; the SDK default of 2 amplifies latency spikes."""
    return _env_int("LLM_MAX_RETRIES", _DEFAULT_LLM_MAX_RETRIES, minimum=0, maximum=3)


def workflow_max_concurrency() -> int:
    """How many workflows may execute at the same time.

    Defaults to 2 so a 2C2G single-machine deployment cannot be saturated by
    concurrently running pipelines.
    """
    return _env_int("WORKFLOW_MAX_CONCURRENCY", 2, minimum=1, maximum=8)


def planner_mode() -> str:
    """Research-contract planning mode: rules | llm | auto."""
    mode = _env_str("PLANNER_MODE", _DEFAULT_PLANNER_MODE).lower()
    return mode if mode in PLANNER_MODES else _DEFAULT_PLANNER_MODE


def structured_tier() -> str:
    """Which model tier handles the structured-output stages: fast | strong.

    ``fast`` is the default: every stage in this pipeline asks for a structured
    payload, and a reasoning model spends its completion budget on hidden reasoning
    before emitting any JSON. Pointing these stages at a non-reasoning model (the
    ``text_fast`` tier) is what keeps structured output parseable.
    """
    tier = _env_str("LLM_STRUCTURED_TIER", "fast").lower()
    return tier if tier in STRUCTURED_TIERS else "fast"


def strong_stages() -> set[str]:
    """Stages pinned to the primary (possibly reasoning) model regardless of tier."""
    raw = (os.getenv("LLM_STRONG_STAGES") or "").strip()
    if not raw:
        return set()
    return {item.strip() for item in raw.split(",") if item.strip()}


def max_tokens_for(stage: str) -> int:
    """Structured-output token budget for one stage."""
    default = _DEFAULT_MAX_TOKENS.get(stage, 1200)
    env_name = _ENV_MAX_TOKENS.get(stage)
    if not env_name:
        return default
    return _env_int(env_name, default, minimum=128, maximum=32000)


# Stages whose budget should scale up hard when they land on a reasoning model. A
# reasoning model bills its hidden reasoning against the same completion budget, so a
# budget sized for plain JSON gets consumed before any JSON is emitted — which is what
# truncated the blueprint, the draft and the review in real runs.
REASONING_TOKEN_MULTIPLIER = 6


def budget_for_tier(stage: str, tier: str) -> int:
    """Token budget for a stage, widened when the stage runs on the ``strong`` tier.

    On the ``strong`` tier we cannot know whether the configured model is a reasoning
    model, and the failure mode is silent (truncated output -> deterministic template
    article), so the budget is scaled up defensively. Harmless for a non-reasoning
    model, decisive for a reasoning one.
    """
    budget = max_tokens_for(stage)
    if str(tier or "").lower() == "strong":
        return min(budget * REASONING_TOKEN_MULTIPLIER, 32000)
    return budget


def truncation_retry_factor() -> float:
    """Multiplier applied to the token budget when a structured call truncates.

    ``1`` disables the retry entirely; the default doubles the budget once, which
    is far cheaper than silently shipping a deterministic template article.
    """
    return _env_float("LLM_TRUNCATION_RETRY_FACTOR", 2.0, minimum=1.0, maximum=4.0)


def search_cache_enabled() -> bool:
    """Whether search results are cached in Redis."""
    return _env_bool("SEARCH_CACHE_ENABLED", True)


def search_cache_ttl_seconds() -> int:
    """Search result cache TTL in seconds."""
    return _env_int("SEARCH_CACHE_TTL_SECONDS", _DEFAULT_SEARCH_CACHE_TTL_SECONDS, minimum=0, maximum=604800)


# --------------------------------------------------------------------------- #
# Source filtering (searched and fetched pages)
# --------------------------------------------------------------------------- #


def source_min_chars() -> int:
    """Minimum extracted body length for a fetched page to be usable."""
    return _env_int("SOURCE_MIN_CHARS", 400, minimum=50, maximum=10000)


def source_official_min_chars() -> int:
    """Lower length floor for official/documentation sources.

    An official announcement or changelog can be terse but is still authoritative
    evidence, so it should not be discarded merely for being short.
    """
    return _env_int("SOURCE_OFFICIAL_MIN_CHARS", 150, minimum=50, maximum=10000)


def source_min_sentences() -> int:
    """Minimum sentence count, to reject navigation/boilerplate captures."""
    return _env_int("SOURCE_MIN_SENTENCES", 3, minimum=1, maximum=50)


def source_min_relevance() -> float:
    """Minimum topic-token overlap ratio between the topic and a page."""
    return _env_float("SOURCE_MIN_RELEVANCE", 0.12, minimum=0.0, maximum=1.0)


def source_near_duplicate_similarity() -> float:
    """Jaccard similarity above which two pages are treated as the same story."""
    return _env_float("SOURCE_NEAR_DUP_SIMILARITY", 0.85, minimum=0.5, maximum=1.0)


def source_max_per_domain() -> int:
    """Maximum kept sources per domain, to force source diversity."""
    return _env_int("SOURCE_MAX_PER_DOMAIN", 2, minimum=1, maximum=20)


def source_min_survivors() -> int:
    """Below this many surviving sources the task is flagged for human review."""
    return _env_int("SOURCE_MIN_SURVIVORS", 3, minimum=1, maximum=30)


def hotspot_source_enabled() -> bool:
    """Whether the hotspot's own source article is fetched before searching."""
    return _env_bool("HOTSPOT_SOURCE_ENABLED", True)


_semaphores: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, dict[str, asyncio.Semaphore]]" = (
    weakref.WeakKeyDictionary()
)


def get_semaphore(name: str, limit: int) -> asyncio.Semaphore:
    """Return a per-event-loop semaphore.

    Semaphores are cached per running loop so that concurrent workflows share one
    budget while independent test event loops stay isolated.
    """
    loop = asyncio.get_running_loop()
    bucket = _semaphores.get(loop)
    if bucket is None:
        bucket = {}
        _semaphores[loop] = bucket
    semaphore = bucket.get(name)
    if semaphore is None or getattr(semaphore, "_dsh_limit", None) != limit:
        semaphore = asyncio.Semaphore(limit)
        setattr(semaphore, "_dsh_limit", limit)
        bucket[name] = semaphore
    return semaphore
