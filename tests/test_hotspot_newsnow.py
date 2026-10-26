"""Tests for the newsnow hotspot provider.

The behaviour under test was extracted from TrendRadar's fetcher
(``trendradar/crawler/fetcher.py``, GPL-3.0) rather than copied: status validation,
jittered retry, invalid-title guards, duplicate-title ranking, and link-domain safety.
Verified against the live API during development: 16/16 platforms returned data.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from workflow.utils.hotspot_providers import (
    NewsNowHotspotProvider,
    _link_is_expected_domain,
    _newsnow_extra_text,
    get_hotspot_provider,
)
from workflow.utils.newsnow_catalog import (
    NEWSNOW_PLATFORM_IDS,
    NEWSNOW_PLATFORMS,
    newsnow_domains_for,
    newsnow_platform_catalog,
)

PLATFORM = {
    "name": "微博热搜",
    "path": "weibo",
    "source": "newsnow",
    "provider_id": "weibo",
    "category": "社会",
    "weight": 1.1,
    "enabled": True,
}


def _payload(*items: dict, status: str = "success") -> str:
    return json.dumps({"status": status, "items": list(items)})


class _FakeResponse:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return json.loads(self.text)


def _client_returning(text: str, *, status_code: int = 200):
    """Patch httpx.AsyncClient so ``get`` returns a canned response."""
    response = _FakeResponse(text, status_code)
    client = MagicMock()
    client.get = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


# --------------------------------------------------------------------------- #
# catalogue
# --------------------------------------------------------------------------- #


def test_catalogue_exposes_all_sixteen_platforms() -> None:
    assert len(NEWSNOW_PLATFORM_IDS) == 16
    assert len(newsnow_platform_catalog([])) == 16
    assert newsnow_platform_catalog([])[0]["source"] == "newsnow"


def test_catalogue_entries_are_valid_hotspot_platforms() -> None:
    """The API validates these into HotspotPlatformConfig, so they must carry name+path."""
    from api.models import HotspotPlatformCatalogItem

    for item in newsnow_platform_catalog([]):
        parsed = HotspotPlatformCatalogItem.model_validate(item)
        assert parsed.source.value == "newsnow"
        assert parsed.name and parsed.path


def test_catalogue_can_be_filtered_by_category() -> None:
    finance = newsnow_platform_catalog(["财经"])
    assert finance
    assert all(item["category"] == "财经" for item in finance)


def test_every_platform_id_matches_its_catalogue_name() -> None:
    by_id = {item["id"]: item["name"] for item in NEWSNOW_PLATFORMS}
    for platform_id in NEWSNOW_PLATFORM_IDS:
        assert by_id[platform_id]


# --------------------------------------------------------------------------- #
# dispatch
# --------------------------------------------------------------------------- #


def test_registry_returns_the_newsnow_provider() -> None:
    assert isinstance(get_hotspot_provider("newsnow"), NewsNowHotspotProvider)


def test_bare_platform_id_is_recognised_as_newsnow() -> None:
    """A path with no scheme and no slash is an upstream platform id, not a TopHub path."""
    from workflow.utils.hotspot_providers import _platform_source

    assert _platform_source({"path": "weibo"}) == "newsnow"
    assert _platform_source({"path": "cls-hot"}) == "newsnow"
    # Real TopHub paths keep their existing meaning.
    assert _platform_source({"path": "/n/mproPpoq6O"}) == "tophub"
    assert _platform_source({"path": "https://x.com/feed.xml"}) == "rss_or_feed"


# --------------------------------------------------------------------------- #
# fetching
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_fetches_and_maps_items() -> None:
    client = _client_returning(
        _payload(
            {"title": "第一条热点", "url": "https://s.weibo.com/weibo?q=a"},
            {"title": "第二条热点", "url": "https://s.weibo.com/weibo?q=b"},
        )
    )
    with patch("workflow.utils.hotspot_providers.httpx.AsyncClient", return_value=client):
        items = await NewsNowHotspotProvider().fetch_platform_items(PLATFORM, top_n=10)

    assert [item["title"] for item in items] == ["第一条热点", "第二条热点"]
    assert [item["rank"] for item in items] == [1, 2]
    assert items[0]["source"] == "newsnow"
    assert items[0]["platform_name"] == "微博热搜"
    assert items[0]["platform_weight"] == pytest.approx(1.1)


@pytest.mark.asyncio
async def test_cached_status_is_accepted() -> None:
    """`cache` means the upstream served a recent snapshot; rejecting it would drop platforms."""
    client = _client_returning(_payload({"title": "缓存热点", "url": "https://s.weibo.com/x"}, status="cache"))
    with patch("workflow.utils.hotspot_providers.httpx.AsyncClient", return_value=client):
        items = await NewsNowHotspotProvider().fetch_platform_items(PLATFORM, top_n=5)

    assert len(items) == 1


@pytest.mark.asyncio
async def test_unexpected_status_is_rejected_after_retries() -> None:
    client = _client_returning(_payload({"title": "x", "url": "https://s.weibo.com/x"}, status="error"))
    with (
        patch("workflow.utils.hotspot_providers.httpx.AsyncClient", return_value=client),
        patch("workflow.utils.hotspot_providers.NEWSNOW_MAX_RETRIES", 0),
    ):
        items = await NewsNowHotspotProvider().fetch_platform_items(PLATFORM, top_n=5)

    assert items == []


@pytest.mark.asyncio
async def test_http_failure_returns_empty_and_never_raises() -> None:
    client = _client_returning("boom", status_code=502)
    with (
        patch("workflow.utils.hotspot_providers.httpx.AsyncClient", return_value=client),
        patch("workflow.utils.hotspot_providers.NEWSNOW_MAX_RETRIES", 0),
    ):
        items = await NewsNowHotspotProvider().fetch_platform_items(PLATFORM, top_n=5)

    assert items == []


@pytest.mark.asyncio
async def test_retry_recovers_from_a_transient_failure() -> None:
    """Jittered retry is ported behaviour: one bad response must not lose the platform."""
    good = _FakeResponse(_payload({"title": "重试成功", "url": "https://s.weibo.com/x"}))
    client = MagicMock()
    client.get = AsyncMock(side_effect=[RuntimeError("network blip"), good])
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("workflow.utils.hotspot_providers.httpx.AsyncClient", return_value=client),
        patch("workflow.utils.hotspot_providers.asyncio.sleep", new=AsyncMock()),
    ):
        items = await NewsNowHotspotProvider().fetch_platform_items(PLATFORM, top_n=5)

    assert [item["title"] for item in items] == ["重试成功"]
    assert client.get.await_count == 2


@pytest.mark.asyncio
async def test_invalid_titles_are_skipped() -> None:
    """Upstream has returned non-string titles before and crashed downstream handling."""
    client = _client_returning(
        _payload(
            {"title": None, "url": "https://s.weibo.com/a"},
            {"title": 1.5, "url": "https://s.weibo.com/b"},
            {"title": "   ", "url": "https://s.weibo.com/c"},
            {"title": "有效标题", "url": "https://s.weibo.com/d"},
        )
    )
    with patch("workflow.utils.hotspot_providers.httpx.AsyncClient", return_value=client):
        items = await NewsNowHotspotProvider().fetch_platform_items(PLATFORM, top_n=10)

    assert [item["title"] for item in items] == ["有效标题"]


@pytest.mark.asyncio
async def test_duplicate_titles_are_merged_and_all_ranks_recorded() -> None:
    client = _client_returning(
        _payload(
            {"title": "重复热点", "url": "https://s.weibo.com/a"},
            {"title": "其它", "url": "https://s.weibo.com/b"},
            {"title": "重复热点", "url": "https://s.weibo.com/a"},
        )
    )
    with patch("workflow.utils.hotspot_providers.httpx.AsyncClient", return_value=client):
        items = await NewsNowHotspotProvider().fetch_platform_items(PLATFORM, top_n=10)

    merged = next(item for item in items if item["title"] == "重复热点")
    assert merged["all_ranks"] == [1, 3]
    assert merged["appearances"] == 2
    assert merged["rank"] == 1


@pytest.mark.asyncio
async def test_top_n_truncates() -> None:
    client = _client_returning(
        _payload(*[{"title": f"热点{i}", "url": f"https://s.weibo.com/{i}"} for i in range(10)])
    )
    with patch("workflow.utils.hotspot_providers.httpx.AsyncClient", return_value=client):
        items = await NewsNowHotspotProvider().fetch_platform_items(PLATFORM, top_n=3)

    assert len(items) == 3


@pytest.mark.asyncio
async def test_missing_items_key_is_tolerated() -> None:
    client = _client_returning(json.dumps({"status": "success"}))
    with patch("workflow.utils.hotspot_providers.httpx.AsyncClient", return_value=client):
        items = await NewsNowHotspotProvider().fetch_platform_items(PLATFORM, top_n=5)

    assert items == []


@pytest.mark.asyncio
async def test_missing_platform_id_short_circuits() -> None:
    items = await NewsNowHotspotProvider().fetch_platform_items({"name": "空"}, top_n=5)
    assert items == []


@pytest.mark.asyncio
async def test_mobile_url_is_used_when_url_is_absent() -> None:
    client = _client_returning(_payload({"title": "只有移动链接", "mobileUrl": "https://s.weibo.com/m"}))
    with patch("workflow.utils.hotspot_providers.httpx.AsyncClient", return_value=client):
        items = await NewsNowHotspotProvider().fetch_platform_items(PLATFORM, top_n=5)

    assert items[0]["url"] == "https://s.weibo.com/m"


@pytest.mark.asyncio
async def test_extra_hover_becomes_extra_text() -> None:
    client = _client_returning(
        _payload(
            {
                "title": "带摘要的热点",
                "url": "https://www.baidu.com/s?wd=a",
                "extra": {"hover": "这是新闻摘要内容"},
            }
        )
    )
    platform = {**PLATFORM, "name": "百度热搜", "path": "baidu", "provider_id": "baidu"}
    with patch("workflow.utils.hotspot_providers.httpx.AsyncClient", return_value=client):
        items = await NewsNowHotspotProvider().fetch_platform_items(platform, top_n=5)

    assert items[0]["extra_text"] == "这是新闻摘要内容"


# --------------------------------------------------------------------------- #
# link-domain safety (ported behaviour)
# --------------------------------------------------------------------------- #


def test_expected_domain_accepts_https_and_subdomains() -> None:
    assert _link_is_expected_domain("https://s.weibo.com/weibo?q=a", ("weibo.com",)) is True
    assert _link_is_expected_domain("https://weibo.com/x", ("weibo.com",)) is True


def test_expected_domain_rejects_plain_http() -> None:
    assert _link_is_expected_domain("http://s.weibo.com/x", ("weibo.com",)) is False


@pytest.mark.parametrize(
    "hostile",
    [
        # Userinfo section makes the URL read as a trusted domain.
        "https://weibo.com@evil.example.com/x",
        "https://s.weibo.com.evil.example.com/x",
        "https://evil.example.com/?weibo.com",
        "https://notweibo.com/x",
    ],
)
def test_expected_domain_rejects_lookalike_hosts(hostile: str) -> None:
    assert _link_is_expected_domain(hostile, ("weibo.com",)) is False


def test_expected_domain_is_permissive_when_no_rule_exists() -> None:
    assert _link_is_expected_domain("https://anything.example.com/x", ()) is True


@pytest.mark.asyncio
async def test_items_with_hostile_links_are_dropped_not_fetched() -> None:
    """A spoofed link must not reach the downstream fetch stage."""
    client = _client_returning(
        _payload(
            {"title": "恶意链接", "url": "https://weibo.com@evil.example.com/x"},
            {"title": "正常链接", "url": "https://s.weibo.com/ok"},
        )
    )
    with patch("workflow.utils.hotspot_providers.httpx.AsyncClient", return_value=client):
        items = await NewsNowHotspotProvider().fetch_platform_items(PLATFORM, top_n=10)

    assert [item["title"] for item in items] == ["正常链接"]


def test_known_platforms_have_domain_rules() -> None:
    for platform_id in NEWSNOW_PLATFORM_IDS:
        assert newsnow_domains_for(platform_id), f"{platform_id} has no domain rule"


def test_extra_text_extraction_handles_other_shapes() -> None:
    assert _newsnow_extra_text({"hover": "摘要"}) == "摘要"
    assert _newsnow_extra_text({"info": "信息"}) == "信息"
    # `icon`-only extras must not be mistaken for a description.
    assert _newsnow_extra_text({"icon": "https://x/y.png"}) == ""
    assert _newsnow_extra_text(None) == ""
    assert _newsnow_extra_text("not-a-dict") == ""
