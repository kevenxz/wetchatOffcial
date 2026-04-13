"""TopHub scraping client used by hotspot capture workflow."""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
import structlog
from bs4 import BeautifulSoup

logger = structlog.get_logger(__name__)

TOPHUB_BASE_URL = "https://tophub.today"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _normalize_path(path: str) -> str:
    cleaned = _clean_text(path)
    if not cleaned:
        return ""
    if cleaned.startswith(("https://", "http://")):
        parsed = urlsplit(cleaned)
        cleaned = parsed.path or "/"
    if not cleaned.startswith("/"):
        cleaned = f"/{cleaned.lstrip('/')}"
    if cleaned != "/" and "?" not in cleaned:
        cleaned = cleaned.rstrip("/")
    return cleaned


def _parse_rank(value: str) -> int | None:
    match = re.search(r"\d+", value or "")
    if not match:
        return None
    rank = int(match.group(0))
    return rank if rank > 0 else None


def parse_hot_value(extra_text: str | None) -> float | None:
    """Parse extra text into numeric heat value when possible."""
    text = _clean_text(extra_text)
    if not text:
        return None

    normalized = text.replace(",", "").replace("，", "").replace("+", "")
    match = re.search(r"(\d+(?:\.\d+)?)\s*([万亿wWkK]?)", normalized)
    if not match:
        return None

    base = float(match.group(1))
    unit = match.group(2).lower()
    if unit == "万" or unit == "w":
        return base * 10_000
    if unit == "亿":
        return base * 100_000_000
    if unit == "k":
        return base * 1_000
    return base


def _resolve_url(base_url: str, href: str) -> str:
    if href.startswith(("http://", "https://")):
        return href
    return urljoin(base_url, href)


class TopHubClient:
    """A lightweight TopHub HTML client with retry and parser helpers."""

    def __init__(
        self,
        *,
        base_url: str = TOPHUB_BASE_URL,
        timeout: float = 12.0,
        max_retries: int = 3,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

    async def _fetch_html(self, path: str) -> str:
        target = path if path.startswith(("http://", "https://")) else _resolve_url(f"{self.base_url}/", path)
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout,
                    headers=DEFAULT_HEADERS,
                    follow_redirects=True,
                ) as client:
                    resp = await client.get(target)
                    resp.raise_for_status()
                    return resp.text
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning(
                    "tophub_fetch_retry",
                    url=target,
                    attempt=attempt,
                    max_retries=self.max_retries,
                    error=str(exc),
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(0.3 * attempt)
        assert last_error is not None
        raise last_error

    async def fetch_category_platforms(self, category: str, *, limit: int = 20) -> list[dict[str, Any]]:
        """Discover platform entries from a TopHub category page."""
        cleaned_category = _clean_text(category).strip("/")
        if not cleaned_category:
            return []

        html = await self._fetch_html(f"/c/{cleaned_category}")
        soup = BeautifulSoup(html, "html.parser")

        platforms: list[dict[str, Any]] = []
        seen_paths: set[str] = set()
        for anchor in soup.select("a[href^='/n/']"):
            raw_path = anchor.get("href", "")
            path = _normalize_path(raw_path)
            if not path or path in seen_paths:
                continue
            name = _clean_text(anchor.get_text(" ", strip=True))
            if len(name) < 2:
                continue
            seen_paths.add(path)
            platforms.append(
                {
                    "name": name,
                    "path": path,
                    "enabled": True,
                    "weight": 1.0,
                    "category": cleaned_category,
                }
            )
            if len(platforms) >= limit:
                break
        return platforms

    async def fetch_platform_hot_items(
        self,
        *,
        platform_name: str,
        platform_path: str,
        category: str = "",
        top_n: int = 10,
        platform_weight: float = 1.0,
    ) -> list[dict[str, Any]]:
        """Fetch and parse one TopHub platform ranking page."""
        path = _normalize_path(platform_path)
        if not path:
            return []

        html = await self._fetch_html(path)
        soup = BeautifulSoup(html, "html.parser")
        items: list[dict[str, Any]] = []
        seen_signatures: set[str] = set()

        # Strategy 1: parse table rows.
        for row in soup.select("tbody tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            rank = _parse_rank(cells[0].get_text(" ", strip=True))
            title_anchor = cells[1].find("a", href=True) or row.find("a", href=True)
            if title_anchor is None:
                continue
            title = _clean_text(title_anchor.get_text(" ", strip=True))
            if len(title) < 2:
                continue
            href = _clean_text(title_anchor.get("href"))
            if not href:
                continue
            extra_text = _clean_text(cells[2].get_text(" ", strip=True) if len(cells) > 2 else "")
            signature = f"{title}::{href}"
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)
            items.append(
                {
                    "source": "tophub",
                    "category": _clean_text(category),
                    "platform_name": _clean_text(platform_name),
                    "platform_path": path,
                    "platform_weight": float(platform_weight),
                    "title": title,
                    "url": _resolve_url(f"{self.base_url}/", href),
                    "rank": rank or (len(items) + 1),
                    "extra_text": extra_text,
                    "hot_value": parse_hot_value(extra_text),
                    "captured_at": _utc_now_iso(),
                }
            )

        # Strategy 2: generic fallback for non-table page layouts.
        if not items:
            for anchor in soup.select("a[href]"):
                href = _clean_text(anchor.get("href"))
                if not href or href.startswith(("/n/", "/c/")):
                    continue
                title = _clean_text(anchor.get_text(" ", strip=True))
                if len(title) < 6:
                    continue
                container = anchor.parent
                context_text = _clean_text(container.get_text(" ", strip=True) if container else title)
                rank = _parse_rank(context_text) or (len(items) + 1)
                extra_text = context_text.replace(title, "").strip(" -|:：")
                signature = f"{title}::{href}"
                if signature in seen_signatures:
                    continue
                seen_signatures.add(signature)
                items.append(
                    {
                        "source": "tophub",
                        "category": _clean_text(category),
                        "platform_name": _clean_text(platform_name),
                        "platform_path": path,
                        "platform_weight": float(platform_weight),
                        "title": title,
                        "url": _resolve_url(f"{self.base_url}/", href),
                        "rank": rank,
                        "extra_text": extra_text,
                        "hot_value": parse_hot_value(extra_text),
                        "captured_at": _utc_now_iso(),
                    }
                )

        return sorted(items, key=lambda item: int(item.get("rank") or 9999))[:top_n]
