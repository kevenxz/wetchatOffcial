"""Helpers for downloading and uploading images to WeChat APIs."""
from __future__ import annotations

import mimetypes
import os
import ssl
from pathlib import Path
from urllib.parse import urlparse

import httpx
import structlog

logger = structlog.get_logger(__name__)

ARTICLE_ALLOWED_IMG_TYPES = {"image/jpeg", "image/png", "image/gif"}
COVER_ALLOWED_IMG_TYPES = {"image/jpeg", "image/png", "image/gif"}
INSECURE_SSL_FALLBACK_ENV = "WECHAT_IMAGE_DOWNLOAD_INSECURE_SSL_FALLBACK"


def _detect_image_mime(content: bytes, content_type_header: str, image_ref: str) -> str:
    """Infer the image MIME type from headers, file suffix, and file signature."""
    content_type = content_type_header.lower().split(";")[0].strip()
    if content_type:
        return content_type

    guessed, _ = mimetypes.guess_type(urlparse(image_ref).path)
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


def _is_remote_image_ref(image_ref: str) -> bool:
    parsed = urlparse(image_ref)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _normalize_image_content(
    content: bytes,
    *,
    image_ref: str,
    content_type_header: str,
    allowed_types: set[str],
    filename_hint: str | None = None,
) -> tuple[bytes, str, str]:
    content_type = _detect_image_mime(content, content_type_header, image_ref)

    if content_type == "image/svg+xml":
        logger.warning("skip_unsupported_svg_image", image_ref=image_ref)
        return b"", "", ""

    if content_type not in allowed_types:
        logger.warning(
            "skip_unsupported_image_type",
            image_ref=image_ref,
            content_type=content_type or "unknown",
        )
        return b"", "", ""

    ext = "jpg" if content_type == "image/jpeg" else content_type.split("/")[-1]
    filename = filename_hint or f"upload_img.{ext}"
    return content, filename, content_type


async def _download_image(
    client: httpx.AsyncClient,
    image_ref: str,
    allowed_types: set[str],
) -> tuple[bytes, str, str]:
    """Download a remote image and return content, filename, and MIME type."""
    try:
        response = await client.get(image_ref, follow_redirects=True, timeout=15.0)
        response.raise_for_status()
        return _normalize_image_content(
            response.content,
            image_ref=image_ref,
            content_type_header=response.headers.get("Content-Type", ""),
            allowed_types=allowed_types,
        )
    except Exception as exc:  # noqa: BLE001
        if _is_ssl_verification_error(exc) and _should_retry_without_ssl_verify():
            logger.warning("download_image_ssl_verify_failed_retry_insecure", url=image_ref, error=str(exc))
            try:
                async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, verify=False) as insecure_client:
                    response = await insecure_client.get(image_ref, follow_redirects=True, timeout=15.0)
                    response.raise_for_status()
                    return _normalize_image_content(
                        response.content,
                        image_ref=image_ref,
                        content_type_header=response.headers.get("Content-Type", ""),
                        allowed_types=allowed_types,
                    )
            except Exception as insecure_exc:  # noqa: BLE001
                logger.warning(
                    "download_image_failed_after_insecure_retry",
                    url=image_ref,
                    error=str(insecure_exc),
                )
                return b"", "", ""

        logger.warning("download_image_failed", url=image_ref, error=str(exc))
        return b"", "", ""


def _load_local_image(image_ref: str, allowed_types: set[str]) -> tuple[bytes, str, str]:
    """Load a locally generated image and return content, filename, and MIME type."""
    try:
        path = Path(image_ref).expanduser()
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        if not path.is_file():
            logger.warning("load_local_image_failed", image_ref=str(path), error="file not found")
            return b"", "", ""

        return _normalize_image_content(
            path.read_bytes(),
            image_ref=str(path),
            content_type_header="",
            allowed_types=allowed_types,
            filename_hint=path.name,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("load_local_image_failed", image_ref=image_ref, error=str(exc))
        return b"", "", ""


async def _read_image_source(
    client: httpx.AsyncClient,
    image_ref: str,
    allowed_types: set[str],
) -> tuple[bytes, str, str]:
    if _is_remote_image_ref(image_ref):
        return await _download_image(client, image_ref, allowed_types)
    return _load_local_image(image_ref, allowed_types)


async def upload_cover_material(client: httpx.AsyncClient, image_ref: str, access_token: str) -> str:
    """Upload cover image and return the permanent media_id required by drafts."""
    if not image_ref:
        return ""

    image_bytes, filename, content_type = await _read_image_source(client, image_ref, COVER_ALLOWED_IMG_TYPES)
    if not image_bytes:
        return ""

    url = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={access_token}&type=image"
    files = {"media": (filename, image_bytes, content_type)}

    try:
        response = await client.post(url, files=files, timeout=20.0)
        data = response.json()
        if "media_id" in data:
            return data["media_id"]

        logger.error("upload_material_failed", result=data, image_ref=image_ref)
        return ""
    except Exception as exc:  # noqa: BLE001
        logger.error("upload_material_exception", image_ref=image_ref, error=str(exc))
        return ""


async def upload_article_image(client: httpx.AsyncClient, image_ref: str, access_token: str) -> str:
    """Upload an in-article image and return the WeChat-hosted image URL."""
    if not image_ref:
        return ""

    image_bytes, filename, content_type = await _read_image_source(client, image_ref, ARTICLE_ALLOWED_IMG_TYPES)
    if not image_bytes:
        return image_ref if _is_remote_image_ref(image_ref) else ""

    url = f"https://api.weixin.qq.com/cgi-bin/media/uploadimg?access_token={access_token}"
    files = {"media": (filename, image_bytes, content_type)}

    try:
        response = await client.post(url, files=files, timeout=20.0)
        data = response.json()
        if "url" in data:
            return data["url"]

        logger.warning("uploadimg_failed", result=data, image_ref=image_ref)
        return image_ref if _is_remote_image_ref(image_ref) else ""
    except Exception as exc:  # noqa: BLE001
        logger.warning("uploadimg_exception", image_ref=image_ref, error=str(exc))
        return image_ref if _is_remote_image_ref(image_ref) else ""
