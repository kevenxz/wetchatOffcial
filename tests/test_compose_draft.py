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
