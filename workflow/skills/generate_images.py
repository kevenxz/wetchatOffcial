"""Skill 4: generate_images 节点实现。
为文章生成封面图与插图。当前默认从网页提取图片中随机/顺序挑选。
"""
from __future__ import annotations

import asyncio
import re
import time
from typing import Any

import structlog

from api.store import get_model_config
from workflow.model_logging import build_model_context, log_model_request, log_model_response
from workflow.state import WorkflowState

logger = structlog.get_logger(__name__)
IMAGE_GENERATION_MAX_RETRIES = 3
IMAGE_GENERATION_RETRY_BASE_SECONDS = 5


def _collect_images(extracted_contents: list[dict]) -> list[str]:
    all_images: list[str] = []
    for content in extracted_contents:
        for img in content.get("images", []):
            if img and img not in all_images:
                all_images.append(img)
    return all_images


def _required_illustration_count(content_text: str) -> int:
    return len(re.findall(r"\[插图\d+\]", content_text or ""))


def _truncate_text(content_text: str, limit: int = 1200) -> str:
    plain_text = re.sub(r"\[插图\d+\]", "", content_text or "")
    return plain_text[:limit]


def _cover_prompt(title: str, article_text: str) -> str:
    excerpt = _truncate_text(article_text, 900)
    return (
        "为微信公众号文章生成封面图，风格现代、专业、信息感强，避免文字与水印。"
        f"文章标题：{title or '未命名文章'}。"
        f"文章摘要：{excerpt}"
    )


def _illustration_prompt(title: str, article_text: str, index: int) -> str:
    excerpt = _truncate_text(article_text, 700)
    return (
        f"为微信公众号文章第{index}张插图生成配图。"
        "要求：写实插画风、构图清晰、可读性强、无文字、无水印。"
        f"文章标题：{title or '未命名文章'}。"
        f"文章摘要：{excerpt}"
    )


async def _generate_dalle_image(client: Any, prompt: str, model: str) -> str:
    resp = await client.images.generate(
        model=model,
        prompt=prompt,
        size="1024x1024",
    )
    data = getattr(resp, "data", None) or []
    if not data:
        return ""
    # WeChat push expects a fetchable image URL; only use URL output.
    return getattr(data[0], "url", "") or ""


def _is_rate_limit_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code == 429:
        return True

    response = getattr(exc, "response", None)
    if getattr(response, "status_code", None) == 429:
        return True

    message = str(exc).lower()
    return "rate limit" in message or "429" in message


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

    return IMAGE_GENERATION_RETRY_BASE_SECONDS * (2 ** retry_index)


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
            log_model_request(
                logger,
                task_id=task_id,
                skill="generate_images",
                context={**model_context, "attempt": retry_index + 1},
                request={"prompt": prompt},
            )
            image_url = await _generate_dalle_image(client, prompt, model)
            log_model_response(
                logger,
                task_id=task_id,
                skill="generate_images",
                context={**model_context, "attempt": retry_index + 1},
                response={"image_url": image_url},
            )
            return image_url
        except Exception as exc:
            if not _is_rate_limit_error(exc) or retry_index >= IMAGE_GENERATION_MAX_RETRIES:
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


async def generate_images_node(state: WorkflowState) -> dict:
    """处理文章配图与封面图。"""
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
        error_msg = "缺少 generated_article，无法生成配图"
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

    # 1. 收集所有可用图片
    all_images = _collect_images(extracted_contents)

    # 2. 从文中查找有多少个插图标记
    content_text = generated_article.get("content", "")
    required_illustrations_count = _required_illustration_count(content_text)

    # 默认先走网页提取图片分配
    cover_image = ""
    illustrations: list[str] = []
    if all_images:
        cover_image = all_images.pop(0)  # 第一张作为封面图
    for _ in range(required_illustrations_count):
        if all_images:
            illustrations.append(all_images.pop(0))
        else:
            break

    # 可选：开启 DALL-E 生图，优先覆盖上述结果
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
                for idx in range(1, required_illustrations_count + 1):
                    img_url = await _generate_dalle_image_with_retry(
                        client,
                        _illustration_prompt(generated_article.get("title", ""), content_text, idx),
                        model,
                        base_url,
                        api_key,
                        task_id,
                        f"illustration_{idx}",
                    )
                    if img_url:
                        generated_illustrations.append(img_url)

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
            except Exception as exc:
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
