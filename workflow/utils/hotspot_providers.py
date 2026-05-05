"""Hotspot provider registry and adapters."""
from __future__ import annotations

import asyncio
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

import httpx
import structlog
from bs4 import BeautifulSoup

from workflow.utils.tophub_client import TopHubClient, list_builtin_platforms

logger = structlog.get_logger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _platform_source(platform: dict[str, Any]) -> str:
    source = _clean_text(platform.get("source") or platform.get("source_type") or "")
    if source:
        return source
    path = _clean_text(platform.get("path") or platform.get("url") or "")
    if path.startswith(("http://", "https://")):
        if "rss" in path.lower() or "feed" in path.lower():
            return "rss_or_feed"
        return "ranking_page"
    return "tophub"


def _platform_endpoint(platform: dict[str, Any]) -> str:
    return _clean_text(platform.get("url") or platform.get("feed_url") or platform.get("path") or "")


class HotspotProvider:
    """Base provider adapter."""

    source_type = ""

    async def fetch_platform_items(
        self,
        platform: dict[str, Any],
        *,
        top_n: int,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError


class TopHubHotspotProvider(HotspotProvider):
    """Fetch items from a TopHub platform page."""

    source_type = "tophub"

    def __init__(self, client: TopHubClient | None = None) -> None:
        self.client = client or TopHubClient()

    async def fetch_platform_items(
        self,
        platform: dict[str, Any],
        *,
        top_n: int,
    ) -> list[dict[str, Any]]:
        return await self.client.fetch_platform_hot_items(
            platform_name=_clean_text(platform.get("name")),
            platform_path=_clean_text(platform.get("path")),
            category=_clean_text(platform.get("category")),
            top_n=top_n,
            platform_weight=float(platform.get("weight") or 1.0),
        )


class RssHotspotProvider(HotspotProvider):
    """Fetch items from a public RSS/Atom feed."""

    source_type = "rss_or_feed"

    async def fetch_platform_items(
        self,
        platform: dict[str, Any],
        *,
        top_n: int,
    ) -> list[dict[str, Any]]:
        endpoint = _platform_endpoint(platform)
        if not endpoint:
            return []
        async with httpx.AsyncClient(timeout=12.0, headers=DEFAULT_HEADERS, follow_redirects=True) as client:
            response = await client.get(endpoint)
            response.raise_for_status()
        return _parse_feed_items(response.text, platform, top_n=top_n)


class HtmlRankingHotspotProvider(HotspotProvider):
    """Fetch items from a public HTML ranking page using configured selectors."""

    source_type = "ranking_page"

    async def fetch_platform_items(
        self,
        platform: dict[str, Any],
        *,
        top_n: int,
    ) -> list[dict[str, Any]]:
        endpoint = _platform_endpoint(platform)
        if not endpoint:
            return []
        async with httpx.AsyncClient(timeout=12.0, headers=DEFAULT_HEADERS, follow_redirects=True) as client:
            response = await client.get(endpoint)
            response.raise_for_status()
        return _parse_html_ranking_items(response.text, endpoint, platform, top_n=top_n)


def _parse_feed_items(xml_text: str, platform: dict[str, Any], *, top_n: int) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        logger.warning("hotspot_feed_parse_failed", platform=platform.get("name"))
        return []

    items: list[dict[str, Any]] = []
    entries = list(root.findall(".//item")) or list(root.findall(".//{http://www.w3.org/2005/Atom}entry"))
    for index, entry in enumerate(entries[:top_n], start=1):
        title = _clean_text(_first_xml_text(entry, ["title", "{http://www.w3.org/2005/Atom}title"]))
        if not title:
            continue
        link = _clean_text(_first_xml_text(entry, ["link"]))
        if not link:
            atom_link = entry.find("{http://www.w3.org/2005/Atom}link")
            link = _clean_text(atom_link.get("href") if atom_link is not None else "")
        summary = _clean_text(
            _first_xml_text(
                entry,
                ["description", "summary", "{http://www.w3.org/2005/Atom}summary", "{http://www.w3.org/2005/Atom}content"],
            )
        )
        items.append(_candidate_from_platform(platform, title=title, url=link, rank=index, extra_text=summary))
    return items


def _first_xml_text(entry: ET.Element, tags: list[str]) -> str:
    for tag in tags:
        node = entry.find(tag)
        if node is not None and node.text:
            return node.text
    return ""


def _parse_html_ranking_items(html: str, base_url: str, platform: dict[str, Any], *, top_n: int) -> list[dict[str, Any]]:
    options = dict(platform.get("parser_options") or {})
    item_selector = _clean_text(options.get("item_selector")) or "article, li, tbody tr, .item, .news-item"
    title_selector = _clean_text(options.get("title_selector")) or "a"
    extra_selector = _clean_text(options.get("extra_selector"))
    soup = BeautifulSoup(html, "html.parser")

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for node in soup.select(item_selector):
        title_node = node.select_one(title_selector) if title_selector else node
        if title_node is None:
            continue
        title = _clean_text(title_node.get_text(" ", strip=True))
        href = _clean_text(title_node.get("href") if hasattr(title_node, "get") else "")
        if len(title) < 2:
            continue
        signature = f"{title}::{href}"
        if signature in seen:
            continue
        seen.add(signature)
        extra_text = ""
        if extra_selector:
            extra_node = node.select_one(extra_selector)
            extra_text = _clean_text(extra_node.get_text(" ", strip=True) if extra_node else "")
        if not extra_text:
            extra_text = _clean_text(node.get_text(" ", strip=True)).replace(title, "").strip()
        items.append(
            _candidate_from_platform(
                platform,
                title=title,
                url=urljoin(base_url, href) if href else base_url,
                rank=len(items) + 1,
                extra_text=extra_text,
            )
        )
        if len(items) >= top_n:
            break
    return items


def _candidate_from_platform(
    platform: dict[str, Any],
    *,
    title: str,
    url: str,
    rank: int,
    extra_text: str = "",
) -> dict[str, Any]:
    source = _platform_source(platform)
    endpoint = _platform_endpoint(platform)
    return {
        "source": source,
        "provider_id": _clean_text(platform.get("provider_id")) or source,
        "category": _clean_text(platform.get("category")),
        "platform_name": _clean_text(platform.get("name")),
        "platform_path": endpoint,
        "platform_weight": float(platform.get("weight") or 1.0),
        "title": title,
        "url": url,
        "rank": rank,
        "extra_text": extra_text,
        "hot_value": None,
        "captured_at": _utc_now_iso(),
    }


def get_hotspot_provider(source_type: str) -> HotspotProvider:
    """Return the provider adapter for one source type."""
    normalized = _clean_text(source_type) or "tophub"
    if normalized == "rss_or_feed":
        return RssHotspotProvider()
    if normalized == "ranking_page":
        return HtmlRankingHotspotProvider()
    return TopHubHotspotProvider()


async def fetch_hotspot_platform_items(platform: dict[str, Any], *, top_n: int) -> list[dict[str, Any]]:
    """Fetch one platform with the right adapter."""
    provider = get_hotspot_provider(_platform_source(platform))
    return await provider.fetch_platform_items(platform, top_n=top_n)


async def discover_hotspot_platforms(categories: list[str]) -> list[dict[str, Any]]:
    """Return builtin and discoverable hotspot platforms."""
    builtin = list_builtin_hotspot_platforms(categories)
    if builtin:
        return builtin
    if not categories:
        return list_builtin_hotspot_platforms([])

    client = TopHubClient()
    discovered_results = await asyncio.gather(
        *[client.fetch_category_platforms(category) for category in categories[:5]],
        return_exceptions=True,
    )
    discovered: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for result in discovered_results:
        if isinstance(result, Exception):
            continue
        for item in result:
            path = _clean_text(item.get("path"))
            if not path or path in seen_paths:
                continue
            seen_paths.add(path)
            discovered.append({**item, "source": "tophub", "provider_id": "tophub"})
    return discovered


def list_builtin_hotspot_platforms(categories: list[str] | None = None, *, limit: int | None = None) -> list[dict[str, Any]]:
    """Return builtin platform presets across providers."""
    items: list[dict[str, Any]] = []
    for item in list_builtin_platforms(categories):
        items.append({**item, "source": "tophub", "provider_id": "tophub"})

    presets = [
        {
            "name": "36氪快讯",
            "path": "https://36kr.com/feed-newsflash",
            "source": "rss_or_feed",
            "provider_id": "36kr_newsflash",
            "category": "科技",
            "weight": 1.1,
            "enabled": True,
        },
        {
            "name": "华尔街日报全球新闻",
            "path": "https://feeds.content.dowjones.io/public/rss/RSSWorldNews",
            "source": "rss_or_feed",
            "provider_id": "wsj_world_news",
            "category": "财经",
            "weight": 1.1,
            "enabled": True,
        },
    ]
    normalized_categories = {_clean_text(category).lower() for category in categories or [] if _clean_text(category)}
    for preset in presets:
        if normalized_categories:
            tokens = {_clean_text(preset.get("category")).lower(), _clean_text(preset.get("name")).lower()}
            if not (tokens & normalized_categories):
                continue
        items.append(dict(preset))
    if limit is not None:
        return items[:limit]
    return items
