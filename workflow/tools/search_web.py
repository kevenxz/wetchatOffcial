"""Search web pages from structured queries with authority-aware metadata."""
from __future__ import annotations

import asyncio
import os
import re
import time
from urllib.parse import parse_qs, unquote, urlparse

import httpx
import structlog
from bs4 import BeautifulSoup

from workflow.state import WorkflowState

logger = structlog.get_logger(__name__)

MEDIA_DOMAINS = {
    "techcrunch.com",
    "theverge.com",
    "wired.com",
    "reuters.com",
    "bloomberg.com",
    "ft.com",
    "wsj.com",
    "mittechnologyreview.com",
    "cnbc.com",
    "venturebeat.com",
    "36kr.com",
    "geekpark.net",
    "ifanr.com",
}
INSTITUTION_DOMAINS = {
    "mckinsey.com",
    "gartner.com",
    "forrester.com",
    "cbinsights.com",
    "idc.com",
    "stanford.edu",
    "mit.edu",
}
RESEARCH_DOMAINS = {
    "arxiv.org",
    "openreview.net",
    "nature.com",
    "science.org",
    "paperswithcode.com",
}
COMMUNITY_DOMAINS = {
    "medium.com",
    "reddit.com",
    "zhihu.com",
    "juejin.cn",
    "dev.to",
    "csdn.net",
    "substack.com",
}
AGGREGATOR_DOMAINS = {
    "news.ycombinator.com",
}
DOC_HINTS = ("docs.", "developer.", "developers.", "platform.", "api.", "/docs", "/api", "/developers")
STOPWORDS = {"the", "and", "for", "with", "from", "that", "this", "latest", "news", "analysis", "official", "blog"}


async def _search_google(query: str, api_key: str) -> list[dict]:
    url = "https://serpapi.com/search"
    params = {"q": query, "api_key": api_key, "engine": "google", "num": 6}
    async with httpx.AsyncClient(timeout=12.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    results: list[dict] = []
    for item in data.get("organic_results", []):
        link = item.get("link")
        if link:
            results.append(
                {
                    "url": link,
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet", ""),
                }
            )
    return results


async def _search_bing(query: str, api_key: str) -> list[dict]:
    url = "https://api.bing.microsoft.com/v7.0/search"
    headers = {"Ocp-Apim-Subscription-Key": api_key}
    params = {"q": query, "count": 6}
    async with httpx.AsyncClient(timeout=12.0) as client:
        resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()

    results: list[dict] = []
    for item in data.get("webPages", {}).get("value", []):
        link = item.get("url")
        if link:
            results.append(
                {
                    "url": link,
                    "title": item.get("name", ""),
                    "snippet": item.get("snippet", ""),
                }
            )
    return results


def _decode_duckduckgo_link(raw_url: str) -> str:
    if not raw_url:
        return ""
    if raw_url.startswith("//"):
        raw_url = f"https:{raw_url}"
    if raw_url.startswith("/l/?"):
        parsed = urlparse(raw_url)
        uddg = parse_qs(parsed.query).get("uddg", [])
        if uddg:
            return unquote(uddg[0])
    if raw_url.startswith("http"):
        return raw_url
    return ""


async def _search_duckduckgo(query: str) -> list[dict]:
    url = "https://html.duckduckgo.com/html/"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    }
    async with httpx.AsyncClient(timeout=12.0, headers=headers, follow_redirects=True) as client:
        resp = await client.get(url, params={"q": query})
        resp.raise_for_status()
        html = resp.text

    soup = BeautifulSoup(html, "html.parser")
    results: list[dict] = []
    for item in soup.select("div.result"):
        anchor = item.select_one("a.result__a")
        if anchor is None:
            continue
        link = _decode_duckduckgo_link(anchor.get("href", ""))
        if not link:
            continue
        snippet = item.select_one(".result__snippet")
        results.append(
            {
                "url": link,
                "title": anchor.get_text(" ", strip=True),
                "snippet": snippet.get_text(" ", strip=True) if snippet else "",
            }
        )
        if len(results) >= 6:
            break
    return results


async def _call_provider_with_retry(provider_name: str, provider_fn, query: str, provider_key: str | None = None) -> list[dict]:
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            if provider_key is None:
                return await provider_fn(query)
            return await provider_fn(query, provider_key)
        except Exception:
            if attempt >= max_attempts:
                raise
            await asyncio.sleep(2 ** (attempt - 1))


def _normalize_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    normalized = f"{parsed.scheme}://{parsed.netloc.lower()}{path}"
    if parsed.query:
        normalized = f"{normalized}?{parsed.query}"
    return normalized


def _domain(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def _query_tokens(query: str) -> set[str]:
    tokens = {
        token
        for token in re.findall(r"[a-z0-9]{3,}", query.lower())
        if token not in STOPWORDS
    }
    return tokens


def _classify_source_type(domain: str, url: str) -> str:
    if domain == "github.com":
        return "github"
    if domain in RESEARCH_DOMAINS:
        return "research"
    if domain in MEDIA_DOMAINS:
        return "media"
    if domain in INSTITUTION_DOMAINS:
        return "institution"
    if domain in COMMUNITY_DOMAINS:
        return "community"
    if domain in AGGREGATOR_DOMAINS:
        return "aggregator"
    lowered_url = url.lower()
    if any(hint in domain or hint in lowered_url for hint in DOC_HINTS):
        return "documentation"
    return "unknown"


def _authority_score(source_type: str, domain: str) -> float:
    if source_type == "official":
        return 0.96
    if source_type == "documentation":
        return 0.94
    if source_type == "github":
        return 0.92
    if source_type == "research":
        return 0.91
    if source_type == "media":
        return 0.86
    if source_type == "institution":
        return 0.85
    if source_type == "community":
        return 0.67
    if source_type == "aggregator":
        return 0.58
    if domain.endswith(".gov") or domain.endswith(".edu"):
        return 0.88
    return 0.7


def _official_bonus(query: str, domain: str, source_type: str) -> float:
    if source_type in {"documentation", "github"}:
        return 0.08
    tokens = _query_tokens(query)
    if any(token in domain for token in tokens):
        return 0.12
    return 0.0


def _relevance_score(query: str, title: str, snippet: str) -> float:
    tokens = _query_tokens(query)
    if not tokens:
        return 0.6
    haystack = f"{title} {snippet}".lower()
    hit_count = sum(1 for token in tokens if token in haystack)
    return round(min(1.0, 0.45 + hit_count * 0.12), 4)


def _freshness_score(title: str, snippet: str, url: str) -> float:
    text = f"{title} {snippet} {url}"
    if "2026" in text:
        return 0.1
    if "2025" in text:
        return 0.08
    if "2024" in text:
        return 0.05
    return 0.02


def _originality_score(source_type: str) -> float:
    if source_type in {"official", "documentation", "github", "research"}:
        return 0.92
    if source_type in {"institution", "media"}:
        return 0.76
    if source_type == "aggregator":
        return 0.35
    return 0.55


def _risk_penalty(source_type: str, title: str, snippet: str) -> float:
    text = f"{title} {snippet}".lower()
    penalty = 0.0
    if source_type in {"community", "aggregator", "unknown"}:
        penalty += 0.08
    if any(token in text for token in ("震惊", "爆炸", "必看", "颠覆", "guaranteed", "shocking")):
        penalty += 0.08
    return min(0.25, penalty)


def _normalize_search_item(query: str, intent: str, provider: str, raw_item: dict) -> dict | None:
    url = raw_item.get("url", "").strip()
    if not url.startswith("http"):
        return None
    normalized_url = _normalize_url(url)
    domain = _domain(normalized_url)
    source_type = _classify_source_type(domain, normalized_url)
    official_bonus = _official_bonus(query, domain, source_type)
    if official_bonus >= 0.12 and source_type == "unknown":
        source_type = "official"
    authority_score = _authority_score(source_type, domain)
    relevance_score = _relevance_score(query, raw_item.get("title", ""), raw_item.get("snippet", ""))
    freshness_score = _freshness_score(raw_item.get("title", ""), raw_item.get("snippet", ""), normalized_url)
    originality_score = _originality_score(source_type)
    content_depth_score = 0.72 if len(raw_item.get("snippet", "")) >= 80 else 0.5
    cross_source_score = 0.0
    risk_penalty = _risk_penalty(source_type, raw_item.get("title", ""), raw_item.get("snippet", ""))
    duplicate_penalty = 0.0
    final_score = (
        authority_score * 0.34
        + relevance_score * 0.25
        + freshness_score * 0.08
        + originality_score * 0.16
        + content_depth_score * 0.12
        + official_bonus
        + cross_source_score * 0.05
        - risk_penalty
        - duplicate_penalty
    )
    return {
        "query": query,
        "query_intent": intent,
        "url": normalized_url,
        "title": raw_item.get("title", "").strip(),
        "snippet": raw_item.get("snippet", "").strip(),
        "domain": domain,
        "provider": provider,
        "source_type": source_type,
        "authority_score": authority_score,
        "relevance_score": relevance_score,
        "freshness_score": freshness_score,
        "originality_score": originality_score,
        "cross_source_score": cross_source_score,
        "content_depth_score": content_depth_score,
        "risk_penalty": risk_penalty,
        "duplicate_penalty": duplicate_penalty,
        "official_bonus": official_bonus,
        "final_score": round(max(0.0, min(1.0, final_score)), 4),
    }


def _dedupe_results(results: list[dict]) -> list[dict]:
    deduped: list[dict] = []
    seen: set[str] = set()
    for item in results:
        normalized_url = item.get("url")
        if not normalized_url or normalized_url in seen:
            continue
        seen.add(normalized_url)
        deduped.append(item)
    return deduped


async def search_web_node(state: WorkflowState) -> dict:
    """Search the web using provider APIs and DuckDuckGo fallback."""
    task_id = state["task_id"]
    search_queries = state.get("search_queries") or [{"query": state["keywords"], "intent": "default", "priority": 1}]

    start_time = time.monotonic()
    logger.info(
        "skill_start",
        task_id=task_id,
        skill="search_web",
        status="running",
        query_count=len(search_queries),
    )

    serpapi_key = os.getenv("SERPAPI_API_KEY") or os.getenv("GOOGLE_SEARCH_API_KEY")
    bing_api_key = os.getenv("BING_SEARCH_API_KEY")

    provider_errors: list[str] = []
    raw_results: list[dict] = []

    for search_query in search_queries[:7]:
        if isinstance(search_query, str):
            query = search_query
            intent = "default"
        else:
            query = search_query.get("query", "")
            intent = search_query.get("intent", "default")

        query_results: list[dict] = []
        for provider_name, provider_fn, provider_key in [
            ("serpapi_google", _search_google, serpapi_key),
            ("bing", _search_bing, bing_api_key),
        ]:
            if not provider_key:
                continue
            try:
                logger.info("search_web_provider", task_id=task_id, provider=provider_name, query=query)
                provider_items = await _call_provider_with_retry(provider_name, provider_fn, query, provider_key)
                query_results.extend(
                    filter(
                        None,
                        [
                            _normalize_search_item(query, intent, provider_name, item)
                            for item in provider_items
                        ],
                    )
                )
            except Exception as exc:  # noqa: BLE001
                provider_errors.append(f"{provider_name}:{exc}")
                logger.warning(
                    "search_web_provider_failed",
                    task_id=task_id,
                    provider=provider_name,
                    query=query,
                    error=str(exc),
                )

        try:
            logger.info("search_web_provider", task_id=task_id, provider="duckduckgo", query=query)
            ddg_items = await _call_provider_with_retry("duckduckgo", _search_duckduckgo, query)
            query_results.extend(
                filter(
                    None,
                    [_normalize_search_item(query, intent, "duckduckgo", item) for item in ddg_items],
                )
            )
        except Exception as exc:  # noqa: BLE001
            provider_errors.append(f"duckduckgo:{exc}")
            logger.warning(
                "search_web_provider_failed",
                task_id=task_id,
                provider="duckduckgo",
                query=query,
                error=str(exc),
            )

        raw_results.extend(query_results)
        await asyncio.sleep(0.1)

    deduped_results = _dedupe_results(raw_results)
    duration_ms = round((time.monotonic() - start_time) * 1000)

    if not deduped_results:
        final_error = "未能搜索到有效结果"
        if provider_errors:
            final_error = f"{final_error}: {' | '.join(provider_errors)}"
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
        result_count=len(deduped_results),
    )

    return {
        "status": "running",
        "current_skill": "search_web",
        "progress": 52,
        "search_results": deduped_results,
        "retry_count": 0,
    }
