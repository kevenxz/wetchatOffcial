"""Tests for TopHub HTML parser and helper utilities."""
from __future__ import annotations

import pytest

from workflow.utils.tophub_client import TopHubClient, parse_hot_value


def test_parse_hot_value_supports_plain_and_units() -> None:
    assert parse_hot_value("3255") == 3255
    assert parse_hot_value("1.2万热度") == 12000
    assert parse_hot_value("8.5k") == 8500
    assert parse_hot_value("无热度") is None


@pytest.mark.asyncio
async def test_fetch_category_platforms_parses_n_links() -> None:
    client = TopHubClient()

    async def fake_fetch_html(path: str) -> str:
        assert path == "/c/finance"
        return """
        <html><body>
          <a href="/n/mproPpoq6O">知乎热榜</a>
          <a href="/n/abc123">第一财经</a>
          <a href="/c/news">新闻分类</a>
        </body></html>
        """

    client._fetch_html = fake_fetch_html  # type: ignore[method-assign]
    platforms = await client.fetch_category_platforms("finance")

    assert len(platforms) == 2
    assert platforms[0]["path"] == "/n/mproPpoq6O"
    assert platforms[1]["name"] == "第一财经"


@pytest.mark.asyncio
async def test_fetch_platform_hot_items_parses_table_rows() -> None:
    client = TopHubClient()

    async def fake_fetch_html(path: str) -> str:
        assert path == "/n/mproPpoq6O"
        return """
        <html><body>
          <table>
            <tbody>
              <tr>
                <td>1</td>
                <td><a href="https://example.com/a">热点标题A</a></td>
                <td>3255</td>
              </tr>
              <tr>
                <td>2</td>
                <td><a href="https://example.com/b">热点标题B</a></td>
                <td>1.2万</td>
              </tr>
            </tbody>
          </table>
        </body></html>
        """

    client._fetch_html = fake_fetch_html  # type: ignore[method-assign]
    items = await client.fetch_platform_hot_items(
        platform_name="知乎热榜",
        platform_path="/n/mproPpoq6O",
        category="finance",
        top_n=10,
        platform_weight=1.0,
    )

    assert len(items) == 2
    assert items[0]["title"] == "热点标题A"
    assert items[0]["rank"] == 1
    assert items[0]["hot_value"] == 3255
    assert items[1]["hot_value"] == 12000
