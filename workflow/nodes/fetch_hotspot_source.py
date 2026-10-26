"""Fetch the hotspot's own source article before searching.

The pipeline used to jump straight from "which hotspot" to a generic query template
(``{topic} 官方 公告 原文`` and friends), so every hotspot produced near-identical
research material and therefore near-identical article structure. This node reads the
article the hotspot is actually about, and derives follow-up queries from its own
content, so the narrative spine comes from the story rather than from a template.

The node never fails the workflow: when the source cannot be resolved or fetched it
records ``hotspot_source_status`` and lets the search stage carry on.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx
import structlog

from workflow import runtime_settings
from workflow.state import WorkflowState
from workflow.tools.fetch_extract import _fetch_and_extract_single
from workflow.utils.source_filter import filter_sources

logger = structlog.get_logger(__name__)

# Ranking pages (TopHub and similar) wrap outbound links in a redirect.
_REDIRECT_HOSTS = ("tophub.today", "tophub.com")
_REDIRECT_PARAMS = ("url", "target", "link", "goto")

# Signals worth turning into a follow-up search query.
_NUMBER_SIGNAL = re.compile(
    r"\d+(?:\.\d+)?\s*%|\d{4}\s*年|\d+(?:\.\d+)?\s*(?:亿元|万元|亿|万美元|亿美元|万台|台|倍)"
)
_QUOTED_NAME = re.compile(r"[《“\"]([^》”\"]{2,20})[》”\"]")

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def resolve_source_url(url: str) -> str:
    """Resolve a ranking-page redirect to the original article URL."""
    raw = str(url or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
    except ValueError:
        return raw

    host = parsed.netloc.lower()
    if not any(marker in host for marker in _REDIRECT_HOSTS):
        return raw

    params = parse_qs(parsed.query)
    for key in _REDIRECT_PARAMS:
        for value in params.get(key) or []:
            candidate = unquote(str(value)).strip()
            if candidate.startswith(("http://", "https://")):
                return candidate
    return raw


def collect_source_urls(state: WorkflowState) -> list[str]:
    """Gather candidate original-article URLs for the selected hotspot."""
    candidates: list[str] = []

    def add(value: Any) -> None:
        text = str(value or "").strip()
        if not text:
            return
        resolved = resolve_source_url(text)
        if resolved and resolved not in candidates:
            candidates.append(resolved)

    selected_hotspot = dict(state.get("selected_hotspot") or {})
    add(selected_hotspot.get("url"))

    selected_topic = dict(state.get("selected_topic") or {})
    for value in list(selected_topic.get("source_cluster") or []):
        add(value)

    for candidate in list(state.get("hotspot_candidates") or [])[:3]:
        if isinstance(candidate, dict):
            add(candidate.get("url"))

    # A ranking-page URL that could not be unwrapped is not worth fetching.
    return [
        url
        for url in candidates
        if not any(marker in urlparse(url).netloc.lower() for marker in _REDIRECT_HOSTS)
    ]


def derive_source_queries(topic: str, title: str, text: str, *, limit: int = 4) -> list[dict[str, Any]]:
    """Derive follow-up search queries from the hotspot article's own content.

    Uses the concrete numbers and quoted names the article mentions, plus an exact
    title lookup, so research targets this story instead of a generic template.
    """
    queries: list[dict[str, Any]] = []

    def add(query: str, *, source_type: str, purpose: str) -> None:
        cleaned = " ".join(str(query or "").split())
        if not cleaned or len(cleaned) < 4:
            return
        if any(item["query"] == cleaned for item in queries):
            return
        queries.append(
            {
                "query": cleaned,
                "angle": "hotspot_source",
                "purpose": purpose,
                "source_type": source_type,
                "priority": len(queries),
            }
        )

    if title:
        add(f'"{title}"', source_type="media", purpose="按原文标题定位一手报道")

    signals: list[str] = []
    for match in _NUMBER_SIGNAL.findall(str(text or "")):
        token = match.strip()
        if token and token not in signals:
            signals.append(token)
        if len(signals) >= 3:
            break
    for signal in signals[:2]:
        add(f"{topic} {signal}", source_type="data", purpose="核对原文提到的具体数字")

    names = [match.strip() for match in _QUOTED_NAME.findall(str(text or ""))]
    for name in names[:1]:
        add(f"{topic} {name}", source_type="official", purpose="核对原文提到的机构或产品")

    return queries[:limit]


def _filter_hotspot_sources(topic: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only the hotspot sources that pass the shared relevance/quality gates."""
    if not items:
        return []
    view = [
        {
            "url": str(item.get("url") or "").strip(),
            "title": str(item.get("title") or "").strip(),
            "text": str(item.get("text") or "").strip(),
            "domain": str(item.get("domain") or "").strip(),
            "source_type": "official",
        }
        for item in items
    ]
    # Official floor: a hotspot's own article is primary evidence and may be brief.
    result = filter_sources(topic, view, min_survivors=1)
    kept_urls = {str(item.get("url") or "").strip() for item in result.kept}
    return [item for item in items if str(item.get("url") or "").strip() in kept_urls]


async def fetch_hotspot_source_node(state: WorkflowState) -> dict[str, Any]:
    """Fetch and read the hotspot's own article before the search stage runs."""
    task_id = str(state.get("task_id") or "")
    research_state = dict(state.get("research_state") or {})
    selected_topic = dict(state.get("selected_topic") or {})
    topic = str(
        selected_topic.get("title") or state.get("task_brief", {}).get("topic") or state.get("keywords") or ""
    ).strip()

    def result(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "running",
            "current_skill": "fetch_hotspot_source",
            "progress": 20,
            "research_state": {**research_state, **payload},
            **payload,
        }

    if not runtime_settings.hotspot_source_enabled():
        return result({"hotspot_source_status": "disabled", "hotspot_sources": [], "hotspot_source_queries": []})

    urls = collect_source_urls(state)
    if not urls:
        logger.info("hotspot_source_unavailable", task_id=task_id, reason="no_url")
        return result(
            {
                "hotspot_source_status": "unavailable",
                "hotspot_source_error": "no_source_url",
                "hotspot_sources": [],
                "hotspot_source_queries": [],
            }
        )

    timeout = httpx.Timeout(runtime_settings.llm_timeout_seconds())
    fetched: list[dict[str, Any]] = []
    errors: list[str] = []
    async with httpx.AsyncClient(headers={"User-Agent": _USER_AGENT}, timeout=timeout) as client:
        for url in urls[:3]:
            item = {"url": url, "title": "", "domain": urlparse(url).netloc.lower()}
            try:
                extracted = await _fetch_and_extract_single(item, client)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{url}: {exc}")
                continue
            if not extracted:
                errors.append(f"{url}: extract_failed")
                continue
            extracted["domain"] = urlparse(str(extracted.get("url") or url)).netloc.lower()
            extracted["source_type"] = "official"
            fetched.append(extracted)

    kept = _filter_hotspot_sources(topic, fetched)
    if not kept:
        status = "unavailable" if not fetched else "filtered_out"
        logger.warning(
            "hotspot_source_unavailable",
            task_id=task_id,
            status=status,
            fetched=len(fetched),
            errors=errors[:3],
        )
        return result(
            {
                "hotspot_source_status": status,
                "hotspot_source_error": "; ".join(errors[:3]) or None,
                "hotspot_sources": [],
                "hotspot_source_queries": [],
            }
        )

    primary = kept[0]
    queries = derive_source_queries(
        topic,
        str(primary.get("title") or ""),
        str(primary.get("text") or ""),
    )
    logger.info(
        "hotspot_source_ready",
        task_id=task_id,
        url=str(primary.get("url") or "")[:120],
        chars=len(str(primary.get("text") or "")),
        derived_queries=[item["query"] for item in queries],
    )
    return result(
        {
            "hotspot_source_status": "resolved",
            "hotspot_source_error": None,
            "hotspot_sources": kept,
            "hotspot_source_queries": queries,
        }
    )
