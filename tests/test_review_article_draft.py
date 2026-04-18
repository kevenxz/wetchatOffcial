from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from workflow.skills.review_article_draft import review_article_draft_node


@pytest.mark.asyncio
async def test_review_article_draft_uses_model_and_records_revision_guidance() -> None:
    state = {
        "task_id": "task-1",
        "task_brief": {"topic": "机器人融资潮"},
        "writing_state": {
            "draft": {
                "title": "机器人融资潮进入第二阶段",
                "content": "## 趋势判断\n融资热度明显上升。\n\n## 风险边界\n量产兑现仍存在不确定性。",
            }
        },
        "planning_state": {
            "article_type": {"type_id": "trend_analysis"},
            "quality_thresholds": {"article": 80},
        },
        "research_state": {
            "evidence_pack": {
                "confirmed_facts": [{"claim": "头部公司融资升温"}],
                "usable_data_points": [{"claim": "融资笔数同比上升"}],
            }
        },
    }

    with patch("workflow.skills.review_article_draft.get_model_config") as mock_get_model_config:
        with patch("workflow.skills.review_article_draft.ChatPromptTemplate") as mock_prompt_class:
            with patch("workflow.skills.review_article_draft.ChatOpenAI") as mock_chat_openai:
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
                    "passed": False,
                    "score": 72,
                    "findings": [{"type": "evidence", "message": "结论支撑不足"}],
                    "revision_guidance": ["补充数据依据", "收紧结论表述"],
                }

                result = await review_article_draft_node(state)

    assert result["writing_state"]["article_review"]["passed"] is False
    assert result["writing_state"]["article_review"]["score"] == 72
    assert result["writing_state"]["review_findings"][0]["message"] == "结论支撑不足"
    assert result["writing_state"]["revision_guidance"] == ["补充数据依据", "收紧结论表述"]
    mock_chat_openai.assert_called_once_with(
        model="text-model",
        api_key="text-key",
        base_url="https://text.example.com/v1",
        max_tokens=1400,
        temperature=0.2,
    )


@pytest.mark.asyncio
async def test_review_article_draft_falls_back_to_rule_checks_without_api_key() -> None:
    state = {
        "task_id": "task-2",
        "writing_state": {
            "draft": {
                "title": "机器人融资潮进入第二阶段",
                "content": "## 趋势判断\n融资热度明显上升。",
            }
        },
    }

    with patch("workflow.skills.review_article_draft.get_model_config") as mock_get_model_config:
        model_config = MagicMock()
        model_config.text.api_key = ""
        model_config.text.base_url = None
        model_config.text.model = "text-model"
        mock_get_model_config.return_value = model_config

        result = await review_article_draft_node(state)

    assert result["writing_state"]["article_review"]["passed"] is False
    assert result["writing_state"]["review_findings"]


@pytest.mark.asyncio
async def test_review_article_draft_fallback_flags_thin_evidence() -> None:
    state = {
        "task_id": "task-3",
        "task_brief": {"topic": "机器人商业化"},
        "writing_state": {
            "draft": {
                "title": "机器人商业化判断",
                "content": "## 先给结论\n机器人商业化正在提速。\n\n## 风险边界\n仍需继续观察。",
            }
        },
        "research_state": {
            "evidence_pack": {
                "research_gaps": ["missing_data_evidence", "missing_high_confidence_fact"],
                "quality_summary": {"high_confidence_items": 0},
            }
        },
    }

    with patch("workflow.skills.review_article_draft.get_model_config") as mock_get_model_config:
        model_config = MagicMock()
        model_config.text.api_key = ""
        model_config.text.base_url = None
        model_config.text.model = "text-model"
        mock_get_model_config.return_value = model_config

        result = await review_article_draft_node(state)

    assert result["writing_state"]["article_review"]["passed"] is False
    assert any(item["type"] == "evidence" for item in result["writing_state"]["review_findings"])
    assert any("证据" in item for item in result["writing_state"]["revision_guidance"])


@pytest.mark.asyncio
async def test_review_article_draft_passes_research_quality_summary_to_model() -> None:
    state = {
        "task_id": "task-4",
        "task_brief": {"topic": "机器人商业化"},
        "writing_state": {
            "draft": {
                "title": "机器人商业化判断",
                "content": "## 先给结论\n内容\n\n## 风险边界\n内容",
            }
        },
        "planning_state": {"article_type": {"type_id": "trend_analysis"}},
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
    }

    with patch("workflow.skills.review_article_draft.get_model_config") as mock_get_model_config:
        with patch("workflow.skills.review_article_draft.ChatPromptTemplate") as mock_prompt_class:
            with patch("workflow.skills.review_article_draft.ChatOpenAI") as mock_chat_openai:
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
                        "passed": False,
                        "score": 70,
                        "findings": [{"type": "evidence", "message": "需要补充数据证据"}],
                        "revision_guidance": ["补充数据证据"],
                    }

                chain.ainvoke.side_effect = fake_ainvoke

                await review_article_draft_node(state)

    assert "research_gaps: missing_data_evidence" in seen_payload["evidence_pack"]
    assert "source_coverage" in seen_payload["evidence_pack"]
