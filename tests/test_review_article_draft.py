from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from workflow.agents.reviewer import review_article_draft_node


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

    with patch("workflow.model_factory.get_model_config") as mock_get_model_config:
        with patch("workflow.agents.reviewer.ChatPromptTemplate") as mock_prompt_class:
            with patch("workflow.model_factory.ChatOpenAI") as mock_chat_openai:
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
    llm_kwargs = mock_chat_openai.call_args.kwargs
    assert llm_kwargs["model"] == "text-model"
    assert llm_kwargs["api_key"] == "text-key"
    assert llm_kwargs["base_url"] == "https://text.example.com/v1"
    # Review output is a small structured payload, so the token cap is tightened.
    assert llm_kwargs["max_tokens"] == 600
    assert llm_kwargs["temperature"] == 0.2
    assert llm_kwargs["timeout"] > 0
    assert llm_kwargs["max_retries"] >= 0


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

    with patch("workflow.model_factory.get_model_config") as mock_get_model_config:
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

    with patch("workflow.model_factory.get_model_config") as mock_get_model_config:
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

    with patch("workflow.model_factory.get_model_config") as mock_get_model_config:
        with patch("workflow.agents.reviewer.ChatPromptTemplate") as mock_prompt_class:
            with patch("workflow.model_factory.ChatOpenAI") as mock_chat_openai:
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


@pytest.mark.asyncio
async def test_review_article_draft_fallback_flags_generic_opener() -> None:
    state = {
        "task_id": "task-5",
        "writing_state": {
            "draft": {
                "title": "机器人商业化判断",
                "content": "本文将从市场、产品和商业化三个方面展开分析。\n\n## 为什么订单开始变慢\n内容\n\n## 风险边界在哪里\n内容",
            }
        },
    }

    with patch("workflow.model_factory.get_model_config") as mock_get_model_config:
        model_config = MagicMock()
        model_config.text.api_key = ""
        model_config.text.base_url = None
        model_config.text.model = "text-model"
        mock_get_model_config.return_value = model_config

        result = await review_article_draft_node(state)

    assert result["writing_state"]["article_review"]["passed"] is False
    assert any(item["type"] == "opener" for item in result["writing_state"]["review_findings"])
    assert any("开头" in item for item in result["writing_state"]["revision_guidance"])


@pytest.mark.asyncio
async def test_review_article_draft_fallback_flags_thin_sections_without_transition_density() -> None:
    state = {
        "task_id": "task-6",
        "writing_state": {
            "draft": {
                "title": "机器人商业化判断",
                "content": "一个开头。\n\n## 为什么订单开始变慢\n一句话。\n\n## 风险边界在哪里\n一句话。",
            }
        },
    }

    with patch("workflow.model_factory.get_model_config") as mock_get_model_config:
        model_config = MagicMock()
        model_config.text.api_key = ""
        model_config.text.base_url = None
        model_config.text.model = "text-model"
        mock_get_model_config.return_value = model_config

        result = await review_article_draft_node(state)

    assert result["writing_state"]["article_review"]["passed"] is False
    assert any(item["type"] == "density" for item in result["writing_state"]["review_findings"])
    assert any("段落" in item for item in result["writing_state"]["revision_guidance"])


@pytest.mark.asyncio
async def test_review_article_draft_accepts_inline_boundary_without_risk_section() -> None:
    state = {
        "task_id": "task-inline-boundary",
        "writing_state": {
            "draft": {
                "title": "机器人商业化正在换一种验证方式",
                "content": (
                    "订单周期变长不必然意味着需求消失，它也可能说明客户开始用更严格的经营指标评估产品。\n\n"
                    "目前能确认的是，多家公司正在调整销售与交付协作；但这一判断仍需更多回款数据验证，不能直接推导出行业已经规模化。\n\n"
                    "接下来真正值得观察的是，承诺、交付和现金流能否形成稳定闭环。"
                ),
            }
        },
        "research_state": {"evidence_pack": {"risk_points": [{"claim": "回款数据尚不充分"}]}},
    }

    with patch("workflow.model_factory.get_model_config") as mock_get_model_config:
        model_config = MagicMock()
        model_config.text.api_key = ""
        model_config.text.base_url = None
        model_config.text.model = "text-model"
        mock_get_model_config.return_value = model_config
        result = await review_article_draft_node(state)

    assert result["writing_state"]["article_review"]["passed"] is True
    assert not any(item["type"] == "evidence_boundary" for item in result["writing_state"]["review_findings"])


@pytest.mark.asyncio
async def test_review_article_draft_rejects_planning_notes_and_source_headings() -> None:
    state = {
        "writing_state": {
            "draft": {
                "title": "Kimi 新版本观察",
                "content": (
                    "一个完整开头，说明变化与读者的关系。\n\n"
                    "## https://example.com/news Kimi release notes\n"
                    "这一节要解决的问题是：解释产品变化。\n\n"
                    "把这条线索放进正文时，需要继续补充事实。"
                ),
            }
        }
    }
    with patch("workflow.model_factory.get_model_config") as mock_get_model_config:
        model_config = MagicMock()
        model_config.text.api_key = ""
        mock_get_model_config.return_value = model_config
        result = await review_article_draft_node(state)

    finding_types = {item["type"] for item in result["writing_state"]["review_findings"]}
    assert "planning_language" in finding_types
    assert "source_heading" in finding_types
    assert result["writing_state"]["article_review"]["passed"] is False
