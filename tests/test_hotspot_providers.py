from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from workflow.utils.hotspot_providers import fetch_hotspot_platform_items, list_builtin_hotspot_platforms


@pytest.mark.asyncio
async def test_rss_hotspot_provider_parses_feed_items() -> None:
    feed = """<?xml version="1.0" encoding="UTF-8" ?>
    <rss><channel>
      <item><title>36氪测试快讯</title><link>https://36kr.com/news/1</link><description>融资与产品更新</description></item>
      <item><title>第二条快讯</title><link>https://36kr.com/news/2</link></item>
    </channel></rss>
    """
    response = MagicMock()
    response.text = feed
    response.raise_for_status.return_value = None

    client = AsyncMock()
    client.get.return_value = response

    with patch("workflow.utils.hotspot_providers.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value = client
        items = await fetch_hotspot_platform_items(
            {
                "name": "36氪快讯",
                "path": "https://36kr.com/feed-newsflash",
                "source": "rss_or_feed",
                "provider_id": "36kr_newsflash",
                "category": "科技",
                "weight": 1.2,
            },
            top_n=5,
        )

    assert len(items) == 2
    assert items[0]["source"] == "rss_or_feed"
    assert items[0]["provider_id"] == "36kr_newsflash"
    assert items[0]["platform_name"] == "36氪快讯"
    assert items[0]["title"] == "36氪测试快讯"


def test_builtin_platforms_include_non_tophub_presets() -> None:
    items = list_builtin_hotspot_platforms(["科技", "财经"])
    names = {item["name"] for item in items}

    assert "36氪快讯" in names
    assert "华尔街日报全球新闻" in names
