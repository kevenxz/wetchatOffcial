"""Draft quality rules and deterministic repair for the writing stage.

The writer used to answer any quality violation with a second full-length LLM
generation. Most violations are mechanical (a heading that leaked a source URL,
a duplicated paragraph, leftover planning language), so they can be repaired
locally and cheaply. Only content-level shortfalls still deserve a model call.
"""
from __future__ import annotations

import re

PLANNING_LANGUAGE = (
    "这一节要解决的问题",
    "把这条线索放进正文",
    "放到微信公众号语境",
    "参考线索：",
    "目前可用资料",
    "本节目标",
    "这一部分将",
)

# Violation prefixes that deterministic repair can resolve on its own.
MECHANICAL_VIOLATION_PREFIXES = (
    "正文暴露编辑备注",
    "小标题过多",
    "小标题含网址",
    "正文存在重复段落",
)

# Violation prefixes that require additional content and therefore a model call.
CONTENT_VIOLATION_PREFIXES = (
    "正文过短",
    "有效正文段落少于",
)

_HEADING_FALLBACKS = (
    "先确认发生了什么",
    "变化背后的逻辑",
    "放进真实场景再看",
    "仍需验证的变量",
    "现在还不能下什么结论",
    "接下来该看什么",
)

MINIMUM_LENGTH_BY_SIZE = {"short": 550, "medium": 850, "long": 1300}
MAX_HEADING_COUNT = 6


def safe_heading(value: str, fallback: str) -> str:
    """Return a publishable heading, or ``fallback`` when the raw value is unusable."""
    heading = " ".join(str(value or "").replace("#", " ").split()).strip(" -—:：")
    if (
        not heading
        or len(heading) > 42
        or re.search(r"(?:https?://|www\.|\.(?:com|cn|net|org)(?:/|$))", heading, flags=re.I)
        or heading.endswith(("...", "……"))
    ):
        return fallback
    return heading


def _iter_paragraphs(content: str) -> list[str]:
    paragraphs: list[str] = []
    for raw_block in content.split("\n\n"):
        block = raw_block.strip()
        if not block:
            continue
        if block.startswith("## "):
            _, _, body_after_heading = block.partition("\n")
            if body_after_heading.strip():
                paragraphs.append(body_after_heading.strip())
            continue
        paragraphs.append(block)
    return paragraphs


def draft_quality_violations(content: str, article_length: str = "medium") -> list[str]:
    """Return human-readable quality violations for a draft body."""
    content = str(content or "").strip()
    violations: list[str] = []
    minimum_length = MINIMUM_LENGTH_BY_SIZE.get(article_length, 850)
    if len(content) < minimum_length:
        violations.append(f"正文过短：当前 {len(content)} 字符，建议至少 {minimum_length} 字符")
    paragraphs = _iter_paragraphs(content)
    if len(paragraphs) < 4:
        violations.append("有效正文段落少于 4 段")
    for phrase in PLANNING_LANGUAGE:
        if phrase in content:
            violations.append(f"正文暴露编辑备注：{phrase}")
    headings = [line[3:].strip() for line in content.splitlines() if line.startswith("## ")]
    if len(headings) > MAX_HEADING_COUNT:
        violations.append(f"小标题过多：{len(headings)} 个")
    if any(safe_heading(heading, "") != heading for heading in headings):
        violations.append("小标题含网址、来源标题或截断文本")
    normalized_paragraphs = ["".join(block.split()) for block in paragraphs if len("".join(block.split())) >= 30]
    if len(normalized_paragraphs) != len(set(normalized_paragraphs)):
        violations.append("正文存在重复段落")
    return violations


def classify_violations(violations: list[str]) -> tuple[list[str], list[str]]:
    """Split violations into (mechanically repairable, content-level)."""
    mechanical: list[str] = []
    content_level: list[str] = []
    for violation in violations:
        if violation.startswith(MECHANICAL_VIOLATION_PREFIXES):
            mechanical.append(violation)
        elif violation.startswith(CONTENT_VIOLATION_PREFIXES):
            content_level.append(violation)
        else:
            # Unknown rules are treated as content-level so they stay visible.
            content_level.append(violation)
    return mechanical, content_level


def _strip_planning_language(text: str) -> tuple[str, int]:
    """Remove sentences that leak editorial instructions into the article body."""
    kept_lines: list[str] = []
    removed = 0
    for line in text.splitlines():
        if not any(phrase in line for phrase in PLANNING_LANGUAGE):
            kept_lines.append(line)
            continue
        removed += 1
        kept_sentences = [
            sentence
            for sentence in re.split(r"(?<=[。！？!?])", line)
            if sentence.strip() and not any(phrase in sentence for phrase in PLANNING_LANGUAGE)
        ]
        if kept_sentences:
            kept_lines.append("".join(kept_sentences).strip())
    return "\n".join(kept_lines), removed


def _derive_heading(body: str, index: int) -> str:
    """Derive a semantic heading from the following paragraph."""
    first_sentence = re.split(r"[。！？!?\n]", str(body or "").strip())[0].strip()
    cleaned = safe_heading(first_sentence, "")
    if cleaned and 4 <= len(cleaned) <= 20:
        return cleaned
    return _HEADING_FALLBACKS[index % len(_HEADING_FALLBACKS)]


def _sanitize_headings(text: str) -> tuple[str, int]:
    """Replace headings that leaked URLs, source titles or truncated snippets."""
    lines = text.splitlines()
    renamed = 0
    for index, line in enumerate(lines):
        if not line.startswith("## "):
            continue
        raw = line[3:].strip()
        if raw and safe_heading(raw, "") == raw:
            continue
        body = ""
        for candidate in lines[index + 1:]:
            if candidate.strip():
                body = candidate.strip()
                break
        lines[index] = f"## {_derive_heading(body, renamed)}"
        renamed += 1
    return "\n".join(lines), renamed


def _reduce_headings(text: str, limit: int = MAX_HEADING_COUNT) -> tuple[str, int]:
    """Demote the thinnest extra headings so the narrative is not over-fragmented."""
    lines = text.splitlines()
    heading_indexes = [index for index, line in enumerate(lines) if line.startswith("## ")]
    if len(heading_indexes) <= limit:
        return text, 0

    body_sizes: dict[int, int] = {}
    for position, index in enumerate(heading_indexes):
        end = heading_indexes[position + 1] if position + 1 < len(heading_indexes) else len(lines)
        body_sizes[index] = sum(len(line) for line in lines[index + 1:end])

    demote_count = len(heading_indexes) - limit
    for index in sorted(body_sizes, key=lambda key: body_sizes[key])[:demote_count]:
        lines[index] = lines[index][3:].strip()
    return "\n".join(lines), demote_count


def _dedupe_paragraphs(text: str) -> tuple[str, int]:
    """Drop repeated body paragraphs while preserving headings."""
    blocks = [block.strip() for block in text.split("\n\n") if block.strip()]
    seen: set[str] = set()
    kept: list[str] = []
    dropped = 0
    for block in blocks:
        if block.startswith("## "):
            kept.append(block)
            continue
        key = "".join(block.split())
        if len(key) >= 30 and key in seen:
            dropped += 1
            continue
        if len(key) >= 30:
            seen.add(key)
        kept.append(block)
    return "\n\n".join(kept), dropped


def normalize_draft_content(content: str) -> tuple[str, list[str]]:
    """Apply deterministic repairs and report which repairs were applied."""
    text = str(content or "")
    if not text.strip():
        return text, []

    fixes: list[str] = []

    text, removed = _strip_planning_language(text)
    if removed:
        fixes.append("planning_language_removed")

    text, renamed = _sanitize_headings(text)
    if renamed:
        fixes.append("headings_sanitized")

    text, demoted = _reduce_headings(text)
    if demoted:
        fixes.append("headings_merged")

    text, dropped = _dedupe_paragraphs(text)
    if dropped:
        fixes.append("paragraphs_deduped")

    return text.strip(), fixes
