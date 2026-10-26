"""Platform catalog and safety rules for the newsnow hot-list source.

Where this comes from
---------------------
The platform ids and names mirror TrendRadar's ``config/config.yaml``
(https://github.com/sansan0/TrendRadar, GPL-3.0). TrendRadar's own crawler
(``trendradar/crawler/fetcher.py``) does not scrape each site: it calls one public
API provided by the newsnow project (https://github.com/ourongxing/newsnow)::

    GET https://newsnow.busiyi.world/api/s?id=<platform_id>&latest
    -> {"status": "success"|"cache", "items": [{"title", "url", "mobileUrl", "extra"}, ...]}

We re-implement that call in our own provider rather than embedding TrendRadar's source:
its licence is GPL-3.0, which would relicense this repository, and ~95% of it (HTML
reporting, nine push channels, LiteLLM analysis, cloud storage sync) is unrelated to
fetching a hot list.

Credit: newsnow (ourongxing/newsnow) for the API, TrendRadar (sansan0/TrendRadar) for the
platform catalogue and for the validation behaviour ported into ``hotspot_providers``.
"""
from __future__ import annotations

from typing import Any

# Platform ids are stable upstream keys; names are display-only and may be renamed.
NEWSNOW_PLATFORMS: tuple[dict[str, Any], ...] = (
    {"id": "toutiao", "name": "今日头条", "category": "社会", "weight": 1.1, "domains": ("toutiao.com",)},
    {"id": "baidu", "name": "百度热搜", "category": "社会", "weight": 1.1, "domains": ("baidu.com",)},
    {"id": "weibo", "name": "微博热搜", "category": "社会", "weight": 1.1, "domains": ("weibo.com", "weibo.cn")},
    {"id": "douyin", "name": "抖音热点", "category": "社会", "weight": 1.0, "domains": ("douyin.com", "iesdouyin.com")},
    {"id": "zhihu", "name": "知乎热榜", "category": "AI", "weight": 1.1, "domains": ("zhihu.com",)},
    {"id": "tieba", "name": "百度贴吧热议", "category": "社会", "weight": 0.8, "domains": ("tieba.baidu.com", "baidu.com")},
    {"id": "thepaper", "name": "澎湃新闻", "category": "社会", "weight": 1.1, "domains": ("thepaper.cn",)},
    {"id": "ifeng", "name": "凤凰网", "category": "社会", "weight": 1.0, "domains": ("ifeng.com",)},
    {
        "id": "bilibili-hot-search",
        "name": "bilibili 热搜",
        "category": "科技",
        "weight": 0.9,
        "domains": ("bilibili.com",),
    },
    {"id": "ithome", "name": "IT之家", "category": "科技", "weight": 1.1, "domains": ("ithome.com",)},
    {
        "id": "wallstreetcn-hot",
        "name": "华尔街见闻",
        "category": "财经",
        "weight": 1.1,
        "domains": ("wallstreetcn.com",),
    },
    {"id": "cls-hot", "name": "财联社热门", "category": "财经", "weight": 1.1, "domains": ("cls.cn",)},
    {"id": "jin10", "name": "金十数据", "category": "财经", "weight": 1.0, "domains": ("jin10.com",)},
    {"id": "xueqiu", "name": "雪球热帖", "category": "财经", "weight": 1.0, "domains": ("xueqiu.com",)},
    {"id": "fastbull", "name": "FastBull", "category": "财经", "weight": 0.9, "domains": ("fastbull.cn", "fastbull.com")},
    {"id": "mktnews", "name": "市场资讯", "category": "财经", "weight": 0.9, "domains": ("mktnews.com",)},
)

NEWSNOW_PLATFORM_IDS: tuple[str, ...] = tuple(item["id"] for item in NEWSNOW_PLATFORMS)

# Platform id -> expected link domains. Used by the provider's link-safety check.
NEWSNOW_DOMAIN_RULES: dict[str, tuple[str, ...]] = {
    str(item["id"]): tuple(item.get("domains") or ()) for item in NEWSNOW_PLATFORMS
}


def newsnow_platform_catalog(categories: list[str] | None = None) -> list[dict[str, Any]]:
    """Return the newsnow platforms as hotspot platform presets.

    Shaped like the existing platform entries so the workflow, the API and the UI can
    treat every source uniformly.
    """
    normalized = {str(category).strip().lower() for category in (categories or []) if str(category).strip()}
    items: list[dict[str, Any]] = []
    for platform in NEWSNOW_PLATFORMS:
        platform_id = str(platform["id"])
        category = str(platform.get("category") or "")
        if normalized and category.lower() not in normalized and platform_id.lower() not in normalized:
            continue
        items.append(
            {
                "name": str(platform["name"]),
                "path": platform_id,
                "source": "newsnow",
                "provider_id": platform_id,
                "category": category,
                "weight": float(platform.get("weight") or 1.0),
                "enabled": True,
            }
        )
    return items


def newsnow_domains_for(platform_id: str) -> tuple[str, ...]:
    """Expected link domains for a platform, empty when we have no rule for it."""
    return NEWSNOW_DOMAIN_RULES.get(str(platform_id or "").strip(), ())
