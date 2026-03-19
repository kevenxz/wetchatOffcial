"""Markdown to inline-styled WeChat HTML."""
from __future__ import annotations

import re

import markdown
from bs4 import BeautifulSoup

from api.store import get_style_config


def _merge_style(existing_style: str, style_str: str) -> str:
    if not existing_style:
        return style_str
    spacer = " " if not existing_style.endswith(";") else ""
    return f"{existing_style}{spacer}{style_str}"


def markdown_to_wechat_html(md_text: str, illustrations: list[str]) -> str:
    """Convert Markdown into WeChat-friendly inline-styled HTML."""
    if not md_text:
        return ""

    def replacer(match: re.Match[str]) -> str:
        idx = int(match.group(1)) - 1
        if 0 <= idx < len(illustrations):
            img_url = illustrations[idx]
            return (
                '<figure class="wx-illustration-container" style="text-align: center; margin: 16px 0;">'
                f'<img src="{img_url}" style="max-width: 100%; height: auto; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);">'
                "</figure>"
            )
        return match.group(0)

    md_text = re.sub(r"\[插图(\d+)\]", replacer, md_text)

    html_content = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "nl2br", "sane_lists"],
    )

    style_config = get_style_config()
    container_style = style_config.get("container", "padding: 0 15px;")
    soup = BeautifulSoup(html_content, "html.parser")

    for selector, style_str in style_config.items():
        if selector == "container" or not style_str:
            continue
        for element in soup.select(selector):
            element["style"] = _merge_style(element.get("style", ""), style_str)

    return f'<div class="wx-article-container" style="{container_style}">{str(soup)}</div>'
