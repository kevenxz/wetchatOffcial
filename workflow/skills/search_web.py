"""Skill 1: search_web 节点实现。
根据关键词搜索互联网，获取相关网页链接。
"""
from __future__ import annotations

import asyncio
import os
import time
from urllib.parse import urlparse

import httpx
import structlog

from workflow.state import WorkflowState

logger = structlog.get_logger(__name__)


async def _search_google(keywords: str, api_key: str) -> list[str]:
    """使用 SerpApi 进行 Google 搜索。"""
    url = "https://serpapi.com/search"
    params = {
        "q": keywords,
        "api_key": api_key,
        "engine": "google",
        "num": 10,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        
    results = []
    for item in data.get("organic_results", []):
        link = item.get("link")
        if link:
            results.append(link)
    return results


async def _search_bing(keywords: str, api_key: str) -> list[str]:
    """使用 Bing Web Search API 进行搜索。"""
    url = "https://api.bing.microsoft.com/v7.0/search"
    headers = {"Ocp-Apim-Subscription-Key": api_key}
    params = {"q": keywords, "count": 10}
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()
        
    results = []
    for item in data.get("webPages", {}).get("value", []):
        link = item.get("url")
        if link:
            results.append(link)
    return results


def _filter_links(links: list[str]) -> list[str]:
    """过滤重复和无效链接。"""
    seen = set()
    result = []
    for link in links:
        # 去除末尾的斜杠以实现简单的归一化
        normalized = link.rstrip("/")
        if normalized not in seen:
            seen.add(normalized)
            result.append(link)
    return result


async def search_web_node(state: WorkflowState) -> dict:
    """搜集相关网页链接。"""
    task_id = state["task_id"]
    keywords = state["keywords"]
    
    start_time = time.monotonic()
    
    logger.info(
        "skill_start",
        task_id=task_id,
        skill="search_web",
        status="running",
        keywords=keywords,
    )
    
    serpapi_key = os.getenv("SERPAPI_API_KEY") or os.getenv("GOOGLE_SEARCH_API_KEY")
    bing_api_key = os.getenv("BING_SEARCH_API_KEY")
    
    all_links = []
    error_msg = None
    retry_count = 0
    max_retries = 3
    
    while retry_count < max_retries:
        try:
            if serpapi_key:
                logger.info("search_web_provider", task_id=task_id, provider="serpapi_google", attempt=retry_count + 1)
                all_links = await _search_google(keywords, serpapi_key)
                if all_links:
                    break
            elif bing_api_key:
                logger.info("search_web_provider", task_id=task_id, provider="bing", attempt=retry_count + 1)
                all_links = await _search_bing(keywords, bing_api_key)
                if all_links:
                    break
            else:
                error_msg = "未配置搜索引擎 API Key"
                break
        except Exception as e:
            error_msg = str(e)
            logger.warning(
                "search_web_failed_attempt",
                task_id=task_id,
                attempt=retry_count + 1,
                error=error_msg
            )
        
        retry_count += 1
        if retry_count < max_retries:
            await asyncio.sleep(2 ** retry_count) # 退避重试
            
    filtered_links = _filter_links(all_links)[:10]
    
    duration_ms = round((time.monotonic() - start_time) * 1000)
    
    if not filtered_links:
        final_error = error_msg or "未能搜索到有效结果"
        logger.error(
            "skill_failed",
            task_id=task_id,
            skill="search_web",
            status="failed",
            duration_ms=duration_ms,
            error=final_error,
        )
        return {
            "status": "failed",
            "current_skill": "search_web",
            "error": final_error,
        }
        
    logger.info(
        "skill_done",
        task_id=task_id,
        skill="search_web",
        status="done",
        duration_ms=duration_ms,
        result_count=len(filtered_links),
    )
    
    return {
        "status": "running",
        "current_skill": "search_web",
        "progress": 25,
        "search_results": filtered_links,
        "retry_count": retry_count,
    }
