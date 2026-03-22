"""Helpers for downloading and uploading images to WeChat APIs."""
from __future__ import annotations

import mimetypes
import os
import ssl
from urllib.parse import urlparse

import httpx
import structlog

logger = structlog.get_logger(__name__)

ARTICLE_ALLOWED_IMG_TYPES = {"image/jpeg", "image/png", "image/gif"}
COVER_ALLOWED_IMG_TYPES = {"image/jpeg", "image/png", "image/gif"}
INSECURE_SSL_FALLBACK_ENV = "WECHAT_IMAGE_DOWNLOAD_INSECURE_SSL_FALLBACK"


def _detect_image_mime(content: bytes, content_type_header: str, img_url: str) -> str:
    """Infer the real image mime type from header, URL suffix, and file signature."""
    content_type = content_type_header.lower().split(";")[0].strip()
    if content_type:
        return content_type

    guessed, _ = mimetypes.guess_type(urlparse(img_url).path)
    if guessed:
        return guessed

    head = content[:64]
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if head.startswith(b"RIFF") and b"WEBP" in content[:16]:
        return "image/webp"

    text_head = content[:256].lstrip().lower()
    if text_head.startswith(b"<?xml") or text_head.startswith(b"<svg") or b"<svg" in text_head:
        return "image/svg+xml"

    return ""


def _is_enabled(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _should_retry_without_ssl_verify() -> bool:
    return _is_enabled(os.getenv(INSECURE_SSL_FALLBACK_ENV), default=True)


def _is_ssl_verification_error(exc: Exception) -> bool:
    current: BaseException | None = exc
    while current is not None:
        if isinstance(current, ssl.SSLCertVerificationError):
            return True

        message = str(current).lower()
        if "certificate verify failed" in message or "certificate_verify_failed" in message:
            return True

        current = current.__cause__ or current.__context__
    return False


def _normalize_image_response(
    resp: httpx.Response,
    img_url: str,
    allowed_types: set[str],
) -> tuple[bytes, str, str]:
    content = resp.content
    content_type = _detect_image_mime(content, resp.headers.get("Content-Type", ""), img_url)

    if content_type == "image/svg+xml":
        logger.warning("skip_unsupported_svg_image", url=img_url)
        return b"", "", ""

    if content_type not in allowed_types:
        logger.warning("skip_unsupported_image_type", url=img_url, content_type=content_type or "unknown")
        return b"", "", ""

    ext = "jpg" if content_type == "image/jpeg" else content_type.split("/")[-1]
    filename = f"upload_img.{ext}"
    return content, filename, content_type


async def _download_image(
    client: httpx.AsyncClient,
    img_url: str,
    allowed_types: set[str],
) -> tuple[bytes, str, str]:
    """Download a remote image and return content, filename, and mime type."""
    try:
        resp = await client.get(img_url, follow_redirects=True, timeout=15.0)
        resp.raise_for_status()
        return _normalize_image_response(resp, img_url, allowed_types)
    except Exception as exc:
        if _is_ssl_verification_error(exc) and _should_retry_without_ssl_verify():
            logger.warning("download_image_ssl_verify_failed_retry_insecure", url=img_url, error=str(exc))
            try:
                async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, verify=False) as insecure_client:
                    resp = await insecure_client.get(img_url, follow_redirects=True, timeout=15.0)
                    resp.raise_for_status()
                    return _normalize_image_response(resp, img_url, allowed_types)
            except Exception as insecure_exc:
                logger.warning(
                    "download_image_failed_after_insecure_retry",
                    url=img_url,
                    error=str(insecure_exc),
                )
                return b"", "", ""

        logger.warning("download_image_failed", url=img_url, error=str(exc))
        return b"", "", ""


async def upload_cover_material(client: httpx.AsyncClient, img_url: str, access_token: str) -> str:
    """Upload cover image and return the permanent media_id required by drafts."""
    if not img_url:
        return ""

    img_data, filename, content_type = await _download_image(client, img_url, COVER_ALLOWED_IMG_TYPES)
    if not img_data:
        return ""

    url = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={access_token}&type=image"
    files = {"media": (filename, img_data, content_type)}

    try:
        resp = await client.post(url, files=files, timeout=20.0)
        data = resp.json()
        if "media_id" in data:
            return data["media_id"]

        logger.error("upload_material_failed", result=data, url=img_url)
        return ""
    except Exception as exc:
        logger.error("upload_material_exception", url=img_url, error=str(exc))
        return ""


async def upload_article_image(client: httpx.AsyncClient, img_url: str, access_token: str) -> str:
    """Upload an in-article image and return the WeChat-hosted image URL."""
    if not img_url:
        return ""

    img_data, filename, content_type = await _download_image(client, img_url, ARTICLE_ALLOWED_IMG_TYPES)
    if not img_data:
        return img_url

    url = f"https://api.weixin.qq.com/cgi-bin/media/uploadimg?access_token={access_token}"
    files = {"media": (filename, img_data, content_type)}

    try:
        resp = await client.post(url, files=files, timeout=20.0)
        data = resp.json()
        if "url" in data:
            return data["url"]

        logger.warning("uploadimg_failed", result=data, url=img_url)
        return img_url
    except Exception as exc:
        logger.warning("uploadimg_exception", url=img_url, error=str(exc))
        return img_url
