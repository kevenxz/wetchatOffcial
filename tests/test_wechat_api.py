from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from workflow.utils.wechat_api import ARTICLE_ALLOWED_IMG_TYPES, _download_image


class _SuccessClient:
    def __init__(self, response: httpx.Response) -> None:
        self._response = response

    async def get(self, *args, **kwargs) -> httpx.Response:
        return self._response


class _SslFailClient:
    async def get(self, *args, **kwargs) -> httpx.Response:
        raise httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")


@pytest.mark.asyncio
async def test_download_image_success() -> None:
    request = httpx.Request("GET", "https://example.com/demo.png")
    response = httpx.Response(
        200,
        content=b"\x89PNG\r\n\x1a\nabc",
        headers={"Content-Type": "image/png"},
        request=request,
    )

    content, filename, content_type = await _download_image(
        _SuccessClient(response),
        "https://example.com/demo.png",
        ARTICLE_ALLOWED_IMG_TYPES,
    )

    assert content == b"\x89PNG\r\n\x1a\nabc"
    assert filename == "upload_img.png"
    assert content_type == "image/png"


@pytest.mark.asyncio
async def test_download_image_retries_without_ssl_verify_on_cert_failure() -> None:
    created_kwargs: list[dict] = []

    class _InsecureClient:
        def __init__(self, *args, **kwargs) -> None:
            created_kwargs.append(kwargs)

        async def __aenter__(self) -> "_InsecureClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, *args, **kwargs) -> httpx.Response:
            request = httpx.Request("GET", "https://example.com/demo.png")
            return httpx.Response(
                200,
                content=b"\x89PNG\r\n\x1a\nabc",
                headers={"Content-Type": "image/png"},
                request=request,
            )

    with patch("workflow.utils.wechat_api.httpx.AsyncClient", new=_InsecureClient):
        content, filename, content_type = await _download_image(
            _SslFailClient(),
            "https://example.com/demo.png",
            ARTICLE_ALLOWED_IMG_TYPES,
        )

    assert content == b"\x89PNG\r\n\x1a\nabc"
    assert filename == "upload_img.png"
    assert content_type == "image/png"
    assert created_kwargs
    assert created_kwargs[0]["verify"] is False


@pytest.mark.asyncio
async def test_download_image_does_not_retry_when_insecure_fallback_disabled() -> None:
    with patch.dict("os.environ", {"WECHAT_IMAGE_DOWNLOAD_INSECURE_SSL_FALLBACK": "false"}):
        content, filename, content_type = await _download_image(
            _SslFailClient(),
            "https://example.com/demo.png",
            ARTICLE_ALLOWED_IMG_TYPES,
        )

    assert content == b""
    assert filename == ""
    assert content_type == ""
