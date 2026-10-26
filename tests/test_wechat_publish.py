"""Tests for WeChat draft publishing."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from workflow.utils.wechat_draft_service import push_article_to_wechat_draft
from workflow.utils.wechat_publish import (
    WeChatPublishError,
    poll_publish_status,
    publish_failure_reason,
    submit_publish,
)


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    """Returns queued responses in order for both GET and POST."""

    def __init__(self, *, posts: list[dict] | None = None, gets: list[dict] | None = None) -> None:
        self._posts = list(posts or [])
        self._gets = list(gets or [])
        self.post_calls: list[dict] = []

    async def post(self, url: str, json: dict | None = None, **kwargs) -> _FakeResponse:
        self.post_calls.append({"url": url, "json": json})
        return _FakeResponse(self._posts.pop(0) if self._posts else {})

    async def get(self, url: str, **kwargs) -> _FakeResponse:
        return _FakeResponse(self._gets.pop(0) if self._gets else {})


@pytest.mark.asyncio
async def test_submit_publish_returns_publish_id() -> None:
    client = _FakeClient(posts=[{"media_id": "draft-1", "publish_id": "publish-1"}])

    publish_id = await submit_publish(client, "token", "draft-1")  # type: ignore[arg-type]

    assert publish_id == "publish-1"
    assert client.post_calls[0]["json"] == {"media_id": "draft-1"}


@pytest.mark.asyncio
async def test_submit_publish_flags_an_expired_token() -> None:
    client = _FakeClient(posts=[{"errcode": 40001, "errmsg": "invalid credential"}])

    with pytest.raises(WeChatPublishError) as excinfo:
        await submit_publish(client, "token", "draft-1")  # type: ignore[arg-type]

    assert excinfo.value.token_expired is True
    assert excinfo.value.errcode == 40001


@pytest.mark.asyncio
async def test_submit_publish_rejects_a_missing_publish_id() -> None:
    client = _FakeClient(posts=[{"errcode": 0}])

    with pytest.raises(WeChatPublishError, match="missing publish_id"):
        await submit_publish(client, "token", "draft-1")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_poll_returns_published_on_success_status() -> None:
    client = _FakeClient(posts=[{"errcode": 0, "publish_status": 0}])

    with patch("workflow.utils.wechat_publish.asyncio.sleep", new_callable=AsyncMock):
        result = await poll_publish_status(client, "token", "publish-1", interval_seconds=0)  # type: ignore[arg-type]

    assert result["published"] is True
    assert result["status"] == 0


@pytest.mark.asyncio
async def test_poll_reports_a_terminal_failure_without_waiting() -> None:
    client = _FakeClient(posts=[{"errcode": 0, "publish_status": 3}])

    with patch("workflow.utils.wechat_publish.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await poll_publish_status(client, "token", "publish-1")  # type: ignore[arg-type]

    assert result["published"] is False
    assert result["status"] == 3
    mock_sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_poll_times_out_while_still_publishing() -> None:
    client = _FakeClient(posts=[{"errcode": 0, "publish_status": 1} for _ in range(3)])

    with patch("workflow.utils.wechat_publish.asyncio.sleep", new_callable=AsyncMock):
        result = await poll_publish_status(client, "token", "publish-1", interval_seconds=0, max_attempts=3)  # type: ignore[arg-type]

    assert result["published"] is False
    assert result["timed_out"] is True


def test_publish_failure_reason_is_operator_readable() -> None:
    assert "审核" in publish_failure_reason(4)
    assert "未知" in publish_failure_reason(None)


@pytest.mark.asyncio
async def test_draft_push_stops_at_draft_by_default() -> None:
    """Without the auto_publish switch no publish call may be made."""
    with patch("workflow.utils.wechat_draft_service.httpx.AsyncClient") as mock_client_cls:
        client = mock_client_cls.return_value.__aenter__.return_value
        client.get = AsyncMock(return_value=_FakeResponse({"access_token": "token", "expires_in": 7200}))
        client.post = AsyncMock(return_value=_FakeResponse({"media_id": "draft-1"}))

        with patch(
            "workflow.utils.wechat_draft_service.upload_cover_material",
            new_callable=AsyncMock,
            return_value="thumb-1",
        ):
            with patch("workflow.utils.wechat_draft_service.markdown_to_wechat_html", return_value="<p>ok</p>"):
                result = await push_article_to_wechat_draft(
                    article={"title": "t", "content": "c", "cover_image": "https://example.com/c.png"},
                    app_id="appid",
                    app_secret="secret",
                )

    assert result["media_id"] == "draft-1"
    assert result["publish_status"] == "draft_only"
    # Only the draft endpoint was called.
    assert all("draft/add" in call.args[0] for call in client.post.await_args_list)


@pytest.mark.asyncio
async def test_auto_publish_submits_and_reports_published() -> None:
    with patch("workflow.utils.wechat_draft_service.httpx.AsyncClient") as mock_client_cls:
        client = mock_client_cls.return_value.__aenter__.return_value
        client.get = AsyncMock(return_value=_FakeResponse({"access_token": "token", "expires_in": 7200}))
        client.post = AsyncMock(
            side_effect=[
                _FakeResponse({"media_id": "draft-1"}),
                _FakeResponse({"publish_id": "publish-1"}),
                _FakeResponse({"publish_status": 0}),
            ]
        )

        with patch(
            "workflow.utils.wechat_draft_service.upload_cover_material",
            new_callable=AsyncMock,
            return_value="thumb-1",
        ):
            with patch("workflow.utils.wechat_draft_service.markdown_to_wechat_html", return_value="<p>ok</p>"):
                with patch("workflow.utils.wechat_publish.asyncio.sleep", new_callable=AsyncMock):
                    result = await push_article_to_wechat_draft(
                        article={"title": "t", "content": "c", "cover_image": "https://example.com/c.png"},
                        app_id="appid",
                        app_secret="secret",
                        auto_publish=True,
                        publish_poll_interval_seconds=0,
                    )

    assert result["media_id"] == "draft-1"
    assert result["publish_id"] == "publish-1"
    assert result["publish_status"] == "published"


@pytest.mark.asyncio
async def test_publish_failure_keeps_the_draft_result() -> None:
    """A publish failure must not discard the successfully created draft."""
    with patch("workflow.utils.wechat_draft_service.httpx.AsyncClient") as mock_client_cls:
        client = mock_client_cls.return_value.__aenter__.return_value
        client.get = AsyncMock(return_value=_FakeResponse({"access_token": "token", "expires_in": 7200}))
        client.post = AsyncMock(
            side_effect=[
                _FakeResponse({"media_id": "draft-1"}),
                _FakeResponse({"errcode": 45009, "errmsg": "reach max api daily quota"}),
            ]
        )

        with patch(
            "workflow.utils.wechat_draft_service.upload_cover_material",
            new_callable=AsyncMock,
            return_value="thumb-1",
        ):
            with patch("workflow.utils.wechat_draft_service.markdown_to_wechat_html", return_value="<p>ok</p>"):
                result = await push_article_to_wechat_draft(
                    article={"title": "t", "content": "c", "cover_image": "https://example.com/c.png"},
                    app_id="appid",
                    app_secret="secret",
                    auto_publish=True,
                )

    assert result["media_id"] == "draft-1"
    assert result["publish_status"] == "publish_failed"
    assert result["publish_error"]
