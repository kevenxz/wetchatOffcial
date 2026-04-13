"""Generate the final article from blueprint, style profile and extracted evidence."""
from __future__ import annotations

import re
import time
from typing import Any

import structlog
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from api.store import get_model_config
from workflow.model_logging import build_model_context, log_model_request, log_model_response
from workflow.state import WorkflowState

logger = structlog.get_logger(__name__)

ARTICLE_MAX_SOURCES = 6
ARTICLE_SOURCE_TEXT_LIMIT = 4000
ARTICLE_TOTAL_EVIDENCE_LIMIT = 24000
ARTICLE_MIN_SOURCE_TEXT_LIMIT = 800
ARTICLE_MIN_TOTAL_EVIDENCE_LIMIT = 6000
RISK_SECTION_KEYWORDS = ("局限", "风险", "挑战", "不确定", "边界", "约束", "难点", "误判")
ACTION_SECTION_KEYWORDS = ("行动", "建议", "下一步", "关注点", "跟踪", "观察", "应对", "怎么做", "实践")


class ArticleOutput(BaseModel):
    """Generated article payload."""

    title: str = Field(description="主标题，15-50字")
    alt_titles: list[str] = Field(description="2个备选标题，15-50字")
    content: str = Field(description="Markdown 正文，必须保留蓝图章节与插图标记")


def _normalize_excerpt(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _truncate_excerpt(text: str, limit: int) -> str:
    normalized = _normalize_excerpt(text)
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit]}...(已截断)"


def _sorted_extracted_contents(extracted_contents: list[dict]) -> list[dict]:
    return sorted(
        extracted_contents,
        key=lambda item: float(item.get("source_meta", {}).get("final_score", 0) or 0),
        reverse=True,
    )


def _format_extracted_texts(
    extracted_contents: list[dict],
    *,
    max_sources: int,
    per_source_limit: int,
    total_limit: int,
) -> tuple[str, dict[str, int]]:
    blocks: list[str] = []
    total_chars = 0
    used_sources = 0
    sorted_contents = _sorted_extracted_contents(extracted_contents)
    for index, content in enumerate(sorted_contents[:max_sources], start=1):
        meta = content.get("source_meta", {})
        snippet = _truncate_excerpt(str(meta.get("snippet", "")), 280)
        remaining = total_limit - total_chars
        if remaining <= 0:
            break
        text_limit = min(per_source_limit, remaining)
        body_text = _truncate_excerpt(str(content.get("text", "")), text_limit)
        block = "\n".join(
            [
                f"【来源{index}】",
                f"标题：{content.get('title', '无标题')}",
                f"链接：{content.get('url', '')}",
                f"域名：{meta.get('domain', '')}",
                f"来源类型：{meta.get('source_type', '')}",
                f"搜索意图：{meta.get('query_intent', '')}",
                f"摘要：{snippet}",
                f"正文节选：\n{body_text}",
            ]
        )
        block_len = len(block)
        if total_chars + block_len > total_limit and blocks:
            break
        blocks.append(block)
        total_chars += block_len
        used_sources += 1
    return "\n\n".join(blocks), {
        "selected_sources": used_sources,
        "available_sources": len(sorted_contents),
        "evidence_chars": total_chars,
        "per_source_limit": per_source_limit,
        "total_limit": total_limit,
    }


def _format_user_intent(user_intent: dict) -> str:
    hotspot_context = user_intent.get("hotspot_context") if isinstance(user_intent, dict) else None
    hotspot_lines: list[str] = []
    if isinstance(hotspot_context, dict):
        hotspot_lines = [
            f"热点标题：{hotspot_context.get('title', '')}",
            f"来源平台：{hotspot_context.get('platform_name', '')}",
            f"榜单排名：{hotspot_context.get('rank', '')}",
            f"热点评分：{hotspot_context.get('selection_score', '')}",
        ]
    return "\n".join(
        [
            f"主题：{user_intent.get('topic', '')}",
            f"原始输入主题：{user_intent.get('original_topic', '')}",
            f"主角色：{user_intent.get('primary_role', '')}",
            f"目标角色：{' / '.join(user_intent.get('target_roles', []))}",
            f"请求策略：{user_intent.get('requested_strategy', '')}",
            f"解析策略：{user_intent.get('resolved_strategy', '')}",
            f"文章目标：{user_intent.get('article_goal', '')}",
            f"补充风格：{user_intent.get('style_hint', '') or '无'}",
            *(hotspot_lines or ["热点上下文：未命中热点或未启用热点捕获"]),
        ]
    )


def _format_style_profile(style_profile: dict) -> str:
    return "\n".join(
        [
            f"style_archetype: {style_profile.get('style_archetype', '')}",
            f"style_source: {style_profile.get('style_source', '')}",
            f"tone: {style_profile.get('tone', '')}",
            f"title_style: {style_profile.get('title_style', '')}",
            f"opening_style: {style_profile.get('opening_style', '')}",
            f"paragraph_style: {style_profile.get('paragraph_style', '')}",
            f"evidence_style: {style_profile.get('evidence_style', '')}",
            f"term_explanation_rule: {style_profile.get('term_explanation_rule', '')}",
            f"reference_direction: {style_profile.get('reference_direction', '')}",
            f"focus_points: {', '.join(style_profile.get('focus_points', []))}",
            f"forbidden_patterns: {', '.join(style_profile.get('forbidden_patterns', []))}",
            f"style_prompt: {style_profile.get('style_prompt', '')}",
        ]
    )


def _format_article_blueprint(article_blueprint: dict) -> str:
    section_lines: list[str] = []
    for item in article_blueprint.get("section_outline", []):
        section_lines.append(
            "\n".join(
                [
                    str(item.get("heading", "")),
                    f"- goal: {item.get('goal', '')}",
                    f"- evidence_needed: {', '.join(item.get('evidence_needed', []))}",
                ]
            )
        )

    visualization_lines: list[str] = []
    for index, item in enumerate(article_blueprint.get("visualization_plan", []), start=1):
        visualization_lines.append(
            "\n".join(
                [
                    f"{index}. {item.get('title', '')}",
                    f"   - chart_type: {item.get('chart_type', '')}",
                    f"   - insight_goal: {item.get('insight_goal', '')}",
                    f"   - data_source_hint: {item.get('data_source_hint', '')}",
                    f"   - placement_heading: {item.get('placement_heading', '')}",
                ]
            )
        )

    return "\n".join(
        [
            f"article_type: {article_blueprint.get('article_type', '')}",
            f"structure_style: {article_blueprint.get('structure_style', '')}",
            f"title_strategy: {article_blueprint.get('title_strategy', '')}",
            f"opening_goal: {article_blueprint.get('opening_goal', '')}",
            f"reader_takeaway: {article_blueprint.get('reader_takeaway', '')}",
            f"search_focuses: {', '.join(article_blueprint.get('search_focuses', []))}",
            f"search_query_hints: {', '.join(article_blueprint.get('search_query_hints', []))}",
            f"ending_style: {article_blueprint.get('ending_style', '')}",
            f"markdown_requirements: {' | '.join(article_blueprint.get('markdown_requirements', []))}",
            f"requires_data_visualization: {bool(article_blueprint.get('requires_data_visualization', False))}",
            f"planned_illustrations: {article_blueprint.get('planned_illustrations', 3)}",
            "visualization_plan:",
            "\n".join(visualization_lines) if visualization_lines else "none",
            "section_outline:",
            "\n".join(section_lines),
        ]
    )


def _required_section_headings(article_blueprint: dict, article_plan: dict) -> list[str]:
    headings = [
        item.get("heading", "").strip()
        for item in article_blueprint.get("section_outline", [])
        if isinstance(item, dict) and item.get("heading")
    ]
    if headings:
        return headings
    return [heading for heading in article_plan.get("section_outline", []) if isinstance(heading, str) and heading.strip()]


def _extract_h2_headings(content: str) -> list[str]:
    return [match.strip() for match in re.findall(r"^##\s+(.+)$", content or "", flags=re.MULTILINE)]


def _normalize_heading_text(heading: str) -> str:
    heading = re.sub(r"^#+\s*", "", heading or "").strip()
    heading = re.sub(r"[\s,:：，。；;（）()\-_]+", "", heading)
    return heading


def _contains_keywords(text: str, keywords: tuple[str, ...]) -> bool:
    normalized = _normalize_heading_text(text)
    return any(keyword in normalized for keyword in keywords)


def _section_requirement_satisfied(required_section: str, headings: list[str]) -> bool:
    normalized_required = _normalize_heading_text(required_section)
    if not normalized_required:
        return True
    if _contains_keywords(normalized_required, RISK_SECTION_KEYWORDS):
        return any(_contains_keywords(heading, RISK_SECTION_KEYWORDS) for heading in headings)
    if _contains_keywords(normalized_required, ACTION_SECTION_KEYWORDS):
        return any(_contains_keywords(heading, ACTION_SECTION_KEYWORDS) for heading in headings)
    return any(_normalize_heading_text(heading) == normalized_required for heading in headings)


def _extract_illustration_indices(content: str) -> list[int]:
    return [int(value) for value in re.findall(r"\[插图(\d+)\]", content or "")]


def _requires_data_visualization(article_blueprint: dict, article_plan: dict) -> bool:
    return bool(
        article_blueprint.get("requires_data_visualization")
        or article_plan.get("requires_data_visualization")
    )


def _required_chart_count(article_blueprint: dict, article_plan: dict) -> int:
    visualization_plan = article_blueprint.get("visualization_plan") or article_plan.get("visualization_plan") or []
    if visualization_plan:
        return min(max(len(visualization_plan), 3), 5)
    planned_illustrations = int(article_blueprint.get("planned_illustrations") or article_plan.get("planned_illustrations", 3))
    return min(max(planned_illustrations, 3), 5)


def _extract_chart_indices(content: str) -> list[int]:
    matches = re.findall(r"^###\s*(?:图表|Chart)\s*(\d+)\s*[:：]", content or "", flags=re.MULTILINE)
    return [int(value) for value in matches]


def _count_markdown_chart_meta_lines(content: str, label: str) -> int:
    pattern = rf"^\s*-\s*{label}[:：].+$"
    return len(re.findall(pattern, content or "", flags=re.MULTILINE))


def _strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    return cleaned.strip()


def _extract_message_text(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, list):
        fragments: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if text:
                    fragments.append(str(text))
            elif isinstance(item, str):
                fragments.append(item)
        return "\n".join(fragments).strip()
    return str(content).strip()


def _remove_title_blocks(text: str) -> str:
    text = re.sub(r"^#\s*主标题[:：]\s*.+$", "", text, count=1, flags=re.MULTILINE)
    text = re.sub(r"^主标题[:：]\s*.+$", "", text, count=1, flags=re.MULTILINE)
    text = re.sub(r"^##\s*备选标题\s*$([\s\S]*?)(?=^##\s+\S|\Z)", "", text, count=1, flags=re.MULTILINE)
    text = re.sub(r"^备选标题\d*[:：]\s*.+$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^##\s*正文\s*$", "", text, count=1, flags=re.MULTILINE)
    return text.strip()


def _parse_fallback_article_output(raw_text: str) -> ArticleOutput:
    text = _strip_code_fences(raw_text)
    title = ""
    alt_titles: list[str] = []

    title_match = re.search(r"^#\s*主标题[:：]\s*(.+)$", text, flags=re.MULTILINE)
    if not title_match:
        title_match = re.search(r"^主标题[:：]\s*(.+)$", text, flags=re.MULTILINE)
    if title_match:
        title = title_match.group(1).strip()
    else:
        for line in text.splitlines():
            if line.strip().startswith("# "):
                title = line.strip()[2:].strip()
                break

    alt_section_match = re.search(r"^##\s*备选标题\s*$([\s\S]*?)(?=^##\s+\S|\Z)", text, flags=re.MULTILINE)
    if alt_section_match:
        for line in alt_section_match.group(1).splitlines():
            stripped = line.strip()
            if stripped.startswith(("- ", "* ")):
                alt_titles.append(stripped[2:].strip())
    if len(alt_titles) < 2:
        for line in text.splitlines():
            match = re.match(r"^备选标题\d*[:：]\s*(.+)$", line.strip())
            if match:
                alt_titles.append(match.group(1).strip())

    content_match = re.search(r"^##\s*正文\s*$([\s\S]*)$", text, flags=re.MULTILINE)
    if content_match:
        content = content_match.group(1).strip()
    else:
        content = _remove_title_blocks(text)

    return ArticleOutput(title=title, alt_titles=alt_titles[:2], content=content)


def _is_structured_output_parse_error(error: Exception) -> bool:
    message = str(error).lower()
    return "json_invalid" in message or "invalid json" in message


def _is_context_too_long_error(error: Exception) -> bool:
    message = str(error).lower()
    markers = (
        "message is too long",
        "input characters limit",
        "context length",
        "maximum context length",
        "token limit",
        "too many tokens",
        "too long",
    )
    return any(marker in message for marker in markers)


def _shrink_evidence_limits(total_limit: int, per_source_limit: int) -> tuple[int, int]:
    next_total = max(ARTICLE_MIN_TOTAL_EVIDENCE_LIMIT, total_limit // 2)
    next_per_source = max(ARTICLE_MIN_SOURCE_TEXT_LIMIT, per_source_limit // 2)
    next_per_source = min(next_per_source, next_total)
    return next_total, next_per_source


def _build_fallback_system_prompt(system_prompt: str) -> str:
    return (
        f"{system_prompt}\n\n"
        "如果无法稳定返回结构化 JSON，请严格按照下面的模板输出，不要添加模板之外的解释：\n\n"
        "# 主标题：{{主标题}}\n"
        "## 备选标题\n"
        "- {{备选标题1}}\n"
        "- {{备选标题2}}\n"
        "## 正文\n"
        "{{完整 Markdown 正文}}\n"
    )


def _validate_article_output(result: ArticleOutput, article_blueprint: dict, article_plan: dict) -> str | None:
    if not result.title or len(result.title.strip()) > 50:
        return "主标题为空或超过 50 字"
    if len(result.alt_titles) != 2:
        return "备选标题必须恰好 2 个"
    if any(not title.strip() or len(title.strip()) > 50 for title in result.alt_titles):
        return "备选标题存在空值或超过 50 字"

    content = (result.content or "").strip()
    if len(content) < 800:
        return "正文长度不足 800 字"

    required_sections = _required_section_headings(article_blueprint, article_plan)
    existing_headings = _extract_h2_headings(content)
    missing_sections = [
        section
        for section in required_sections
        if not _section_requirement_satisfied(section, existing_headings)
    ]
    if missing_sections:
        return f"缺少必要章节：{'、'.join(missing_sections)}"

    planned_illustrations = int(article_blueprint.get("planned_illustrations") or article_plan.get("planned_illustrations", 3))
    illustration_indices = _extract_illustration_indices(content)
    expected_indices = list(range(1, planned_illustrations + 1))
    if illustration_indices[:planned_illustrations] != expected_indices:
        return "插图标记必须按 [插图1][插图2][插图3] 顺序出现"

    if _requires_data_visualization(article_blueprint, article_plan):
        required_chart_count = _required_chart_count(article_blueprint, article_plan)
        chart_indices = _extract_chart_indices(content)
        expected_chart_indices = list(range(1, required_chart_count + 1))
        if chart_indices[:required_chart_count] != expected_chart_indices:
            return "金融/市场类文章必须按顺序包含 ### 图表1 到 ### 图表N 的 Markdown 图表块"
        if _count_markdown_chart_meta_lines(content, "数据来源") < required_chart_count:
            return "金融/市场类文章的每个图表都必须附带数据来源"
        if _count_markdown_chart_meta_lines(content, "图表说明") < required_chart_count:
            return "金融/市场类文章的每个图表都必须附带图表说明"

    if not any(_contains_keywords(heading, RISK_SECTION_KEYWORDS) for heading in existing_headings):
        return "缺少风险/局限类章节"
    if not any(_contains_keywords(heading, ACTION_SECTION_KEYWORDS) for heading in existing_headings):
        return "缺少行动建议类章节"
    return None


async def generate_article_node(state: WorkflowState) -> dict:
    """Generate final article content."""
    task_id = state["task_id"]
    extracted_contents = state.get("extracted_contents", [])
    generation_config = state.get("generation_config", {})
    user_intent = state.get("user_intent", {})
    style_profile = state.get("style_profile", {})
    article_blueprint = state.get("article_blueprint", {})
    article_plan = state.get("article_plan", {})

    start_time = time.monotonic()
    logger.info(
        "skill_start",
        task_id=task_id,
        skill="generate_article",
        status="running",
        source_count=len(extracted_contents),
    )

    text_model_config = get_model_config().text
    api_key = text_model_config.api_key
    if not api_key:
        duration_ms = round((time.monotonic() - start_time) * 1000)
        error_msg = "text model API key is not configured"
        logger.error(
            "skill_failed",
            task_id=task_id,
            skill="generate_article",
            status="failed",
            duration_ms=duration_ms,
            error=error_msg,
        )
        return {
            "status": "failed",
            "current_skill": "generate_article",
            "error": error_msg,
        }

    if not extracted_contents:
        duration_ms = round((time.monotonic() - start_time) * 1000)
        error_msg = "无提取内容，无法生成文章"
        logger.error(
            "skill_failed",
            task_id=task_id,
            skill="generate_article",
            status="failed",
            duration_ms=duration_ms,
            error=error_msg,
        )
        return {
            "status": "failed",
            "current_skill": "generate_article",
            "error": error_msg,
        }

    system_prompt = (
        "你是中文公众号主编。"
        "请基于用户意图、风格画像、文章蓝图和公开证据写一篇可直接发布的 Markdown 文章。"
        "正文必须完整保留蓝图中的所有 H2 标题，不要改写章节标题。"
        "文章必须是 Markdown，不要输出 HTML。"
        "段落要短，适合手机阅读，关键数据或结论可以使用 **加粗**。"
        "如果公开资料之间存在冲突，要明确写出“公开资料存在分歧”；如果证据不足，要明确写出“公开资料尚不足以证明”。"
        "请按顺序使用 `[插图1]...[插图N]` 占位，不要跳号，不要重复。"
        "如果蓝图要求数据可视化，请严格使用如下 Markdown 图表块格式："
        "`### 图表N：标题`，下一行放 `[插图N]`，然后分别写 `- 数据来源：...` 和 `- 图表说明：...`。"
        "财经、金融、宏观、能源、商品和市场类文章必须做到图文结合，图表块要和正文分析紧密对应。"
    )
    human_prompt = (
        "用户主题：\n{keywords}\n\n"
        "用户意图：\n{user_intent}\n\n"
        "文章生成配置：\n{generation_config}\n\n"
        "风格画像：\n{style_profile}\n\n"
        "文章蓝图：\n{article_blueprint}\n\n"
        "兼容 article_plan：\n{article_plan}\n\n"
        "证据素材：\n{extracted_texts}\n\n"
        "修正要求：\n{retry_feedback}"
    )
    fallback_system_prompt = _build_fallback_system_prompt(system_prompt)

    prompt = ChatPromptTemplate.from_messages([("system", system_prompt), ("human", human_prompt)])
    fallback_prompt = ChatPromptTemplate.from_messages([("system", fallback_system_prompt), ("human", human_prompt)])

    base_llm = ChatOpenAI(
        model=text_model_config.model,
        api_key=api_key,
        base_url=text_model_config.base_url or None,
        max_tokens=4500,
        temperature=0.65,
    )
    structured_chain = prompt | base_llm.with_structured_output(ArticleOutput)
    fallback_chain = fallback_prompt | base_llm

    retry_count = 0
    max_retries = 3
    structured_output_enabled = True
    final_article: ArticleOutput | None = None
    error_msg: str | None = None
    retry_feedback = "首次生成，请严格按蓝图输出完整文章。"
    evidence_total_limit = ARTICLE_TOTAL_EVIDENCE_LIMIT
    evidence_per_source_limit = ARTICLE_SOURCE_TEXT_LIMIT
    model_context = build_model_context(
        model=text_model_config.model,
        base_url=text_model_config.base_url,
        api_key=api_key,
        structured_output="ArticleOutput",
    )

    while retry_count < max_retries:
        try:
            logger.info("generate_article_attempt", task_id=task_id, attempt=retry_count + 1)
            formatted_texts, evidence_stats = _format_extracted_texts(
                extracted_contents,
                max_sources=ARTICLE_MAX_SOURCES,
                per_source_limit=evidence_per_source_limit,
                total_limit=evidence_total_limit,
            )
            payload = {
                "keywords": state.get("keywords", ""),
                "user_intent": _format_user_intent(user_intent),
                "generation_config": generation_config,
                "style_profile": _format_style_profile(style_profile),
                "article_blueprint": _format_article_blueprint(article_blueprint),
                "article_plan": article_plan,
                "extracted_texts": formatted_texts,
                "retry_feedback": retry_feedback,
            }
            log_model_request(
                logger,
                task_id=task_id,
                skill="generate_article",
                context={
                    **model_context,
                    "attempt": retry_count + 1,
                    "structured_output_enabled": structured_output_enabled,
                    **evidence_stats,
                },
                request=payload,
            )

            if structured_output_enabled:
                try:
                    result = await structured_chain.ainvoke(payload)
                    log_model_response(
                        logger,
                        task_id=task_id,
                        skill="generate_article",
                        context={**model_context, "attempt": retry_count + 1, "response_mode": "structured"},
                        response=result.model_dump(),
                    )
                except Exception as structured_exc:
                    if _is_structured_output_parse_error(structured_exc):
                        structured_output_enabled = False
                        logger.info(
                            "generate_article_disable_structured_output_for_task",
                            task_id=task_id,
                            attempt=retry_count + 1,
                            error=str(structured_exc),
                        )
                    else:
                        logger.warning(
                            "generate_article_structured_output_failed",
                            task_id=task_id,
                            attempt=retry_count + 1,
                            error=str(structured_exc),
                        )
                    if _is_context_too_long_error(structured_exc):
                        raise
                    raw_result = await fallback_chain.ainvoke(payload)
                    raw_text = _extract_message_text(raw_result)
                    log_model_response(
                        logger,
                        task_id=task_id,
                        skill="generate_article",
                        context={**model_context, "attempt": retry_count + 1, "response_mode": "fallback_raw"},
                        response=raw_text,
                    )
                    result = _parse_fallback_article_output(raw_text)
                    log_model_response(
                        logger,
                        task_id=task_id,
                        skill="generate_article",
                        context={**model_context, "attempt": retry_count + 1, "response_mode": "fallback_parsed"},
                        response=result.model_dump(),
                    )
            else:
                raw_result = await fallback_chain.ainvoke(payload)
                raw_text = _extract_message_text(raw_result)
                log_model_response(
                    logger,
                    task_id=task_id,
                    skill="generate_article",
                    context={**model_context, "attempt": retry_count + 1, "response_mode": "fallback_raw"},
                    response=raw_text,
                )
                result = _parse_fallback_article_output(raw_text)
                log_model_response(
                    logger,
                    task_id=task_id,
                    skill="generate_article",
                    context={**model_context, "attempt": retry_count + 1, "response_mode": "fallback_parsed"},
                    response=result.model_dump(),
                )

            validation_error = _validate_article_output(result, article_blueprint, article_plan)
            if not validation_error:
                final_article = result
                break
            error_msg = validation_error
            retry_feedback = (
                "上一轮输出不合格，请完整重写，重点修复这些问题："
                f"{validation_error}。不要删除蓝图中的章节，不要遗漏插图或图表标记。"
            )
        except Exception as exc:  # noqa: BLE001
            error_msg = str(exc)
            if _is_context_too_long_error(exc):
                next_total_limit, next_per_source_limit = _shrink_evidence_limits(
                    evidence_total_limit,
                    evidence_per_source_limit,
                )
                if next_total_limit == evidence_total_limit and next_per_source_limit == evidence_per_source_limit:
                    retry_feedback = "输入上下文仍然过长，无法继续压缩，请减少搜索结果或更换上下文更大的模型。"
                else:
                    logger.warning(
                        "generate_article_context_too_long_shrinking",
                        task_id=task_id,
                        attempt=retry_count + 1,
                        previous_total_limit=evidence_total_limit,
                        previous_per_source_limit=evidence_per_source_limit,
                        next_total_limit=next_total_limit,
                        next_per_source_limit=next_per_source_limit,
                        error=error_msg,
                    )
                    evidence_total_limit = next_total_limit
                    evidence_per_source_limit = next_per_source_limit
                    retry_feedback = (
                        "上一轮输入上下文过长，请基于更精简的证据素材重新输出完整文章。"
                        "优先保留最关键的事实、背景、风险和行动建议。"
                    )
            else:
                retry_feedback = "上一轮调用失败，请完整重写，并确保结构、Markdown、图表块和插图标记都满足要求。"
            logger.warning(
                "generate_article_failed_attempt",
                task_id=task_id,
                attempt=retry_count + 1,
                error=error_msg,
            )
        retry_count += 1

    duration_ms = round((time.monotonic() - start_time) * 1000)
    if not final_article:
        final_error = error_msg or "文章生成失败"
        logger.error(
            "skill_failed",
            task_id=task_id,
            skill="generate_article",
            status="failed",
            duration_ms=duration_ms,
            error=final_error,
        )
        return {
            "status": "failed",
            "current_skill": "generate_article",
            "error": final_error,
        }

    logger.info(
        "skill_done",
        task_id=task_id,
        skill="generate_article",
        status="done",
        duration_ms=duration_ms,
        content_length=len(final_article.content),
    )
    return {
        "status": "running",
        "current_skill": "generate_article",
        "progress": 80,
        "generated_article": {
            "title": final_article.title,
            "alt_titles": final_article.alt_titles,
            "content": final_article.content,
            "cover_image": "",
            "illustrations": [],
        },
    }
