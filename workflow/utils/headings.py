"""Shared subject/heading extraction for content-driven article structure.

Both the blueprint planner and the deterministic draft builder derive section
headings from the story's own claims. Keeping that logic in one place stops the two
paths from drifting apart, and makes it obvious that headings are meant to differ
per story rather than coming from a fixed template.
"""
from __future__ import annotations

import re

# Sentence/clause boundaries used to isolate the leading clause of a claim.
_CLAUSE_SPLIT = re.compile(r"[。！？；;，,、:：\n]")

# Discourse markers that add no meaning to a heading.
LEADING_CONNECTORS: tuple[str, ...] = (
    "此外", "同时", "另外", "因此", "不过", "但是", "然而", "目前",
    "值得注意", "事实上", "可以说", "总体来看", "需要注意的是",
)

_TRIM_CHARS = "，,、:： "


def subject_from_claim(claim: str, limit: int = 24) -> str:
    """Extract a short, story-specific subject phrase from one claim.

    The default limit fits a complete Chinese clause. Chinese has no word spacing, so
    a tighter limit truncates mid-phrase and the heading reads unfinished; the value
    still stays well inside the heading length limit.

    Returns an empty string when nothing usable can be derived, so callers can fall
    back to a neutral heading instead of emitting a half-sentence.
    """
    text = " ".join(str(claim or "").split())
    if not text:
        return ""

    head = _CLAUSE_SPLIT.split(text, maxsplit=1)[0].strip()
    for connector in LEADING_CONNECTORS:
        if head.startswith(connector):
            head = head[len(connector):].strip(_TRIM_CHARS)

    head = head.strip("“”\"'（）()【】[] 《》")
    if len(head) > limit:
        truncated = head[:limit]
        # Do not cut a Latin word in half; Chinese has no word spaces so this only
        # affects mixed or English material.
        if re.search(r"[A-Za-z0-9]", truncated[-1:]) and " " in truncated:
            truncated = truncated.rsplit(" ", 1)[0]
        head = truncated.rstrip(_TRIM_CHARS)
    return head
