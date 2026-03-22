from __future__ import annotations

"""Tests for generate_article skill."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.models import ImageModelConfig, ModelConfig, TextModelConfig
from langchain_core.prompts import ChatPromptTemplate

from workflow.skills.generate_article import ArticleOutput, _build_fallback_system_prompt, generate_article_node
from workflow.state import WorkflowState


def _valid_content() -> str:
    paragraph = "这是用于测试的正文内容，强调信息密度、结构完整和公众号可读性。"
    repeated = paragraph * 18
    return "\n\n".join(
        [
            "## 开篇：为什么现在值得关注",
            repeated,
            "## 关键信息与背景",
            f"{repeated}[插图1]",
            "## 技术拆解：核心原理与能力边界",
            f"{repeated}[插图2]",
            "## 投资者视角：最该关注什么",
            f"{repeated}[插图3]",
            "## 局限与风险",
            repeated,
            "## 行动建议",
            repeated,
        ]
    )


def _valid_content_with_flexible_headings() -> str:
    paragraph = "这是用于测试的正文内容，强调信息密度、结构完整和公众号可读性。"
    repeated = paragraph * 18
    return "\n\n".join(
        [
            "## 开篇：为什么现在值得关注",
            repeated,
            "## 关键信息与背景",
            f"{repeated}[插图1]",
            "## 技术拆解：核心原理与能力边界",
            f"{repeated}[插图2]",
            "## 投资者视角：最该关注什么",
            f"{repeated}[插图3]",
            "## 风险与不确定性",
            repeated,
            "## 下一步怎么跟踪",
            repeated,
        ]
    )


def _model_config(api_key: str = "text-key", model: str = "text-model", base_url: str | None = "https://text.example.com/v1") -> ModelConfig:
    return ModelConfig(
        text=TextModelConfig(api_key=api_key, model=model, base_url=base_url),
        image=ImageModelConfig(enabled=False, api_key="", model="dall-e-3", base_url=None),
    )


@pytest.fixture
def mock_state() -> WorkflowState:
    return WorkflowState(
        task_id="test_task_123",
        keywords="ai news",
        generation_config={"audience_roles": ["投资者"], "article_strategy": "trend_outlook"},
        user_intent={
            "topic": "AI Agent",
            "primary_role": "投资者",
            "target_roles": ["投资者"],
            "requested_strategy": "trend_outlook",
            "resolved_strategy": "trend_outlook",
            "article_goal": "帮助投资者理解商业化机会和风险",
            "style_hint": "",
        },
        style_profile={
            "style_archetype": "finance_rational",
            "style_source": "auto_inferred",
            "tone": "理性克制，少煽动，多判断",
            "title_style": "标题突出价值判断与关键变量",
            "opening_style": "开头先解释为什么现在值得关注",
            "paragraph_style": "短段落，高信息密度",
            "evidence_style": "优先使用数据、案例和风险提示",
            "term_explanation_rule": "术语 + 中文解释 + 一句话类比",
            "reference_direction": "参考财经公众号的克制分析写法",
            "focus_points": ["商业价值", "竞争格局", "风险因素"],
            "forbidden_patterns": ["空泛赞美"],
            "style_prompt": "采用理性克制的科技公众号写法。",
        },
        article_blueprint={
            "title_strategy": "标题突出趋势判断和价值点",
            "opening_goal": "解释为什么现在值得关注",
            "reader_takeaway": "帮助投资者理解机会和风险",
            "search_focuses": ["官方发布", "行业数据", "风险争议"],
            "ending_style": "结尾收束观点并给出行动建议",
            "planned_illustrations": 3,
            "section_outline": [
                {"heading": "## 开篇：为什么现在值得关注", "goal": "交代时间点", "evidence_needed": ["背景"]},
                {"heading": "## 关键信息与背景", "goal": "背景信息", "evidence_needed": ["事实"]},
                {"heading": "## 技术拆解：核心原理与能力边界", "goal": "技术分析", "evidence_needed": ["原理"]},
                {"heading": "## 投资者视角：最该关注什么", "goal": "投资视角", "evidence_needed": ["商业化"]},
                {"heading": "## 局限与风险", "goal": "写风险", "evidence_needed": ["风险"]},
                {"heading": "## 行动建议", "goal": "给建议", "evidence_needed": ["建议"]},
            ],
        },
        search_queries=[],
        search_results=["https://example.com/1"],
        extracted_contents=[
            {"url": "https://example.com/1", "title": "Page 1", "text": "Some text content here"},
        ],
        article_plan={
            "primary_role": "投资者",
            "audience_roles": ["投资者"],
            "requested_strategy": "trend_outlook",
            "resolved_strategy": "trend_outlook",
            "resolved_strategy_label": "趋势展望式",
            "title_strategy": "标题要突出趋势判断、行业变量和行动窗口。",
            "section_outline": [
                "## 开篇：为什么现在值得关注",
                "## 关键信息与背景",
                "## 技术拆解：核心原理与能力边界",
                "## 投资者视角：最该关注什么",
                "## 局限与风险",
                "## 行动建议",
            ],
            "planned_illustrations": 3,
        },
        generated_article={},
        draft_info=None,
        retry_count=0,
        error=None,
        status="running",
        current_skill="",
        progress=0,
        skip_auto_push=False,
    )


@pytest.mark.asyncio
async def test_generate_article_success_uses_text_model_config(mock_state: WorkflowState) -> None:
    with patch("workflow.skills.generate_article.get_model_config", return_value=_model_config()):
        with patch("workflow.skills.generate_article.ChatPromptTemplate") as mock_prompt_class:
            with patch("workflow.skills.generate_article.ChatOpenAI") as mock_chat_openai:
                structured_prompt = MagicMock()
                fallback_prompt = MagicMock()
                structured_chain = AsyncMock()
                fallback_chain = AsyncMock()
                llm = MagicMock()
                llm.with_structured_output.return_value = MagicMock(name="structured-llm")

                mock_prompt_class.from_messages.side_effect = [structured_prompt, fallback_prompt]
                structured_prompt.__or__.return_value = structured_chain
                fallback_prompt.__or__.return_value = fallback_chain
                mock_chat_openai.return_value = llm

                fake_output = ArticleOutput(
                    title="投资者现在该怎么看 AI Agent",
                    alt_titles=["AI Agent 机会与风险判断", "从资本视角看 AI Agent"],
                    content=_valid_content(),
                )
                structured_chain.ainvoke.return_value = fake_output

                result = await generate_article_node(mock_state)

    assert result["status"] == "running"
    assert result["current_skill"] == "generate_article"
    assert result["generated_article"]["title"] == fake_output.title
    assert "[插图1]" in result["generated_article"]["content"]
    mock_chat_openai.assert_called_once_with(
        model="text-model",
        api_key="text-key",
        base_url="https://text.example.com/v1",
        max_tokens=4500,
        temperature=0.65,
    )


@pytest.mark.asyncio
async def test_generate_article_missing_api_key(mock_state: WorkflowState) -> None:
    with patch("workflow.skills.generate_article.get_model_config", return_value=_model_config(api_key="", base_url=None)):
        result = await generate_article_node(mock_state)

    assert result["status"] == "failed"
    assert "api key" in result["error"].lower()


@pytest.mark.asyncio
async def test_generate_article_invalid_structure(mock_state: WorkflowState) -> None:
    with patch("workflow.skills.generate_article.get_model_config", return_value=_model_config()):
        with patch("workflow.skills.generate_article.ChatPromptTemplate") as mock_prompt_class:
            with patch("workflow.skills.generate_article.ChatOpenAI") as mock_chat_openai:
                structured_prompt = MagicMock()
                fallback_prompt = MagicMock()
                structured_chain = AsyncMock()
                fallback_chain = AsyncMock()
                llm = MagicMock()
                llm.with_structured_output.return_value = MagicMock(name="structured-llm")

                mock_prompt_class.from_messages.side_effect = [structured_prompt, fallback_prompt]
                structured_prompt.__or__.return_value = structured_chain
                fallback_prompt.__or__.return_value = fallback_chain
                mock_chat_openai.return_value = llm

                structured_chain.ainvoke.return_value = ArticleOutput(
                    title="Test Title",
                    alt_titles=["Alt 1", "Alt 2"],
                    content="Too short",
                )

                result = await generate_article_node(mock_state)

    assert result["status"] == "failed"
    assert "不足" in result["error"] or "失败" in result["error"]


@pytest.mark.asyncio
async def test_generate_article_fallback_to_text_parse(mock_state: WorkflowState) -> None:
    with patch("workflow.skills.generate_article.get_model_config", return_value=_model_config()):
        with patch("workflow.skills.generate_article.ChatPromptTemplate") as mock_prompt_class:
            with patch("workflow.skills.generate_article.ChatOpenAI") as mock_chat_openai:
                structured_prompt = MagicMock()
                fallback_prompt = MagicMock()
                structured_chain = AsyncMock()
                fallback_chain = AsyncMock()
                llm = MagicMock()
                llm.with_structured_output.return_value = MagicMock(name="structured-llm")

                mock_prompt_class.from_messages.side_effect = [structured_prompt, fallback_prompt]
                structured_prompt.__or__.return_value = structured_chain
                fallback_prompt.__or__.return_value = fallback_chain
                mock_chat_openai.return_value = llm

                structured_chain.ainvoke.side_effect = ValueError("Invalid JSON")
                fallback_chain.ainvoke.return_value = type(
                    "RawMessage",
                    (),
                    {
                        "content": (
                            "# 主标题：投资者现在该怎么看 AI Agent\n"
                            "## 备选标题\n"
                            "- AI Agent 机会与风险判断\n"
                            "- 从资本视角看 AI Agent\n"
                            "## 正文\n"
                            f"{_valid_content()}"
                        ),
                    },
                )()

                result = await generate_article_node(mock_state)

    assert result["status"] == "running"
    assert result["generated_article"]["title"] == "投资者现在该怎么看 AI Agent"


@pytest.mark.asyncio
async def test_generate_article_accepts_flexible_risk_and_action_headings(mock_state: WorkflowState) -> None:
    with patch("workflow.skills.generate_article.get_model_config", return_value=_model_config()):
        with patch("workflow.skills.generate_article.ChatPromptTemplate") as mock_prompt_class:
            with patch("workflow.skills.generate_article.ChatOpenAI") as mock_chat_openai:
                structured_prompt = MagicMock()
                fallback_prompt = MagicMock()
                structured_chain = AsyncMock()
                fallback_chain = AsyncMock()
                llm = MagicMock()
                llm.with_structured_output.return_value = MagicMock(name="structured-llm")

                mock_prompt_class.from_messages.side_effect = [structured_prompt, fallback_prompt]
                structured_prompt.__or__.return_value = structured_chain
                fallback_prompt.__or__.return_value = fallback_chain
                mock_chat_openai.return_value = llm

                structured_chain.ainvoke.return_value = ArticleOutput(
                    title="投资者现在该怎么看 AI Agent",
                    alt_titles=["AI Agent 机会与风险判断", "从资本视角看 AI Agent"],
                    content=_valid_content_with_flexible_headings(),
                )

                result = await generate_article_node(mock_state)

    assert result["status"] == "running"
    assert "## 风险与不确定性" in result["generated_article"]["content"]
    assert "## 下一步怎么跟踪" in result["generated_article"]["content"]


def test_fallback_prompt_escapes_literal_placeholders() -> None:
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", _build_fallback_system_prompt("system prompt")),
            ("human", "{keywords}\n{retry_feedback}"),
        ]
    )

    assert set(prompt.input_variables) == {"keywords", "retry_feedback"}


@pytest.mark.asyncio
async def test_generate_article_shrinks_evidence_when_context_too_long(mock_state: WorkflowState) -> None:
    mock_state["extracted_contents"] = [
        {
            "url": f"https://example.com/{index}",
            "title": f"Page {index}",
            "text": "长文本" * 4000,
            "source_meta": {
                "domain": "example.com",
                "source_type": "media",
                "query_intent": "reputable_news",
                "snippet": "摘要",
                "final_score": 0.9 - index * 0.01,
            },
        }
        for index in range(1, 5)
    ]
    with patch("workflow.skills.generate_article.get_model_config", return_value=_model_config()):
        with patch("workflow.skills.generate_article.ChatPromptTemplate") as mock_prompt_class:
            with patch("workflow.skills.generate_article.ChatOpenAI") as mock_chat_openai:
                structured_prompt = MagicMock()
                fallback_prompt = MagicMock()
                structured_chain = AsyncMock()
                fallback_chain = AsyncMock()
                llm = MagicMock()
                llm.with_structured_output.return_value = MagicMock(name="structured-llm")

                mock_prompt_class.from_messages.side_effect = [structured_prompt, fallback_prompt]
                structured_prompt.__or__.return_value = structured_chain
                fallback_prompt.__or__.return_value = fallback_chain
                mock_chat_openai.return_value = llm

                fake_output = ArticleOutput(
                    title="投资者现在该怎么看 AI Agent",
                    alt_titles=["AI Agent 机会与风险判断", "从资本视角看 AI Agent"],
                    content=_valid_content(),
                )
                structured_chain.ainvoke.side_effect = [
                    ValueError("input characters limit is 393216"),
                    fake_output,
                ]

                result = await generate_article_node(mock_state)

    assert result["status"] == "running"
    assert structured_chain.ainvoke.await_count == 2
    assert fallback_chain.ainvoke.await_count == 0
