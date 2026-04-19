from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from workflow.skills.compose_draft import compose_draft_node


@pytest.mark.asyncio
async def test_compose_draft_generates_article_from_blueprint_and_evidence() -> None:
    state = {
        "task_brief": {"topic": "AI 智能体创业"},
        "planning_state": {
            "article_type": {"type_id": "trend_analysis", "title_style": "insight_first"},
            "article_blueprint": {"sections": [{"heading": "趋势判断", "goal": "解释驱动因素"}]},
        },
        "research_state": {"evidence_pack": {"confirmed_facts": [{"claim": "融资升温"}]}},
    }

    result = await compose_draft_node(state)

    assert result["writing_state"]["draft"]["title"]
    assert "趋势判断" in result["writing_state"]["draft"]["content"]


@pytest.mark.asyncio
async def test_compose_draft_uses_model_to_generate_structured_draft() -> None:
    state = {
        "task_id": "task-1",
        "keywords": "机器人融资潮",
        "task_brief": {"topic": "机器人融资潮"},
        "planning_state": {
            "article_type": {"type_id": "trend_analysis", "title_style": "insight_first"},
            "article_blueprint": {
                "thesis": "机器人融资潮正在从事件走向趋势",
                "sections": [
                    {"heading": "趋势判断", "goal": "解释驱动因素"},
                    {"heading": "风险边界", "goal": "说明不确定性"},
                ],
            },
        },
        "research_state": {
            "evidence_pack": {
                "confirmed_facts": [{"claim": "头部机器人公司融资升温"}],
                "usable_data_points": [{"claim": "2026 年融资笔数上升"}],
            }
        },
        "writing_state": {},
    }

    with patch("workflow.skills.compose_draft.get_model_config") as mock_get_model_config:
        with patch("workflow.skills.compose_draft.ChatPromptTemplate") as mock_prompt_class:
            with patch("workflow.skills.compose_draft.ChatOpenAI") as mock_chat_openai:
                model_config = MagicMock()
                model_config.text.api_key = "text-key"
                model_config.text.base_url = "https://text.example.com/v1"
                model_config.text.model = "text-model"
                mock_get_model_config.return_value = model_config

                prompt = MagicMock()
                chain = AsyncMock()
                llm = MagicMock()
                llm.with_structured_output.return_value = MagicMock(name="structured-llm")
                mock_prompt_class.from_messages.return_value = prompt
                prompt.__or__.return_value = chain
                mock_chat_openai.return_value = llm

                chain.ainvoke.return_value = {
                    "title": "机器人融资潮进入第二阶段",
                    "content": "## 趋势判断\n融资从个案走向密集出现。\n\n## 风险边界\n估值和量产仍有不确定性。",
                    "summary": "融资热度提升，但兑现仍需观察。",
                }

                result = await compose_draft_node(state)

    assert result["writing_state"]["draft"]["title"] == "机器人融资潮进入第二阶段"
    assert "## 趋势判断" in result["generated_article"]["content"]
    assert result["writing_state"]["draft"]["summary"] == "融资热度提升，但兑现仍需观察。"
    mock_chat_openai.assert_called_once_with(
        model="text-model",
        api_key="text-key",
        base_url="https://text.example.com/v1",
        max_tokens=2600,
        temperature=0.55,
    )


@pytest.mark.asyncio
async def test_compose_draft_passes_revision_brief_to_model() -> None:
    state = {
        "task_id": "task-2",
        "keywords": "机器人融资潮",
        "task_brief": {"topic": "机器人融资潮"},
        "planning_state": {
            "article_type": {"type_id": "trend_analysis", "title_style": "insight_first"},
            "article_blueprint": {
                "thesis": "机器人融资潮正在从事件走向趋势",
                "sections": [
                    {"heading": "趋势判断", "goal": "解释驱动因素"},
                    {"heading": "风险边界", "goal": "说明不确定性"},
                ],
            },
        },
        "research_state": {"evidence_pack": {"confirmed_facts": [{"claim": "头部机器人公司融资升温"}]}},
        "writing_state": {
            "revision_brief": {
                "mode": "targeted_revision",
                "guidance": ["补充数据依据", "收紧结论表述"],
                "findings": [{"type": "evidence", "message": "结论支撑不足"}],
            }
        },
    }

    with patch("workflow.skills.compose_draft.get_model_config") as mock_get_model_config:
        with patch("workflow.skills.compose_draft.ChatPromptTemplate") as mock_prompt_class:
            with patch("workflow.skills.compose_draft.ChatOpenAI") as mock_chat_openai:
                model_config = MagicMock()
                model_config.text.api_key = "text-key"
                model_config.text.base_url = "https://text.example.com/v1"
                model_config.text.model = "text-model"
                mock_get_model_config.return_value = model_config

                prompt = MagicMock()
                chain = AsyncMock()
                llm = MagicMock()
                llm.with_structured_output.return_value = MagicMock(name="structured-llm")
                mock_prompt_class.from_messages.return_value = prompt
                prompt.__or__.return_value = chain
                mock_chat_openai.return_value = llm

                seen_payload: dict = {}

                async def fake_ainvoke(payload: dict) -> dict:
                    seen_payload.update(payload)
                    return {
                        "title": "修订后的机器人融资潮判断",
                        "content": "## 趋势判断\n补充了数据依据。\n\n## 风险边界\n结论表述已收紧。",
                        "summary": "按评审意见完成定向修订。",
                    }

                chain.ainvoke.side_effect = fake_ainvoke

                result = await compose_draft_node(state)

    assert seen_payload["revision_brief"]["guidance"] == ["补充数据依据", "收紧结论表述"]
    assert result["writing_state"]["draft"]["title"] == "修订后的机器人融资潮判断"
    assert result["writing_state"]["revision_brief"] == {}


@pytest.mark.asyncio
async def test_compose_draft_passes_research_quality_summary_to_model() -> None:
    state = {
        "task_id": "task-3",
        "task_brief": {"topic": "机器人商业化"},
        "planning_state": {
            "article_type": {"type_id": "trend_analysis", "title_style": "insight_first"},
            "article_blueprint": {
                "thesis": "机器人商业化进入验证期",
                "sections": [
                    {"heading": "先给结论", "goal": "界定判断范围"},
                    {"heading": "风险边界", "goal": "说明不确定性"},
                ],
            },
        },
        "research_state": {
            "evidence_pack": {
                "confirmed_facts": [{"claim": "头部公司融资回暖"}],
                "research_gaps": ["missing_data_evidence"],
                "quality_summary": {
                    "source_coverage": {"official": 1, "community": 1},
                    "angle_coverage": {"fact": 1, "opinion": 1},
                },
            }
        },
        "writing_state": {},
    }

    with patch("workflow.skills.compose_draft.get_model_config") as mock_get_model_config:
        with patch("workflow.skills.compose_draft.ChatPromptTemplate") as mock_prompt_class:
            with patch("workflow.skills.compose_draft.ChatOpenAI") as mock_chat_openai:
                model_config = MagicMock()
                model_config.text.api_key = "text-key"
                model_config.text.base_url = "https://text.example.com/v1"
                model_config.text.model = "text-model"
                mock_get_model_config.return_value = model_config

                prompt = MagicMock()
                chain = AsyncMock()
                llm = MagicMock()
                llm.with_structured_output.return_value = MagicMock(name="structured-llm")
                mock_prompt_class.from_messages.return_value = prompt
                prompt.__or__.return_value = chain
                mock_chat_openai.return_value = llm

                seen_payload: dict = {}

                async def fake_ainvoke(payload: dict) -> dict:
                    seen_payload.update(payload)
                    return {
                        "title": "机器人商业化进入验证期",
                        "content": "## 先给结论\n内容\n\n## 风险边界\n内容",
                        "summary": "摘要",
                    }

                chain.ainvoke.side_effect = fake_ainvoke

                await compose_draft_node(state)

    assert "research_gaps: missing_data_evidence" in seen_payload["evidence_pack"]
    assert "source_coverage" in seen_payload["evidence_pack"]


@pytest.mark.asyncio
async def test_compose_draft_model_prompt_allows_heading_refinement_for_wechat() -> None:
    state = {
        "task_id": "task-4",
        "task_brief": {"topic": "机器人公司为什么开始重做销售体系"},
        "planning_state": {
            "article_type": {"type_id": "trend_analysis", "title_style": "insight_first"},
            "article_blueprint": {
                "thesis": "销售体系重做背后是商业化压力上升",
                "sections": [
                    {"heading": "销售体系为什么突然变成头号问题", "goal": "定义问题"},
                    {"heading": "风险边界在哪里", "goal": "约束结论"},
                ],
            },
        },
        "research_state": {"evidence_pack": {"confirmed_facts": [{"claim": "公司开始扩销售"}]}},
        "writing_state": {},
    }

    with patch("workflow.skills.compose_draft.get_model_config") as mock_get_model_config:
        with patch("workflow.skills.compose_draft.ChatPromptTemplate") as mock_prompt_class:
            with patch("workflow.skills.compose_draft.ChatOpenAI") as mock_chat_openai:
                model_config = MagicMock()
                model_config.text.api_key = "text-key"
                model_config.text.base_url = "https://text.example.com/v1"
                model_config.text.model = "text-model"
                mock_get_model_config.return_value = model_config

                prompt = MagicMock()
                chain = AsyncMock()
                llm = MagicMock()
                llm.with_structured_output.return_value = MagicMock(name="structured-llm")
                mock_prompt_class.from_messages.return_value = prompt
                prompt.__or__.return_value = chain
                mock_chat_openai.return_value = llm
                chain.ainvoke.return_value = {
                    "title": "机器人公司开始重做销售，不只是组织调整",
                    "content": "## 销售为什么突然成了头号问题\n内容\n\n## 风险边界在哪里\n内容",
                    "summary": "摘要",
                }

                await compose_draft_node(state)

    messages = mock_prompt_class.from_messages.call_args.args[0]
    system_prompt = messages[0][1]
    assert "wechat" in system_prompt.lower()
    assert "refine section headings" in system_prompt.lower()
    assert "keep all provided h2 headings" not in system_prompt.lower()
