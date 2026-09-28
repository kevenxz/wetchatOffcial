"""Tests for deterministic draft repair."""
from __future__ import annotations

from workflow.utils.draft_quality import (
    classify_violations,
    draft_quality_violations,
    normalize_draft_content,
    safe_heading,
)

LONG_BODY = "这是一段用于满足最小长度要求的正文内容，说明变化已经发生，但仍需结合后续数据判断趋势是否稳定。" * 12


def test_safe_heading_rejects_urls_and_truncated_text() -> None:
    assert safe_heading("https://example.com/very/long/path", "回退标题") == "回退标题"
    assert safe_heading("被截断的来源标题……", "回退标题") == "回退标题"
    assert safe_heading("真正的判断", "回退标题") == "真正的判断"


def test_planning_language_is_removed() -> None:
    content = f"## 判断\n\n本节目标是把这条线索放进正文。{LONG_BODY}"

    normalized, fixes = normalize_draft_content(content)

    assert "planning_language_removed" in fixes
    assert "本节目标" not in normalized
    assert "把这条线索放进正文" not in normalized


def test_source_heading_is_replaced_with_semantic_heading() -> None:
    content = f"## https://example.com/source\n\n变化已经发生，但仍需观察后续数据。{LONG_BODY}"

    normalized, fixes = normalize_draft_content(content)

    assert "headings_sanitized" in fixes
    assert "https://example.com/source" not in normalized
    assert normalized.startswith("## ")


def test_excess_headings_are_demoted_to_limit() -> None:
    sections = "\n\n".join(f"## 小节标题{i}\n\n这是第{i}节的正文内容，用于占位。" for i in range(1, 9))

    normalized, fixes = normalize_draft_content(sections)

    assert "headings_merged" in fixes
    assert normalized.count("## ") <= 6


def test_duplicate_paragraphs_are_dropped() -> None:
    paragraph = "这段内容足够长，用来触发重复段落检测逻辑，避免被短文本规则忽略掉。" * 2
    content = f"{paragraph}\n\n{paragraph}"

    normalized, fixes = normalize_draft_content(content)

    assert "paragraphs_deduped" in fixes
    assert normalized.count(paragraph) == 1


def test_classify_violations_separates_mechanical_from_content() -> None:
    mechanical, content_level = classify_violations(
        [
            "正文暴露编辑备注：本节目标",
            "小标题过多：8 个",
            "正文过短：当前 300 字符，建议至少 850 字符",
            "有效正文段落少于 4 段",
        ]
    )

    assert mechanical == ["正文暴露编辑备注：本节目标", "小标题过多：8 个"]
    assert content_level == ["正文过短：当前 300 字符，建议至少 850 字符", "有效正文段落少于 4 段"]


def test_unknown_violation_stays_visible_as_content_level() -> None:
    mechanical, content_level = classify_violations(["某个未来的新规则"])

    assert mechanical == []
    assert content_level == ["某个未来的新规则"]


def test_clean_draft_needs_no_repair() -> None:
    content = "\n\n".join(
        [
            "开头给出一个具体判断，而不是从背景介绍开始，这一点决定了首屏是否留得住读者。" * 3,
            f"## 变化信号\n\n{LONG_BODY}",
            f"## 风险边界\n\n变化成立的条件还没有被完全验证，{LONG_BODY}",
            f"## 接下来看什么\n\n后续需要观察交付结果能否重复出现，{LONG_BODY}",
            f"结尾回扣判断并给出下一步观察指标，而不是复述全文。{LONG_BODY}",
        ]
    )

    normalized, fixes = normalize_draft_content(content)

    assert fixes == []
    assert normalized == content.strip()


def test_quality_violations_detect_short_and_thin_drafts() -> None:
    violations = draft_quality_violations("太短了。", "medium")

    assert any(item.startswith("正文过短") for item in violations)
    assert any(item.startswith("有效正文段落少于") for item in violations)
