"""Fetch top-ranked pages and extract clean article content."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

import httpx
import structlog
import trafilatura
from bs4 import BeautifulSoup

from workflow.state import WorkflowState

logger = structlog.get_logger(__name__)


def _is_valid_image(url: str, img_tag: dict | None = None) -> bool:
    """Validate image format and rough size."""
    if not url:
        return False

    url_lower = url.lower()
    valid_ext = (".jpg", ".jpeg", ".png", ".webp")
    if not any(ext in url_lower for ext in valid_ext):
        if ".gif" in url_lower or ".svg" in url_lower or "base64" in url_lower:
            return False

    if img_tag:
        try:
            width = int(img_tag.get("width", 0))
            height = int(img_tag.get("height", 0))
            if width > 0 and width < 300:
                return False
            if height > 0 and height < 300:
                return False
        except (ValueError, TypeError):
            pass

    return True


def _extract_source_items(search_results: list) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    for entry in search_results:
        if isinstance(entry, str):
            url = entry
            item = {"url": url}
        else:
            item = dict(entry)
            url = item.get("url", "")
        if not url or url in seen:
            continue
        seen.add(url)
        items.append(item)
    return items


async def _fetch_and_extract_single(item: dict, client: httpx.AsyncClient) -> dict | None:
    """Fetch one URL and extract text, title and images."""
    url = item["url"]
    try:
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()
        html_content = resp.text
    except Exception as exc:  # noqa: BLE001
        logger.warning("fetch_failed", url=url, error=str(exc))
        return None

    extracted_text = trafilatura.extract(html_content, include_images=False, include_links=False)
    soup = BeautifulSoup(html_content, "html.parser")
    title = soup.title.string.strip() if soup.title and soup.title.string else item.get("title", "").strip()

    if not extracted_text:
        paragraphs = soup.find_all("p")
        extracted_text = "\n".join(
            [
                paragraph.get_text(separator=" ", strip=True)
                for paragraph in paragraphs
                if len(paragraph.get_text(strip=True)) > 20
            ]
        )

    if not extracted_text or len(extracted_text) < 50:
        logger.warning("extract_failed_or_too_short", url=url)
        return None

    images: list[str] = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if src and src.startswith("http") and _is_valid_image(src, img.attrs):
            images.append(src)
            if len(images) >= 5:
                break

    return {
        "url": url,
        "title": title,
        "text": extracted_text,
        "images": images,
        "source_meta": {
            "query": item.get("query", ""),
            "query_intent": item.get("query_intent", ""),
            "provider": item.get("provider", ""),
            "domain": item.get("domain", ""),
            "source_type": item.get("source_type", ""),
            "authority_score": item.get("authority_score", 0),
            "relevance_score": item.get("relevance_score", 0),
            "freshness_score": item.get("freshness_score", 0),
            "originality_score": item.get("originality_score", 0),
            "cross_source_score": item.get("cross_source_score", 0),
            "content_depth_score": item.get("content_depth_score", 0),
            "risk_penalty": item.get("risk_penalty", 0),
            "duplicate_penalty": item.get("duplicate_penalty", 0),
            "final_score": item.get("final_score", 0),
            "snippet": item.get("snippet", ""),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        },
    }


async def fetch_extract_node(state: WorkflowState) -> dict:
    """Fetch top search results and extract clean content."""
    task_id = state["task_id"]
    source_items = _extract_source_items(state.get("search_results", []))[:8]

    start_time = time.monotonic()
    logger.info(
        "skill_start",
        task_id=task_id,
        skill="fetch_and_extract",
        status="running",
        url_count=len(source_items),
    )

    if not source_items:
        logger.warning("no_urls_to_fetch", task_id=task_id)
        return {
            "status": "failed",
            "current_skill": "fetch_and_extract",
            "error": "没有找到可提取的 URL",
        }

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    }
    timeout = httpx.Timeout(15.0)

    extracted: list[dict] = []
    async with httpx.AsyncClient(headers=headers, timeout=timeout) as client:
        tasks = [_fetch_and_extract_single(item, client) for item in source_items]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, dict) and result:
            extracted.append(result)

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
        "progress": 68,
        "extracted_contents": extracted,
    }
