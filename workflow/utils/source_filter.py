"""Deterministic filtering for searched and fetched pages.

Before this module existed, everything the search stage returned flowed straight
into the evidence pack: the only gates were "extracted text is at least 50
characters" and exact-URL de-duplication. Off-topic pages, navigation captures,
syndicated copies of the same wire story, and low-authority aggregators therefore
reached the blueprint and the draft as if they were evidence.

Every gate here is deterministic and cheap (no model calls), and each dropped item
records why, so an operator can audit what was thrown away.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import structlog

from workflow import runtime_settings

logger = structlog.get_logger(__name__)

# Sources that may inform the article but must not be presented as hard fact.
LOW_AUTHORITY_SOURCE_TYPES = frozenset({"community", "aggregator", "social", "unknown"})

_CJK = re.compile(r"[\u4e00-\u9fff]")
_ALNUM_WORD = re.compile(r"[a-zA-Z0-9]{2,}")
_SENTENCE_END = re.compile(r"[。！？!?；;]")
_WHITESPACE = re.compile(r"\s+")

# Words too common to signal topical relevance.
_STOPWORDS = frozenset(
    {
        "the", "and", "for", "with", "that", "this", "from", "are", "was", "were",
        "has", "have", "will", "not", "but", "you", "your", "its", "into", "about",
        "最新", "消息", "报道", "解读", "分析", "影响", "相关", "进行", "一个", "我们",
    }
)


def _normalize(text: str) -> str:
    return _WHITESPACE.sub(" ", str(text or "")).strip()


def topic_tokens(topic: str, extra: list[str] | None = None) -> set[str]:
    """Tokenize a topic into CJK bigrams and Latin words for overlap scoring."""
    text = " ".join([str(topic or ""), *[str(item or "") for item in (extra or [])]])
    tokens: set[str] = set()

    lowered = text.lower()
    tokens.update(word for word in _ALNUM_WORD.findall(lowered) if word not in _STOPWORDS)

    cjk_runs = re.findall(r"[\u4e00-\u9fff]+", text)
    for run in cjk_runs:
        if len(run) == 1:
            tokens.add(run)
            continue
        for index in range(len(run) - 1):
            bigram = run[index : index + 2]
            if bigram not in _STOPWORDS:
                tokens.add(bigram)
    return tokens


def relevance_score(topic: str, item: dict[str, Any], extra: list[str] | None = None) -> float:
    """Ratio of topic tokens that appear in the item's title and lead text."""
    tokens = topic_tokens(topic, extra)
    if not tokens:
        return 1.0

    haystack = " ".join(
        [
            _normalize(str(item.get("title") or "")),
            _normalize(str(item.get("text") or item.get("content") or item.get("claim") or ""))[:500],
        ]
    ).lower()
    if not haystack:
        return 0.0

    hits = sum(1 for token in tokens if token in haystack)
    return round(hits / len(tokens), 4)


def _shingles(text: str, size: int = 6) -> set[str]:
    compact = re.sub(r"\s+", "", str(text or ""))[:600]
    if len(compact) <= size:
        return {compact} if compact else set()
    return {compact[index : index + size] for index in range(len(compact) - size + 1)}


def similarity(left: str, right: str) -> float:
    """Jaccard similarity between two texts' character shingles."""
    left_set = _shingles(left)
    right_set = _shingles(right)
    if not left_set or not right_set:
        return 0.0
    intersection = len(left_set & right_set)
    union = len(left_set | right_set)
    return round(intersection / union, 4) if union else 0.0


def _sentence_count(text: str) -> int:
    return len([part for part in _SENTENCE_END.split(text) if len(part.strip()) >= 8])


def _body_text(item: dict[str, Any]) -> str:
    for key in ("text", "content", "excerpt", "claim", "snippet", "summary"):
        value = _normalize(str(item.get(key) or ""))
        if value:
            return value
    return ""


def _domain(item: dict[str, Any]) -> str:
    return _normalize(str(item.get("domain") or "")).lower()


@dataclass
class SourceFilterResult:
    """Outcome of one filtering pass."""

    kept: list[dict[str, Any]] = field(default_factory=list)
    dropped: list[dict[str, Any]] = field(default_factory=list)
    insufficient: bool = False

    @property
    def kept_count(self) -> int:
        return len(self.kept)

    def summary(self) -> dict[str, Any]:
        reasons: dict[str, int] = {}
        for item in self.dropped:
            reason = str(item.get("reason") or "unknown")
            reasons[reason] = reasons.get(reason, 0) + 1
        return {
            "kept": len(self.kept),
            "dropped": len(self.dropped),
            "reasons": reasons,
            "insufficient": self.insufficient,
            "dropped_items": self.dropped[:20],
        }


def filter_sources(
    topic: str,
    items: list[dict[str, Any]],
    *,
    keywords: list[str] | None = None,
    min_survivors: int | None = None,
    min_relevance: float | None = None,
    min_chars: int | None = None,
    min_sentences: int | None = None,
    max_per_domain: int | None = None,
    near_duplicate_similarity: float | None = None,
) -> SourceFilterResult:
    """Apply the relevance, quality, near-duplicate and per-domain gates.

    Kept items are annotated with ``needs_caution`` (low-authority sources may
    inform the article but must not be presented as established fact), ``relevance``
    and ``filtered`` so downstream stages can explain their decisions.
    """
    min_relevance = runtime_settings.source_min_relevance() if min_relevance is None else min_relevance
    min_chars = runtime_settings.source_min_chars() if min_chars is None else min_chars
    min_sentences = runtime_settings.source_min_sentences() if min_sentences is None else min_sentences
    max_per_domain = runtime_settings.source_max_per_domain() if max_per_domain is None else max_per_domain
    near_duplicate_similarity = (
        runtime_settings.source_near_duplicate_similarity()
        if near_duplicate_similarity is None
        else near_duplicate_similarity
    )
    min_survivors = runtime_settings.source_min_survivors() if min_survivors is None else min_survivors

    result = SourceFilterResult()
    domain_counts: dict[str, int] = {}
    kept_bodies: list[str] = []

    for index, raw in enumerate(items):
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        url = _normalize(str(item.get("url") or ""))
        body = _body_text(item)
        source_type = _normalize(str(item.get("source_type") or "unknown")).lower()

        # 1. Quality: too short, or no real sentences (navigation/boilerplate).
        # Official announcements may be brief but are still authoritative.
        effective_min_chars = (
            min(min_chars, runtime_settings.source_official_min_chars())
            if source_type in {"official", "documentation"}
            else min_chars
        )
        if len(body) < effective_min_chars:
            result.dropped.append(
                {"url": url, "reason": "too_short", "chars": len(body), "threshold": effective_min_chars}
            )
            continue
        if _sentence_count(body) < min_sentences:
            result.dropped.append({"url": url, "reason": "not_prose", "sentences": _sentence_count(body)})
            continue

        # 2. Relevance: must actually be about the topic.
        score = relevance_score(topic, item, keywords)
        if score < min_relevance:
            result.dropped.append({"url": url, "reason": "off_topic", "relevance": score})
            continue

        # 3. Near-duplicate: the same wire story syndicated across sites.
        duplicate_of = ""
        for kept_body in kept_bodies:
            if similarity(body, kept_body) >= near_duplicate_similarity:
                duplicate_of = kept_body[:80]
                break
        if duplicate_of:
            result.dropped.append({"url": url, "reason": "near_duplicate", "sample": duplicate_of})
            continue

        # 4. Per-domain cap: force source diversity.
        domain = _domain(item)
        if domain and domain_counts.get(domain, 0) >= max_per_domain:
            result.dropped.append({"url": url, "reason": "domain_cap", "domain": domain})
            continue

        source_type = _normalize(str(item.get("source_type") or "unknown")).lower()
        item["relevance"] = score
        item["filtered"] = True
        if source_type in LOW_AUTHORITY_SOURCE_TYPES and not item.get("needs_caution"):
            # Usable as a clue, never as the sole basis for a core fact.
            item["needs_caution"] = True
        result.kept.append(item)
        kept_bodies.append(body)
        if domain:
            domain_counts[domain] = domain_counts.get(domain, 0) + 1

    result.insufficient = len(result.kept) < min_survivors

    logger.info(
        "source_filter_applied",
        topic=str(topic or "")[:80],
        incoming=len(items),
        kept=result.kept_count,
        dropped=len(result.dropped),
        reasons=result.summary()["reasons"],
        insufficient=result.insufficient,
    )
    return result
