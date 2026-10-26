"""Strip syndication boilerplate out of a claim before it reaches an image prompt.

Why this exists
---------------
A real generated image prompt contained this as its "data signal":

    以下文章来源于科创板日报 ，作者史正丞 专注科创板和科技创新，上海报业集团主管主办，界面财联社出品。

That is scraped syndication chrome, not evidence. It reached the image model through
the outline section's `goal` (``可用证据：<raw claim>``), which `plan_visual_assets`
used as both `purpose` and `key_points`. Feeding an image model a wall of Chinese
prose is one of the direct causes of "the pictures are all text".

Pure functions only: no model calls, so this is cheap and fully unit-testable.
"""
from __future__ import annotations

import re

# Strong markers of syndication chrome. Deliberately narrow: a bare "作者" is not a
# marker because legitimate sentences also say things like "作者认为".
BOILERPLATE_PATTERNS: tuple[str, ...] = (
    r"以下文章来源于",
    r"本文(?:来自|转载|首发|系)",
    r"文章(?:来自|转载)",
    r"转自[：:]?",
    r"来源[：:]\s*\S{1,20}",
    r"主管主办",
    r"出品",
    r"点击(?:上方|下方|关注|这里)",
    r"扫码(?:关注|阅读)?",
    r"关注我们",
    r"免责声明",
    r"版权(?:所有|归)",
    r"原标题[：:]",
    r"编辑[：:]\s*\S{1,10}",
    r"作者[：:]\s*\S{1,10}",
    r"实习(?:生|记者)",
)

_BOILERPLATE_REGEX = re.compile("|".join(BOILERPLATE_PATTERNS))
_URL_REGEX = re.compile(r"https?://\S+|www\.\S+")
# Trailing truncation left over from cutting a long extraction, e.g. "与此同..."
_ELLIPSIS_TAIL_REGEX = re.compile(r"[.．。]{2,}\s*$|…+\s*$|[，,]\s*$")
_SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?；;])")
_WHITESPACE = re.compile(r"\s+")

# A claim longer than this is not usable as a visual signal anyway.
DEFAULT_CLAIM_LIMIT = 200


def has_boilerplate(text: str) -> bool:
    """Whether the text contains syndication chrome."""
    return bool(_BOILERPLATE_REGEX.search(str(text or "")))


def strip_urls(text: str) -> str:
    return _URL_REGEX.sub(" ", str(text or ""))


def strip_ellipsis_tail(text: str) -> str:
    """Remove trailing truncation artefacts like ``与此同...`` or ``…``."""
    cleaned = str(text or "")
    while True:
        stripped = _ELLIPSIS_TAIL_REGEX.sub("", cleaned).rstrip()
        if stripped == cleaned:
            return stripped
        cleaned = stripped


def drop_boilerplate_sentences(text: str) -> str:
    """Drop whole sentences that look like syndication chrome."""
    kept = [
        sentence
        for sentence in _SENTENCE_SPLIT.split(str(text or ""))
        if sentence.strip() and not _BOILERPLATE_REGEX.search(sentence)
    ]
    return "".join(kept)


def clean_claim(text: str, limit: int = DEFAULT_CLAIM_LIMIT) -> str:
    """Return a short, usable claim with boilerplate and truncation removed.

    Returns an empty string when nothing usable survives, so callers can omit the
    field rather than shipping chrome to the model.
    """
    cleaned = _WHITESPACE.sub(" ", strip_urls(str(text or ""))).strip()
    if not cleaned:
        return ""

    cleaned = drop_boilerplate_sentences(cleaned)
    cleaned = strip_ellipsis_tail(_WHITESPACE.sub(" ", cleaned).strip())
    if not cleaned:
        return ""

    if len(cleaned) <= limit:
        return cleaned

    # Prefer cutting on a sentence boundary so the claim stays readable.
    head = cleaned[:limit]
    boundary = max(head.rfind(mark) for mark in "。！？!?；;")
    if boundary >= limit // 2:
        return head[: boundary + 1].strip()
    return strip_ellipsis_tail(head).rstrip("，,、:： ") + "。"


def clean_claims(items: list[str], limit: int = DEFAULT_CLAIM_LIMIT, max_items: int = 3) -> list[str]:
    """Clean a list of claims, dropping empties and duplicates."""
    cleaned: list[str] = []
    for item in items:
        value = clean_claim(item, limit=limit)
        if value and value not in cleaned:
            cleaned.append(value)
        if len(cleaned) >= max_items:
            break
    return cleaned
