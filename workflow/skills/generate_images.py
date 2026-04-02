"""Workflow skill for selecting or generating article cover and illustration images."""
from __future__ import annotations

import asyncio
import base64
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import structlog

from api.store import get_model_config
from workflow.model_logging import build_model_context, log_model_request, log_model_response
from workflow.state import WorkflowState

logger = structlog.get_logger(__name__)

IMAGE_GENERATION_MAX_RETRIES = 3
IMAGE_GENERATION_RETRY_BASE_SECONDS = 5
GENERATED_IMAGES_DIR = Path("artifacts/generated_images")
SUPPORTED_IMAGE_FORMATS = {"png", "jpg", "jpeg", "webp", "gif"}


def _collect_images(extracted_contents: list[dict]) -> list[str]:
    all_images: list[str] = []
    for content in extracted_contents:
        for image in content.get("images", []):
            if image and image not in all_images:
                all_images.append(image)
    return all_images


def _required_illustration_count(content_text: str) -> int:
    return len(re.findall(r"\[插图\d+\]", content_text or ""))


def _truncate_text(content_text: str, limit: int = 1200) -> str:
    plain_text = re.sub(r"\[插图\d+\]", "", content_text or "")
    return plain_text[:limit]


def _extract_markdown_chart_blocks(content_text: str) -> dict[int, dict[str, str]]:
    chart_blocks: dict[int, dict[str, str]] = {}
    text = content_text or ""
    matches = list(re.finditer(r"^###\s*(?:图表|Chart)\s*(\d+)\s*[:：]\s*(.+?)\s*$", text, flags=re.MULTILINE))

    for index, match in enumerate(matches):
        next_chart_start = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        next_h2_match = re.search(r"^##\s+", text[match.end() :], flags=re.MULTILINE)
        block_end = next_chart_start
        if next_h2_match:
            block_end = min(block_end, match.end() + next_h2_match.start())

        block = text[match.start() : block_end]
        illustration_match = re.search(r"\[插图(\d+)\]", block)
        illustration_index = int(illustration_match.group(1)) if illustration_match else int(match.group(1))
        data_source_match = re.search(
            r"^\s*-\s*(?:数据来源|Data Source)\s*[:：]\s*(.+?)\s*$",
            block,
            flags=re.MULTILINE,
        )
        chart_note_match = re.search(
            r"^\s*-\s*(?:图表说明|说明|Chart Note|Description)\s*[:：]\s*(.+?)\s*$",
            block,
            flags=re.MULTILINE,
        )
        chart_blocks[illustration_index] = {
            "title": match.group(2).strip(),
            "data_source": data_source_match.group(1).strip() if data_source_match else "",
            "chart_note": chart_note_match.group(1).strip() if chart_note_match else "",
        }

    return chart_blocks


def _cover_prompt(title: str, article_text: str) -> str:
    excerpt = _truncate_text(article_text, 900)
    return (
        "为微信公众号文章生成封面图，风格现代、专业、信息感强，避免文字和水印。"
        f"文章标题：{title or '未命名文章'}。"
        f"文章摘要：{excerpt}"
    )


def _illustration_prompt(
    title: str,
    article_text: str,
    index: int,
    chart_instruction: dict[str, str] | None = None,
) -> str:
    excerpt = _truncate_text(article_text, 700)
    if chart_instruction:
        prompt_parts = [
            f"为微信公众号财经文章第{index}张插图生成图表型信息图。",
            "要求：专业金融图表风格，结构清晰，适合手机阅读，优先用线图、柱状图、面积图或对比图表达趋势和关系。",
            "不要人物插画，不要照片风格，不要水印，不要密集小字，也不要伪造精确数值。",
            f"文章标题：{title or '未命名文章'}。",
            f"图表标题：{chart_instruction.get('title', f'图表{index}')}。",
        ]
        if chart_instruction.get("data_source"):
            prompt_parts.append(f"数据来源参考：{chart_instruction['data_source']}。")
        if chart_instruction.get("chart_note"):
            prompt_parts.append(f"图表说明：{chart_instruction['chart_note']}。")
        prompt_parts.append(f"文章摘要：{excerpt}")
        return "".join(prompt_parts)

    return (
        f"为微信公众号文章第{index}张插图生成配图。"
        "要求：写实插画风、构图清晰、可读性强、无文字、无水印。"
        f"文章标题：{title or '未命名文章'}。"
        f"文章摘要：{excerpt}"
    )


def _response_value(payload: Any, key: str, default: Any = None) -> Any:
    if isinstance(payload, dict):
        return payload.get(key, default)
    return getattr(payload, key, default)


def _sanitize_output_format(output_format: str | None) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]", "", (output_format or "png").strip().lower())
    if cleaned == "jpeg":
        return "jpg"
    if cleaned in SUPPORTED_IMAGE_FORMATS:
        return cleaned
    return "png"


def _save_generated_image_bytes(
    image_bytes: bytes,
    *,
    task_id: str,
    image_kind: str,
    output_format: str | None = None,
) -> str:
    suffix = _sanitize_output_format(output_format)
    GENERATED_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    file_name = f"{task_id}_{image_kind}_{int(time.time() * 1000)}.{suffix}"
    path = (GENERATED_IMAGES_DIR / file_name).resolve()
    path.write_bytes(image_bytes)
    return str(path)


def _decode_base64_image(encoded: str) -> bytes:
    try:
        return base64.b64decode(encoded)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("image response contains invalid base64 content") from exc


def _image_ref_kind(image_ref: str) -> str:
    if not image_ref:
        return "empty"
    parsed = urlparse(image_ref)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return "remote_url"
    return "local_file"


def _extract_generated_image_from_images_response(response: Any, *, task_id: str, image_kind: str) -> str:
    data = _response_value(response, "data", []) or []
    if not data:
        return ""

    first = data[0]
    image_url = _response_value(first, "url", "") or ""
    if image_url:
        return image_url

    b64_json = _response_value(first, "b64_json", "") or _response_value(first, "image_base64", "") or ""
    if b64_json:
        return _save_generated_image_bytes(
            _decode_base64_image(b64_json),
            task_id=task_id,
            image_kind=image_kind,
            output_format=_response_value(response, "output_format", None),
        )

    return ""


async def _generate_dalle_image(client: Any, prompt: str, model: str, *, task_id: str, image_kind: str) -> str:
    response = await client.images.generate(
        model=model,
        prompt=prompt,
        size="1024x1024",
    )
    return _extract_generated_image_from_images_response(response, task_id=task_id, image_kind=image_kind)


def _extract_first_url(text: str) -> str:
    match = re.search(r"https?://[^\s'\"<>]+", text or "")
    if not match:
        return ""
    url = match.group(0).rstrip(".,);]")
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return url


def _extract_generated_image_from_chat_response(response: Any, *, task_id: str, image_kind: str) -> str:
    choices = _response_value(response, "choices", []) or []
    if not choices:
        return ""

    message = _response_value(choices[0], "message")
    if message is None:
        return ""

    content = _response_value(message, "content")
    if isinstance(content, str):
        return _extract_first_url(content)

    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                image_url = item.get("image_url")
                if isinstance(image_url, dict) and image_url.get("url"):
                    return str(image_url["url"])
                if isinstance(image_url, str) and image_url:
                    return image_url

                inline_b64 = item.get("b64_json") or item.get("image_base64")
                if isinstance(inline_b64, str) and inline_b64:
                    return _save_generated_image_bytes(
                        _decode_base64_image(inline_b64),
                        task_id=task_id,
                        image_kind=image_kind,
                        output_format=str(item.get("output_format") or "png"),
                    )

                for key in ("text", "content"):
                    value = item.get(key)
                    if value:
                        image_url = _extract_first_url(str(value))
                        if image_url:
                            return image_url
            elif isinstance(item, str):
                image_url = _extract_first_url(item)
                if image_url:
                    return image_url

    return ""


async def _generate_chat_completion_image(
    client: Any,
    prompt: str,
    model: str,
    *,
    task_id: str,
    image_kind: str,
) -> tuple[str, Any]:
    response = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    return _extract_generated_image_from_chat_response(response, task_id=task_id, image_kind=image_kind), response


def _is_rate_limit_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code == 429:
        return True

    response = getattr(exc, "response", None)
    if getattr(response, "status_code", None) == 429:
        return True

    message = str(exc).lower()
    return "rate limit" in message or "429" in message


def _status_code_from_exception(exc: Exception) -> int | None:
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code

    response = getattr(exc, "response", None)
    response_status_code = getattr(response, "status_code", None)
    if isinstance(response_status_code, int):
        return response_status_code

    return None


def _get_backoff_delay_seconds(retry_index: int) -> int:
    return IMAGE_GENERATION_RETRY_BASE_SECONDS * (2 ** retry_index)


def _is_retryable_generation_error(exc: Exception) -> bool:
    status_code = _status_code_from_exception(exc)
    if status_code is not None:
        return status_code in {408, 409, 425, 429, 500, 502, 503, 504}

    message = str(exc).lower()
    retryable_markers = (
        "timeout",
        "timed out",
        "connection",
        "temporarily unavailable",
        "service unavailable",
        "server error",
        "try again",
        "rate limit",
        "429",
        "502",
        "503",
        "504",
    )
    return any(marker in message for marker in retryable_markers)


def _get_retry_delay_seconds(exc: Exception, retry_index: int) -> int:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers:
        retry_after = headers.get("retry-after") or headers.get("Retry-After")
        if retry_after:
            try:
                return max(1, int(float(retry_after)))
            except ValueError:
                pass

    return _get_backoff_delay_seconds(retry_index)


async def _generate_dalle_image_with_retry(
    client: Any,
    prompt: str,
    model: str,
    base_url: str | None,
    api_key: str,
    task_id: str,
    image_kind: str,
) -> str:
    retry_index = 0
    model_context = build_model_context(
        model=model,
        base_url=base_url,
        api_key=api_key,
        image_kind=image_kind,
        size="1024x1024",
    )

    while True:
        try:
            images_context = {**model_context, "attempt": retry_index + 1, "api_method": "images.generate"}
            log_model_request(
                logger,
                task_id=task_id,
                skill="generate_images",
                context=images_context,
                request={"prompt": prompt},
            )
            image_ref = await _generate_dalle_image(
                client,
                prompt,
                model,
                task_id=task_id,
                image_kind=image_kind,
            )
            log_model_response(
                logger,
                task_id=task_id,
                skill="generate_images",
                context=images_context,
                response={
                    "image_ref": image_ref,
                    "image_ref_kind": _image_ref_kind(image_ref),
                },
            )
            if image_ref:
                return image_ref

            if retry_index >= IMAGE_GENERATION_MAX_RETRIES:
                raise ValueError("images.generate response does not contain image content")

            wait_seconds = _get_backoff_delay_seconds(retry_index)
            logger.warning(
                "image_generation_empty_result_retrying",
                task_id=task_id,
                image_kind=image_kind,
                retry_count=retry_index + 1,
                wait_seconds=wait_seconds,
                api_method="images.generate",
            )
            await asyncio.sleep(wait_seconds)
            retry_index += 1
            continue
        except Exception as exc:
            if _is_rate_limit_error(exc):
                if retry_index >= IMAGE_GENERATION_MAX_RETRIES:
                    raise
                wait_seconds = _get_retry_delay_seconds(exc, retry_index)
                logger.warning(
                    "image_generation_rate_limited_retrying",
                    task_id=task_id,
                    image_kind=image_kind,
                    retry_count=retry_index + 1,
                    wait_seconds=wait_seconds,
                    error=str(exc),
                )
                await asyncio.sleep(wait_seconds)
                retry_index += 1
                continue

            logger.warning(
                "image_generation_images_api_failed_try_chat",
                task_id=task_id,
                image_kind=image_kind,
                error=str(exc),
            )

            chat_context = {**model_context, "attempt": retry_index + 1, "api_method": "chat.completions.create"}
            try:
                log_model_request(
                    logger,
                    task_id=task_id,
                    skill="generate_images",
                    context=chat_context,
                    request={"messages": [{"role": "user", "content": prompt}]},
                )
                image_ref, raw_response = await _generate_chat_completion_image(
                    client,
                    prompt,
                    model,
                    task_id=task_id,
                    image_kind=image_kind,
                )
                log_model_response(
                    logger,
                    task_id=task_id,
                    skill="generate_images",
                    context=chat_context,
                    response={
                        "image_ref": image_ref,
                        "image_ref_kind": _image_ref_kind(image_ref),
                        "raw_content": _response_value(_response_value((_response_value(raw_response, "choices", [None]) or [None])[0], "message"), "content"),
                    },
                )
                if image_ref:
                    return image_ref
                if retry_index >= IMAGE_GENERATION_MAX_RETRIES:
                    raise ValueError("chat completion response does not contain image content")

                wait_seconds = _get_backoff_delay_seconds(retry_index)
                logger.warning(
                    "image_generation_empty_result_retrying",
                    task_id=task_id,
                    image_kind=image_kind,
                    retry_count=retry_index + 1,
                    wait_seconds=wait_seconds,
                    api_method="chat.completions.create",
                )
                await asyncio.sleep(wait_seconds)
                retry_index += 1
                continue
            except Exception as chat_exc:
                if _is_rate_limit_error(chat_exc):
                    if retry_index >= IMAGE_GENERATION_MAX_RETRIES:
                        raise
                    wait_seconds = _get_retry_delay_seconds(chat_exc, retry_index)
                    logger.warning(
                        "image_generation_rate_limited_retrying",
                        task_id=task_id,
                        image_kind=image_kind,
                        retry_count=retry_index + 1,
                        wait_seconds=wait_seconds,
                        error=str(chat_exc),
                    )
                    await asyncio.sleep(wait_seconds)
                    retry_index += 1
                    continue
                if retry_index < IMAGE_GENERATION_MAX_RETRIES and (
                    _is_retryable_generation_error(exc) or _is_retryable_generation_error(chat_exc)
                ):
                    wait_seconds = _get_retry_delay_seconds(chat_exc, retry_index)
                    logger.warning(
                        "image_generation_failed_retrying",
                        task_id=task_id,
                        image_kind=image_kind,
                        retry_count=retry_index + 1,
                        wait_seconds=wait_seconds,
                        images_api_error=str(exc),
                        chat_api_error=str(chat_exc),
                    )
                    await asyncio.sleep(wait_seconds)
                    retry_index += 1
                    continue
                raise chat_exc


async def generate_images_node(state: WorkflowState) -> dict:
    """Generate article cover and illustration images."""
    task_id = state["task_id"]
    extracted_contents = state.get("extracted_contents", [])
    generated_article = state.get("generated_article", {})

    start_time = time.monotonic()
    logger.info(
        "skill_start",
        task_id=task_id,
        skill="generate_images",
        status="running",
    )

    if not generated_article:
        duration_ms = round((time.monotonic() - start_time) * 1000)
        error_msg = "missing generated_article, cannot generate images"
        logger.error(
            "skill_failed",
            task_id=task_id,
            skill="generate_images",
            status="failed",
            duration_ms=duration_ms,
            error=error_msg,
        )
        return {
            "status": "failed",
            "current_skill": "generate_images",
            "error": error_msg,
        }

    all_images = _collect_images(extracted_contents)
    content_text = generated_article.get("content", "")
    required_illustrations_count = _required_illustration_count(content_text)
    chart_blocks = _extract_markdown_chart_blocks(content_text)

    cover_image = ""
    illustrations: list[str] = []
    if all_images:
        cover_image = all_images.pop(0)
    for _ in range(required_illustrations_count):
        if all_images:
            illustrations.append(all_images.pop(0))
        else:
            break

    image_model_config = get_model_config().image
    if image_model_config.enabled:
        api_key = image_model_config.api_key
        if not api_key:
            logger.warning("image_generation_enabled_but_no_api_key", task_id=task_id)
        else:
            model = image_model_config.model
            base_url = image_model_config.base_url
            try:
                from openai import AsyncOpenAI

                client = AsyncOpenAI(api_key=api_key, base_url=base_url)
                generated_cover = await _generate_dalle_image_with_retry(
                    client,
                    _cover_prompt(generated_article.get("title", ""), content_text),
                    model,
                    base_url,
                    api_key,
                    task_id,
                    "cover",
                )
                generated_illustrations: list[str] = []
                for index in range(1, required_illustrations_count + 1):
                    image_ref = await _generate_dalle_image_with_retry(
                        client,
                        _illustration_prompt(
                            generated_article.get("title", ""),
                            content_text,
                            index,
                            chart_blocks.get(index),
                        ),
                        model,
                        base_url,
                        api_key,
                        task_id,
                        f"illustration_{index}",
                    )
                    if image_ref:
                        generated_illustrations.append(image_ref)

                if generated_cover:
                    cover_image = generated_cover
                if generated_illustrations:
                    illustrations = generated_illustrations

                logger.info(
                    "image_generation_done",
                    task_id=task_id,
                    cover_image_set=bool(generated_cover),
                    illustrations_count=len(generated_illustrations),
                    model=model,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "image_generation_failed_fallback_to_extracted",
                    task_id=task_id,
                    error=str(exc),
                )

    new_article = dict(generated_article)
    new_article["cover_image"] = cover_image
    new_article["illustrations"] = illustrations

    duration_ms = round((time.monotonic() - start_time) * 1000)
    logger.info(
        "skill_done",
        task_id=task_id,
        skill="generate_images",
        status="done",
        duration_ms=duration_ms,
        cover_image_set=bool(cover_image),
        illustrations_count=len(illustrations),
    )

    return {
        "status": "running",
        "current_skill": "generate_images",
        "progress": 85,
        "generated_article": new_article,
    }
