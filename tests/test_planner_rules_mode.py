"""Tests for planner mode gating and the search cache."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from workflow import runtime_settings
from workflow.utils.search_cache import cache_key, get_cached_search, set_cached_search


@pytest.mark.asyncio
async def test_planner_rules_mode_skips_the_llm() -> None:
    with patch.dict("os.environ", {"PLANNER_MODE": "rules"}, clear=False):
        with patch("workflow.agents.planner._build_ai_search_contract", new_callable=AsyncMock) as mock_ai:
            from workflow.agents.planner import planner_agent_node

            result = await planner_agent_node(
                {
                    "task_id": "task-planner",
                    "keywords": "机器人融资",
                    "task_brief": {"topic": "机器人融资"},
                    "config_snapshot": {"generation": {}},
                }
            )

    mock_ai.assert_not_called()
    contract = result["planning_state"]["search_contract"]
    # The deterministic contract still carries every field downstream nodes need.
    assert contract["query_plan"]
    assert contract["category"]
    assert contract["search_depth"]
    assert contract["planner_source"] == "fallback_rules"


@pytest.mark.asyncio
async def test_planner_auto_mode_escalates_for_strict_depth() -> None:
    with patch.dict("os.environ", {"PLANNER_MODE": "auto"}, clear=False):
        with patch("workflow.agents.planner._build_ai_search_contract", new_callable=AsyncMock) as mock_ai:
            mock_ai.return_value = None
            from workflow.agents.planner import planner_agent_node

            # A finance topic escalates to strict depth under the rule engine.
            await planner_agent_node(
                {
                    "task_id": "task-planner-strict",
                    "keywords": "上市公司财报与股价",
                    "task_brief": {"topic": "上市公司财报与股价"},
                    "config_snapshot": {"generation": {}},
                }
            )

    mock_ai.assert_awaited()


def test_planner_mode_defaults_to_rules_and_ignores_invalid_values() -> None:
    with patch.dict("os.environ", {}, clear=False):
        assert runtime_settings.planner_mode() == "rules"
    with patch.dict("os.environ", {"PLANNER_MODE": "nonsense"}, clear=False):
        assert runtime_settings.planner_mode() == "rules"


def test_cache_key_is_stable_and_normalizes_query_case() -> None:
    assert cache_key("serpapi_google", "AI 芯片", 6) == cache_key("serpapi_google", "  ai 芯片 ", 6)
    assert cache_key("serpapi_google", "AI 芯片", 6) != cache_key("bing", "AI 芯片", 6)


@pytest.mark.asyncio
async def test_cache_is_a_noop_without_redis() -> None:
    with patch.dict("os.environ", {"REDIS_URL": ""}, clear=False):
        assert await get_cached_search("serpapi_google", "q", 6) is None
        # Must not raise even though there is nowhere to write.
        await set_cached_search("serpapi_google", "q", 6, [{"url": "https://example.com"}])


@pytest.mark.asyncio
async def test_cache_round_trip_through_a_fake_client() -> None:
    store: dict[str, str] = {}

    class FakeRedis:
        async def get(self, key: str):
            return store.get(key)

        async def set(self, key: str, value: str, ex: int | None = None):
            store[key] = value

    with patch.dict("os.environ", {"REDIS_URL": "redis://localhost:6379/0", "SEARCH_CACHE_ENABLED": "true"}, clear=False):
        with patch("workflow.utils.search_cache.get_redis", new_callable=AsyncMock) as mock_get_redis:
            mock_get_redis.return_value = FakeRedis()

            await set_cached_search("serpapi_google", "query", 6, [{"url": "https://example.com"}])
            cached = await get_cached_search("serpapi_google", "query", 6)

    assert cached == [{"url": "https://example.com"}]


@pytest.mark.asyncio
async def test_cache_can_be_disabled_by_env() -> None:
    with patch.dict("os.environ", {"SEARCH_CACHE_ENABLED": "false"}, clear=False):
        with patch("workflow.utils.search_cache.get_redis", new_callable=AsyncMock) as mock_get_redis:
            assert await get_cached_search("serpapi_google", "query", 6) is None

    mock_get_redis.assert_not_awaited()
