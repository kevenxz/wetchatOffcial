"""Skill 2: fetch_and_extract 节点实现。
并发抓取网页链接，提取正文、标题和图片。
"""
from __future__ import annotations

import asyncio
import time
from urllib.parse import urlparse

import httpx
import structlog
import trafilatura
from bs4 import BeautifulSoup

from workflow.state import WorkflowState

logger = structlog.get_logger(__name__)


def _is_valid_image(url: str, img_tag: dict | None = None) -> bool:
    """粗略校验图片格式和尺寸（如果有 width/height 属性）。"""
    if not url:
        return False
        
    url_lower = url.lower()
    # 允许的后缀或包含关键字
    valid_ext = (".jpg", ".jpeg", ".png", ".webp")
    if not any(ext in url_lower for ext in valid_ext):
        # 有些图床没有显式后缀，简单放行以保证覆盖面，
        # 但过滤掉常见的 非图片 或 gif/svg 格式
        if ".gif" in url_lower or ".svg" in url_lower or "base64" in url_lower:
            return False
            
    if img_tag:
        try:
            w = int(img_tag.get("width", 0))
            h = int(img_tag.get("height", 0))
            if w > 0 and w < 300:
                return False
            if h > 0 and h < 300:
                return False
        except (ValueError, TypeError):
            pass

    return True


async def _fetch_and_extract_single(url: str, client: httpx.AsyncClient) -> dict | None:
    """抓取单个 URL 并提取内容。"""
    try:
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()
        html_content = resp.text
    except Exception as e:
        logger.warning(
            "fetch_failed",
            url=url,
            error=str(e),
        )
        return None

    # 1. Trafilatura 提取正文和标题
    extracted_text = trafilatura.extract(html_content, include_images=False, include_links=False)
    
    # 2. BeautifulSoup 补充提取标题和图片
    soup = BeautifulSoup(html_content, "html.parser")
    title = ""
    
    # 如果 trafilatura 没有提取到 title，用 bs4 补救
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
        
    if not extracted_text:
        # Fallback to bs4 text extraction if trafilatura fails
        paragraphs = soup.find_all("p")
        extracted_text = "\n".join([p.get_text(separator=" ", strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20])
        
    if not extracted_text or len(extracted_text) < 50:
        logger.warning("extract_failed_or_too_short", url=url)
        return None

    # 提取图片
    images = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if src and src.startswith("http"):
            # 校验图片
            if _is_valid_image(src, img.attrs):
                images.append(src)
                if len(images) >= 5: # 单页面最多采集 5 张
                    break

    return {
        "url": url,
        "title": title,
        "text": extracted_text,
        "images": images
    }


async def fetch_extract_node(state: WorkflowState) -> dict:
    """并发抓取所有 search_results 的内容。"""
    task_id = state["task_id"]
    urls = state.get("search_results", [])
    
    start_time = time.monotonic()
    
    logger.info(
        "skill_start",
        task_id=task_id,
        skill="fetch_and_extract",
        status="running",
        url_count=len(urls),
    )
    
    if not urls:
        duration_ms = round((time.monotonic() - start_time) * 1000)
        logger.warning("no_urls_to_fetch", task_id=task_id)
        return {
            "status": "failed",
            "current_skill": "fetch_and_extract",
            "error": "没有找到可提取的 URL",
        }

    # 并发抓取
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    timeout = httpx.Timeout(15.0)
    
    extracted = []
    async with httpx.AsyncClient(headers=headers, timeout=timeout) as client:
        tasks = [_fetch_and_extract_single(url, client) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
    for res in results:
        if isinstance(res, dict) and res:
            extracted.append(res)
            
    duration_ms = round((time.monotonic() - start_time) * 1000)

    if not extracted:
        error_msg = "所有页面抓取或内容提取均失败"
        logger.error(
            "skill_failed",
            task_id=task_id,
            skill="fetch_and_extract",
            status="failed",
            duration_ms=duration_ms,
            error=error_msg,
        )
        return {
            "status": "failed",
            "current_skill": "fetch_and_extract",
            "error": error_msg,
        }
        
    logger.info(
        "skill_done",
        task_id=task_id,
        skill="fetch_and_extract",
        status="done",
        duration_ms=duration_ms,
        success_count=len(extracted),
    )

    return {
        "status": "running",
        "current_skill": "fetch_and_extract",
        "progress": 50,
        "extracted_contents": extracted,
    }
