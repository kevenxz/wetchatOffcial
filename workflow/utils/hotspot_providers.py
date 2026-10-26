"""Hotspot provider registry and adapters."""
from __future__ import annotations

import asyncio
import os
import random
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
import structlog
from bs4 import BeautifulSoup

from workflow.utils.newsnow_catalog import newsnow_domains_for, newsnow_platform_catalog
from workflow.utils.tophub_client import TopHubClient, list_builtin_platforms

logger = structlog.get_logger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

# newsnow serves the multi-platform hot lists that TrendRadar consumes. Configurable so
# a self-hosted newsnow instance can be used instead of the public one.
NEWSNOW_API_BASE = (os.getenv("NEWSNOW_API_BASE") or "https://newsnow.busiyi.world/api").rstrip("/")
NEWSNOW_TIMEOUT_SECONDS = 12.0
# Statuses the upstream returns. `cache` means it served a recent cached snapshot rather
# than re-crawling; that data is still usable, but rejecting it would drop whole platforms.
NEWSNOW_ACCEPTED_STATUSES = frozenset({"success", "cache"})
NEWSNOW_MAX_RETRIES = 2


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
    # A bare identifier (no scheme) is a newsnow platform id, e.g. "weibo" or "cls-hot".
    if path and "/" not in path:
        return "newsnow"
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


def _newsnow_platform_id(platform: dict[str, Any]) -> str:
    """Resolve the upstream platform id for a newsnow entry."""
    return (
        _clean_text(platform.get("provider_id"))
        or _clean_text(platform.get("path"))
        or _clean_text(platform.get("url"))
    )


def _link_is_expected_domain(url: str, domains: tuple[str, ...]) -> bool:
    """Whether a returned link is HTTPS and belongs to the platform's expected domain.

    The hot lists come from a third-party API, so a compromised or spoofed response could
    point our downstream fetching at arbitrary hosts. Parsing with ``urlsplit`` and
    comparing the *hostname* (not the raw string) is what stops a
    ``https://baidu.com@evil.com/`` style bypass, where the userinfo section reads like a
    trusted domain.
    """
    if not domains:
        return True
    parsed = urlsplit(str(url or ""))
    if parsed.scheme != "https":
        return False
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return False
    return any(hostname == domain.lower() or hostname.endswith("." + domain.lower()) for domain in domains)


class NewsNowHotspotProvider(HotspotProvider):
    """Fetch one platform's hot list from the newsnow API.

    This is the endpoint TrendRadar itself consumes, so a single structured JSON call
    replaces HTML scraping and covers the same 16 platforms. The behaviour below is
    ported from TrendRadar's ``trendradar/crawler/fetcher.py`` (GPL-3.0) as *behaviour*,
    not code: status validation, jittered retry, invalid-title guards, duplicate title
    ranking, and link-domain safety.
    """

    source_type = "newsnow"

    async def fetch_platform_items(
        self,
        platform: dict[str, Any],
        *,
        top_n: int,
    ) -> list[dict[str, Any]]:
        platform_id = _newsnow_platform_id(platform)
        if not platform_id:
            return []

        payload = await self._fetch_payload(platform_id, platform_name=_clean_text(platform.get("name")))
        if payload is None:
            return []

        items = payload.get("items")
        if not isinstance(items, list):
            logger.warning("newsnow_items_missing", platform_id=platform_id)
            return []

        # Same title may appear at several ranks; keep one candidate and record all ranks.
        ranked: dict[str, list[int]] = {}
        details: dict[str, dict[str, str]] = {}
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            raw_title = item.get("title")
            # Require a real string: the upstream has returned numbers and nulls, and
            # stringifying them turns a broken payload into headlines like "1.5".
            # Downstream title handling also assumes text.
            if not isinstance(raw_title, str):
                continue
            title = _clean_text(raw_title)
            if not title:
                continue
            ranked.setdefault(title, []).append(index)
            details.setdefault(
                title,
                {
                    "url": _clean_text(item.get("url")),
                    "mobile_url": _clean_text(item.get("mobileUrl")),
                    "extra_text": _newsnow_extra_text(item.get("extra")),
                },
            )

        domains = newsnow_domains_for(platform_id)
        candidates: list[dict[str, Any]] = []
        for title, ranks in list(ranked.items())[: max(0, top_n)]:
            detail = details.get(title, {})
            url = detail.get("url") or detail.get("mobile_url")
            if url and not _link_is_expected_domain(url, domains):
                logger.warning(
                    "newsnow_link_domain_rejected",
                    platform_id=platform_id,
                    url=url[:120],
                    expected=list(domains),
                )
                continue
            candidate = _candidate_from_platform(
                platform,
                title=title,
                url=url or "",
                rank=ranks[0],
                extra_text=detail.get("extra_text") or "",
            )
            candidate["all_ranks"] = ranks
            candidate["appearances"] = len(ranks)
            candidates.append(candidate)

        logger.debug(
            "newsnow_platform_fetched",
            platform_id=platform_id,
            status=str(payload.get("status") or ""),
            returned=len(candidates),
        )
        return candidates

    async def _fetch_payload(self, platform_id: str, *, platform_name: str = "") -> dict[str, Any] | None:
        """GET one platform, retrying transient failures with jittered backoff."""
        url = f"{NEWSNOW_API_BASE}/s?id={platform_id}&latest"
        headers = {
            **DEFAULT_HEADERS,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        last_error = ""
        for attempt in range(NEWSNOW_MAX_RETRIES + 1):
            if attempt:
                # Jitter matters: 16 platforms are fetched together, and a fixed delay
                # would keep them in lockstep against the upstream.
                await asyncio.sleep(random.uniform(0.4, 1.2) * attempt)
            try:
                async with httpx.AsyncClient(timeout=NEWSNOW_TIMEOUT_SECONDS, headers=headers) as client:
                    response = await client.get(url)
                    response.raise_for_status()
                    payload = response.json()
                if not isinstance(payload, dict):
                    last_error = "response is not a JSON object"
                    continue
                status = str(payload.get("status") or "").strip().lower()
                if status not in NEWSNOW_ACCEPTED_STATUSES:
                    last_error = f"unexpected status {status!r}"
                    continue
                return payload
            except Exception as exc:  # noqa: BLE001
                last_error = f"{type(exc).__name__}: {exc}"
        logger.warning(
            "newsnow_platform_failed",
            platform_id=platform_id,
            platform_name=platform_name,
            attempts=NEWSNOW_MAX_RETRIES + 1,
            error=last_error,
            exc_info=True,
        )
        return None


def _newsnow_extra_text(extra: Any) -> str:
    """Extract a human-readable summary from newsnow's ``extra`` field.

    Shape varies per platform (``hover`` on baidu, ``date`` on ifeng, ``icon`` on most),
    so only descriptive text is taken.
    """
    if not isinstance(extra, dict):
        return ""
    for key in ("hover", "info", "desc", "description"):
        value = _clean_text(extra.get(key))
        if value:
            return value
    return ""


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
        logger.warning("hotspot_feed_parse_failed", platform=platform.get("name"), exc_info=True)
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
    if normalized == "newsnow":
        return NewsNowHotspotProvider()
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

    # The newsnow platforms lead: one structured JSON call per platform beats scraping
    # ranking HTML, and it is where the retry/timeout failures were coming from.
    items.extend(newsnow_platform_catalog(categories))

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
