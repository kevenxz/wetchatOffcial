from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, patch

import httpx
import pytest

try:
    import markdown  # noqa: F401
except ModuleNotFoundError:
    sys.modules["markdown"] = types.SimpleNamespace(markdown=lambda text, **kwargs: text)

try:
    import structlog  # noqa: F401
except ModuleNotFoundError:
    class _NoopLogger:
        def info(self, *args, **kwargs) -> None:
            return None

        def warning(self, *args, **kwargs) -> None:
            return None

        def error(self, *args, **kwargs) -> None:
            return None

    sys.modules["structlog"] = types.SimpleNamespace(get_logger=lambda *args, **kwargs: _NoopLogger())

from workflow.utils.wechat_draft_service import _access_token_cache, push_article_to_wechat_draft


class _FakeAsyncClient:
    instances: list["_FakeAsyncClient"] = []

    def __init__(self, *args, **kwargs) -> None:
        self.post_calls: list[dict] = []
        _FakeAsyncClient.instances.append(self)

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def get(self, url: str, *args, **kwargs) -> httpx.Response:
        request = httpx.Request("GET", url)
        return httpx.Response(
            200,
            json={"access_token": "token-123", "expires_in": 7200},
            request=request,
        )

    async def post(self, url: str, *args, **kwargs) -> httpx.Response:
        payload = kwargs.get("json")
        self.post_calls.append({"url": url, "json": payload})

        request = httpx.Request("POST", url)
        if "draft/add" not in url:
            return httpx.Response(200, json={}, request=request)

        thumb_media_id = ((payload or {}).get("articles") or [{}])[0].get("thumb_media_id")
        if not thumb_media_id:
            return httpx.Response(
                200,
                json={"errcode": 40007, "errmsg": "invalid media_id"},
                request=request,
            )

        return httpx.Response(200, json={"media_id": "draft_media_ok"}, request=request)


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    _access_token_cache.clear()
    _FakeAsyncClient.instances.clear()


@pytest.mark.asyncio
async def test_push_article_to_wechat_draft_falls_back_to_illustration_cover() -> None:
    article = {
        "title": "title",
        "content": "content",
        "cover_image": "https://example.com/invalid-cover.png",
        "illustrations": [
            "https://example.com/illustration-1.png",
            "https://example.com/illustration-2.png",
        ],
    }

    with patch("workflow.utils.wechat_draft_service.httpx.AsyncClient", new=_FakeAsyncClient):
        with patch("workflow.utils.wechat_draft_service.markdown_to_wechat_html", return_value="<p>ok</p>"):
            with patch(
                "workflow.utils.wechat_draft_service.upload_cover_material",
                new_callable=AsyncMock,
            ) as mock_upload_cover:
                mock_upload_cover.side_effect = ["", "cover_media_from_illustration"]
                with patch(
                    "workflow.utils.wechat_draft_service.upload_article_image",
                    new_callable=AsyncMock,
                    return_value="https://mmbiz.qpic.cn/demo.png",
                ):
                    result = await push_article_to_wechat_draft(
                        article=article,
                        app_id="appid",
                        app_secret="secret",
                    )

    assert result["media_id"] == "draft_media_ok"
    assert mock_upload_cover.await_count == 2
    first_call_ref = mock_upload_cover.await_args_list[0].args[1]
    second_call_ref = mock_upload_cover.await_args_list[1].args[1]
    assert first_call_ref == "https://example.com/invalid-cover.png"
    assert second_call_ref == "https://example.com/illustration-1.png"

    client = _FakeAsyncClient.instances[0]
    assert client.post_calls
    draft_payload = client.post_calls[-1]["json"]
    assert draft_payload["articles"][0]["thumb_media_id"] == "cover_media_from_illustration"


@pytest.mark.asyncio
async def test_push_article_to_wechat_draft_raises_when_no_valid_cover_media_id() -> None:
    article = {
        "title": "title",
        "content": "content",
        "illustrations": [],
    }

    with patch("workflow.utils.wechat_draft_service.httpx.AsyncClient", new=_FakeAsyncClient):
        with patch("workflow.utils.wechat_draft_service.markdown_to_wechat_html", return_value="<p>ok</p>"):
            with patch(
                "workflow.utils.wechat_draft_service.upload_cover_material",
                new_callable=AsyncMock,
                return_value="",
            ) as mock_upload_cover:
                with patch(
                    "workflow.utils.wechat_draft_service.upload_article_image",
                    new_callable=AsyncMock,
                    return_value="",
                ):
                    with pytest.raises(ValueError, match="thumb_media_id"):
                        await push_article_to_wechat_draft(
                            article=article,
                            app_id="appid",
                            app_secret="secret",
                        )

    assert mock_upload_cover.await_count == 0
    client = _FakeAsyncClient.instances[0]
    assert all("draft/add" not in call["url"] for call in client.post_calls)


@pytest.mark.asyncio
async def test_push_article_to_wechat_draft_falls_back_to_visual_assets() -> None:
    article = {
        "title": "title",
        "content": "content",
        "visual_assets": [
            {"role": "cover", "url": "https://example.com/cover-from-assets.png"},
            {"role": "infographic", "url": "https://example.com/infographic-from-assets.png"},
        ],
    }

    with patch("workflow.utils.wechat_draft_service.httpx.AsyncClient", new=_FakeAsyncClient):
        with patch("workflow.utils.wechat_draft_service.markdown_to_wechat_html", return_value="<p>ok</p>"):
            with patch(
                "workflow.utils.wechat_draft_service.upload_cover_material",
                new_callable=AsyncMock,
                return_value="cover_media_from_assets",
            ) as mock_upload_cover:
                with patch(
                    "workflow.utils.wechat_draft_service.upload_article_image",
                    new_callable=AsyncMock,
                    return_value="https://mmbiz.qpic.cn/asset.png",
                ) as mock_upload_article:
                    result = await push_article_to_wechat_draft(
                        article=article,
                        app_id="appid",
                        app_secret="secret",
                    )

    assert result["media_id"] == "draft_media_ok"
    assert mock_upload_cover.await_args.args[1] == "https://example.com/cover-from-assets.png"
    assert mock_upload_article.await_args.args[1] == "https://example.com/infographic-from-assets.png"
