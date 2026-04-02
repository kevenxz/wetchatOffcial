"""Manual integration script to generate one image and save it under ./artifacts/generated_images."""
from __future__ import annotations

import argparse
import base64
import mimetypes
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv
from openai import OpenAI

PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.chdir(PROJECT_ROOT)
load_dotenv(PROJECT_ROOT / ".env")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.store import get_model_config

ARTIFACTS_DIR = PROJECT_ROOT / "artifacts" / "generated_images"
DEFAULT_PROMPT = (
    "Generate a realistic photo of a golden retriever sitting by a sunny window, "
    "natural lighting, shallow depth of field, high detail, no text, no watermark."
)
SUPPORTED_IMAGE_FORMATS = {"png", "jpg", "jpeg", "webp", "gif"}


def _response_value(payload: Any, key: str, default: Any = None) -> Any:
    if isinstance(payload, dict):
        return payload.get(key, default)
    return getattr(payload, key, default)


def _extract_first_url(text: str) -> str:
    markdown_match = re.search(r"!\[[^\]]*\]\((https?://[^)]+)\)", text or "")
    if markdown_match:
        return markdown_match.group(1)

    url_match = re.search(r"https?://[^\s'\"<>]+", text or "")
    if not url_match:
        return ""

    url = url_match.group(0).rstrip(".,);]")
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return url


def _mask_secret(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}***{value[-4:]}"


def _sanitize_output_format(output_format: str | None) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]", "", (output_format or "png").strip().lower())
    if cleaned == "jpeg":
        return "jpg"
    if cleaned in SUPPORTED_IMAGE_FORMATS:
        return cleaned
    return "png"


def _guess_suffix(url: str = "", content_type: str | None = None) -> str:
    if content_type:
        guessed = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if guessed:
            return guessed

    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix
    return suffix if suffix else ".png"


def _decode_base64_image(encoded: str) -> bytes:
    try:
        return base64.b64decode(encoded)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("image response contains invalid base64 content") from exc


def _save_bytes(image_bytes: bytes, *, suffix: str, output_name: str | None = None) -> Path:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = output_name or f"manual_generated_image_{timestamp}"
    if not suffix.startswith("."):
        suffix = f".{suffix}"
    path = ARTIFACTS_DIR / f"{stem}{suffix}"
    path.write_bytes(image_bytes)
    return path


def _download_url(url: str, output_name: str | None = None) -> Path:
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
    suffix = _guess_suffix(url, response.headers.get("content-type"))
    return _save_bytes(response.content, suffix=suffix, output_name=output_name)


def _save_from_images_response(response: Any, output_name: str | None = None) -> Path | None:
    data = _response_value(response, "data", []) or []
    if not data:
        return None

    first = data[0]
    image_url = _response_value(first, "url", "") or ""
    if image_url:
        return _download_url(image_url, output_name=output_name)

    b64_json = _response_value(first, "b64_json", "") or _response_value(first, "image_base64", "") or ""
    if b64_json:
        suffix = f".{_sanitize_output_format(_response_value(response, 'output_format', None))}"
        return _save_bytes(_decode_base64_image(b64_json), suffix=suffix, output_name=output_name)

    return None


def _extract_path_from_chat_response(response: Any, output_name: str | None = None) -> Path | None:
    choices = _response_value(response, "choices", []) or []
    if not choices:
        return None

    message = _response_value(choices[0], "message")
    if message is None:
        return None

    content = _response_value(message, "content")
    if isinstance(content, str):
        image_url = _extract_first_url(content)
        if image_url:
            return _download_url(image_url, output_name=output_name)
        return None

    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                image_url = item.get("image_url")
                if isinstance(image_url, dict) and image_url.get("url"):
                    return _download_url(str(image_url["url"]), output_name=output_name)
                if isinstance(image_url, str) and image_url:
                    return _download_url(image_url, output_name=output_name)

                inline_b64 = item.get("b64_json") or item.get("image_base64")
                if isinstance(inline_b64, str) and inline_b64:
                    suffix = f".{_sanitize_output_format(str(item.get('output_format') or 'png'))}"
                    return _save_bytes(_decode_base64_image(inline_b64), suffix=suffix, output_name=output_name)

                for key in ("text", "content"):
                    value = item.get(key)
                    if value:
                        image_url = _extract_first_url(str(value))
                        if image_url:
                            return _download_url(image_url, output_name=output_name)
            elif isinstance(item, str):
                image_url = _extract_first_url(item)
                if image_url:
                    return _download_url(image_url, output_name=output_name)

    return None


def _build_config(
    *,
    api_key: str | None,
    base_url: str | None,
    model: str | None,
) -> tuple[str, str | None, str]:
    image_config = get_model_config().image
    resolved_api_key = (api_key or image_config.api_key or "").strip()
    resolved_base_url = (base_url or image_config.base_url or "").strip() or None
    resolved_model = (model or image_config.model or "").strip()

    if not resolved_api_key:
        raise RuntimeError("image model API key is not configured")
    if not resolved_model:
        raise RuntimeError("image model is not configured")
    return resolved_api_key, resolved_base_url, resolved_model


def _print_request(method: str, *, base_url: str | None, model: str, prompt: str, size: str) -> None:
    print(
        {
            "request_method": method,
            "base_url": base_url,
            "model": model,
            "size": size,
            "prompt": prompt,
        }
    )


def _print_images_response_summary(response: Any) -> None:
    data = _response_value(response, "data", []) or []
    print(
        {
            "response_type": "images.generate",
            "data_count": len(data),
            "output_format": _response_value(response, "output_format", ""),
            "usage": _response_value(response, "usage", None),
        }
    )


def _print_chat_response_summary(response: Any) -> None:
    choices = _response_value(response, "choices", []) or []
    message = _response_value(choices[0], "message") if choices else None
    print(
        {
            "response_type": "chat.completions.create",
            "choices_count": len(choices),
            "content_preview": str(_response_value(message, "content", ""))[:500],
        }
    )


def generate_and_download_image(
    prompt: str,
    output_name: str | None = None,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    size: str = "1024x1024",
    skip_chat_fallback: bool = False,
) -> tuple[Path, str]:
    resolved_api_key, resolved_base_url, resolved_model = _build_config(
        api_key=api_key,
        base_url=base_url,
        model=model,
    )

    print(
        {
            "image_base_url": resolved_base_url,
            "image_model": resolved_model,
            "image_api_key": _mask_secret(resolved_api_key),
            "artifacts_dir": str(ARTIFACTS_DIR),
        }
    )

    client = OpenAI(api_key=resolved_api_key, base_url=resolved_base_url)

    try:
        _print_request(
            "images.generate",
            base_url=resolved_base_url,
            model=resolved_model,
            prompt=prompt,
            size=size,
        )
        response = client.images.generate(
            model=resolved_model,
            prompt=prompt,
            size=size,
        )
        _print_images_response_summary(response)
        saved_path = _save_from_images_response(response, output_name=output_name)
        if saved_path:
            return saved_path, "images.generate"
        print("images.generate returned no downloadable image content")
    except Exception as exc:  # noqa: BLE001
        print(f"images.generate failed: {exc}")
        if skip_chat_fallback:
            raise

    _print_request(
        "chat.completions.create",
        base_url=resolved_base_url,
        model=resolved_model,
        prompt=prompt,
        size=size,
    )
    response = client.chat.completions.create(
        model=resolved_model,
        messages=[{"role": "user", "content": prompt}],
    )
    _print_chat_response_summary(response)
    saved_path = _extract_path_from_chat_response(response, output_name=output_name)
    if saved_path:
        return saved_path, "chat.completions.create"

    raise RuntimeError("model response does not contain a downloadable image")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate one image with the configured model and save it under ./artifacts/generated_images")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT, help="Prompt used for image generation")
    parser.add_argument("--output-name", default=None, help="Optional output file name without extension")
    parser.add_argument("--api-key", default=None, help="Override image API key for this run")
    parser.add_argument("--base-url", default=None, help="Override image base URL for this run")
    parser.add_argument("--model", default=None, help="Override image model for this run")
    parser.add_argument("--size", default="1024x1024", help="Image size for images.generate requests")
    parser.add_argument("--skip-chat-fallback", action="store_true", help="Fail immediately if images.generate does not succeed")
    args = parser.parse_args()

    path, method = generate_and_download_image(
        args.prompt,
        args.output_name,
        api_key=args.api_key,
        base_url=args.base_url,
        model=args.model,
        size=args.size,
        skip_chat_fallback=args.skip_chat_fallback,
    )
    print(f"saved image: {path}")
    print(f"generation method: {method}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
