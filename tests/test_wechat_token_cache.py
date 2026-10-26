"""Tests for the shared WeChat access-token cache."""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from workflow.utils import wechat_token
from workflow.utils.wechat_token import (
    _access_token_cache,
    get_access_token,
    invalidate_access_token,
    token_cache_key,
)


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    _access_token_cache.clear()
    wechat_token._access_token_cache.clear()


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.calls = 0

    async def get(self, url: str) -> _FakeResponse:
        self.calls += 1
        return _FakeResponse(self._payload)


@pytest.mark.asyncio
async def test_token_is_fetched_once_and_then_served_from_memory() -> None:
    client = _FakeClient({"access_token": "token-1", "expires_in": 7200})

    with patch.dict("os.environ", {"REDIS_URL": ""}, clear=False):
        first = await get_access_token("appid", "secret", client)  # type: ignore[arg-type]
        second = await get_access_token("appid", "secret", client)  # type: ignore[arg-type]

    assert first == "token-1"
    assert second == "token-1"
    assert client.calls == 1


@pytest.mark.asyncio
async def test_expired_memory_token_is_refreshed() -> None:
    _access_token_cache["appid"] = {"token": "stale", "expires_at": time.time() - 10}
    client = _FakeClient({"access_token": "fresh", "expires_in": 7200})

    with patch.dict("os.environ", {"REDIS_URL": ""}, clear=False):
        token = await get_access_token("appid", "secret", client)  # type: ignore[arg-type]

    assert token == "fresh"
    assert client.calls == 1


@pytest.mark.asyncio
async def test_redis_hit_avoids_a_provider_call() -> None:
    stored = f'{{"token": "shared-token", "expires_at": {time.time() + 3600}}}'

    class FakeRedis:
        async def get(self, key: str):
            assert key == token_cache_key("appid")
            return stored

    client = _FakeClient({"access_token": "should-not-be-used", "expires_in": 7200})

    with patch("workflow.utils.wechat_token.get_redis", new_callable=AsyncMock) as mock_get_redis:
        mock_get_redis.return_value = FakeRedis()
        token = await get_access_token("appid", "secret", client)  # type: ignore[arg-type]

    assert token == "shared-token"
    assert client.calls == 0
    # The shared token is also cached locally to avoid another Redis round trip.
    assert _access_token_cache["appid"]["token"] == "shared-token"


@pytest.mark.asyncio
async def test_fetched_token_is_written_through_to_redis() -> None:
    written: dict[str, str] = {}

    class FakeRedis:
        async def get(self, key: str):
            return None

        async def set(self, key: str, value: str, ex: int | None = None):
            written[key] = value

    client = _FakeClient({"access_token": "new-token", "expires_in": 7200})

    with patch("workflow.utils.wechat_token.get_redis", new_callable=AsyncMock) as mock_get_redis:
        mock_get_redis.return_value = FakeRedis()
        token = await get_access_token("appid", "secret", client)  # type: ignore[arg-type]

    assert token == "new-token"
    assert token_cache_key("appid") in written


@pytest.mark.asyncio
async def test_redis_failure_degrades_to_memory_without_raising() -> None:
    class BrokenRedis:
        async def get(self, key: str):
            raise RuntimeError("connection reset")

    client = _FakeClient({"access_token": "fallback-token", "expires_in": 7200})

    with patch("workflow.utils.wechat_token.get_redis", new_callable=AsyncMock) as mock_get_redis:
        mock_get_redis.return_value = BrokenRedis()
        token = await get_access_token("appid", "secret", client)  # type: ignore[arg-type]

    assert token == "fallback-token"


@pytest.mark.asyncio
async def test_invalidate_clears_memory_and_redis() -> None:
    _access_token_cache["appid"] = {"token": "stale", "expires_at": time.time() + 3600}
    deleted: list[str] = []

    class FakeRedis:
        async def delete(self, key: str):
            deleted.append(key)

    with patch("workflow.utils.wechat_token.get_redis", new_callable=AsyncMock) as mock_get_redis:
        mock_get_redis.return_value = FakeRedis()
        await invalidate_access_token("appid")

    assert "appid" not in _access_token_cache
    assert deleted == [token_cache_key("appid")]


@pytest.mark.asyncio
async def test_missing_access_token_in_payload_raises() -> None:
    client = _FakeClient({"errcode": 40013, "errmsg": "invalid appid"})

    with patch.dict("os.environ", {"REDIS_URL": ""}, clear=False):
        with pytest.raises(ValueError, match="failed to get access token"):
            await get_access_token("appid", "secret", client)  # type: ignore[arg-type]
