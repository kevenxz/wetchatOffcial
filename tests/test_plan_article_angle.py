from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from workflow.skills.plan_article_angle import plan_article_angle_node


@pytest.mark.asyncio
async def test_plan_article_angle_builds_different_section_shapes_for_different_topics() -> None:
    base_state = {
        "planning_state": {
            "article_type": {
                "type_id": "trend_analysis",
                "recommended_section_shapes": ["hook", "drivers", "evidence", "case", "risks", "next_steps"],
            }
        },
        "research_state": {
            "evidence_pack": {
                "confirmed_facts": [{"claim": "融资热度上升"}],
                "usable_data_points": [{"claim": "融资笔数同比提升"}],
                "usable_cases": [{"claim": "头部公司连续获投"}],
            }
        },
    }

    funding_result = await plan_article_angle_node(
        {
            **base_state,
            "task_brief": {"topic": "机器人融资潮"},
        }
    )
    expansion_result = await plan_article_angle_node(
        {
            **base_state,
            "task_brief": {"topic": "AI agent 出海"},
        }
    )

    funding_sections = funding_result["planning_state"]["article_blueprint"]["sections"]
    expansion_sections = expansion_result["planning_state"]["article_blueprint"]["sections"]

    assert 4 <= len(funding_sections) <= 6
    assert 4 <= len(expansion_sections) <= 6
    assert funding_sections != expansion_sections
    assert any("风险" in section["heading"] for section in funding_sections)
    assert any("风险" in section["heading"] for section in expansion_sections)


@pytest.mark.asyncio
async def test_plan_article_angle_avoids_fixed_wechat_headings_for_general_topics() -> None:
    state = {
        "planning_state": {
            "article_type": {
                "type_id": "trend_analysis",
                "recommended_section_shapes": ["hook", "drivers", "evidence", "case", "risks", "next_steps"],
            }
        },
        "task_brief": {"topic": "机器人创业公司为什么开始重做销售体系"},
        "research_state": {
            "evidence_pack": {
                "confirmed_facts": [{"claim": "多家公司开始补销售团队"}],
                "usable_data_points": [{"claim": "订单周期拉长"}],
                "usable_cases": [{"claim": "头部公司调整渠道模式"}],
            }
        },
    }

    result = await plan_article_angle_node(state)
    headings = [section["heading"] for section in result["planning_state"]["article_blueprint"]["sections"]]

    assert "先给结论" not in headings
    assert "发生变化的核心原因" not in headings
    assert "哪些证据最值得看" not in headings


@pytest.mark.asyncio
async def test_plan_article_angle_uses_model_to_generate_structured_blueprint() -> None:
    state = {
        "task_id": "task-1",
        "keywords": "机器人融资潮",
        "task_brief": {"topic": "机器人融资潮"},
        "planning_state": {
            "article_type": {
                "type_id": "trend_analysis",
                "recommended_section_shapes": ["hook", "drivers", "evidence", "case", "risks", "next_steps"],
            }
        },
        "research_state": {
            "evidence_pack": {
                "confirmed_facts": [{"claim": "头部公司融资升温"}],
                "usable_data_points": [{"claim": "融资笔数上升"}],
                "usable_cases": [{"claim": "具身智能公司连续获投"}],
            }
        },
    }

    with patch("workflow.skills.plan_article_angle.get_model_config") as mock_get_model_config:
        with patch("workflow.skills.plan_article_angle.ChatPromptTemplate") as mock_prompt_class:
            with patch("workflow.skills.plan_article_angle.ChatOpenAI") as mock_chat_openai:
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
                    "thesis": "机器人融资潮正在从热闹走向分化",
                    "reader_value": "帮助读者判断这一轮融资热度的含金量",
                    "sections": [
                        {"heading": "这一轮融资潮先看什么", "goal": "先给结论", "shape": "hook"},
                        {"heading": "资金为什么重新流入", "goal": "解释驱动因素", "shape": "drivers"},
                        {"heading": "哪些公司真的吃到红利", "goal": "展开案例", "shape": "case"},
                        {"heading": "风险边界在哪里", "goal": "约束结论", "shape": "risks"},
                    ],
                    "must_cover_points": ["融资节奏", "估值分化"],
                    "drop_points": ["泛泛产业背景"],
                }

                result = await plan_article_angle_node(state)

    blueprint = result["planning_state"]["article_blueprint"]

    assert blueprint["thesis"] == "机器人融资潮正在从热闹走向分化"
    assert blueprint["reader_value"] == "帮助读者判断这一轮融资热度的含金量"
    assert blueprint["sections"][0]["heading"] == "这一轮融资潮先看什么"
    assert blueprint["must_cover_points"] == ["融资节奏", "估值分化"]
    mock_chat_openai.assert_called_once_with(
        model="text-model",
        api_key="text-key",
        base_url="https://text.example.com/v1",
        max_tokens=1800,
        temperature=0.35,
    )


@pytest.mark.asyncio
async def test_plan_article_angle_adds_validation_sections_when_evidence_is_thin() -> None:
    state = {
        "planning_state": {
            "article_type": {
                "type_id": "trend_analysis",
                "recommended_section_shapes": ["hook", "drivers", "evidence", "case", "risks", "next_steps"],
            }
        },
        "task_brief": {"topic": "机器人出海"},
        "research_state": {
            "evidence_pack": {
                "confirmed_facts": [],
                "usable_data_points": [],
                "usable_cases": [],
                "research_gaps": ["missing_data_evidence", "missing_high_confidence_fact"],
                "quality_summary": {
                    "high_confidence_items": 0,
                    "source_coverage": {"community": 2},
                    "angle_coverage": {"opinion": 2},
                },
            }
        },
    }

    result = await plan_article_angle_node(state)
    blueprint = result["planning_state"]["article_blueprint"]
    headings = [section["heading"] for section in blueprint["sections"]]

    assert any("验证" in heading for heading in headings)
    assert "补齐官方或数据证据" in blueprint["must_cover_points"]


@pytest.mark.asyncio
async def test_plan_article_angle_passes_research_quality_summary_to_model() -> None:
    state = {
        "task_id": "task-4",
        "task_brief": {"topic": "机器人商业化"},
        "planning_state": {
            "article_type": {
                "type_id": "trend_analysis",
                "recommended_section_shapes": ["hook", "drivers", "evidence", "case", "risks", "next_steps"],
            }
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
    }

    with patch("workflow.skills.plan_article_angle.get_model_config") as mock_get_model_config:
        with patch("workflow.skills.plan_article_angle.ChatPromptTemplate") as mock_prompt_class:
            with patch("workflow.skills.plan_article_angle.ChatOpenAI") as mock_chat_openai:
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
                    "thesis": "机器人商业化正在进入验证期",
                    "reader_value": "帮助读者判断哪些结论已经被证据支撑",
                    "sections": [
                        {"heading": "先给结论", "goal": "定义判断范围", "shape": "hook"},
                        {"heading": "驱动因素", "goal": "解释核心变化", "shape": "drivers"},
                        {"heading": "案例信号", "goal": "展开案例", "shape": "case"},
                        {"heading": "风险边界", "goal": "约束结论", "shape": "risks"},
                    ],
                    "must_cover_points": ["证据边界"],
                    "drop_points": [],
                }

                await plan_article_angle_node(state)

    payload = chain.ainvoke.await_args.args[0]
    assert "research_gaps: missing_data_evidence" in payload["evidence_pack"]
    assert "source_coverage" in payload["evidence_pack"]


@pytest.mark.asyncio
async def test_plan_article_angle_model_prompt_requests_wechat_style_structure() -> None:
    state = {
        "task_id": "task-5",
        "task_brief": {"topic": "机器人公司为什么开始重做销售体系"},
        "planning_state": {
            "article_type": {
                "type_id": "trend_analysis",
                "recommended_section_shapes": ["hook", "drivers", "evidence", "case", "risks", "next_steps"],
            }
        },
        "research_state": {
            "evidence_pack": {
                "confirmed_facts": [{"claim": "公司开始扩销售"}],
                "usable_data_points": [{"claim": "回款周期拉长"}],
            }
        },
    }

    with patch("workflow.skills.plan_article_angle.get_model_config") as mock_get_model_config:
        with patch("workflow.skills.plan_article_angle.ChatPromptTemplate") as mock_prompt_class:
            with patch("workflow.skills.plan_article_angle.ChatOpenAI") as mock_chat_openai:
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
                    "thesis": "销售体系重做背后是商业化压力上升",
                    "reader_value": "帮助读者判断组织调整的真实信号",
                    "sections": [
                        {"heading": "销售体系为什么突然变成头号问题", "goal": "定义问题", "shape": "hook"},
                        {"heading": "订单和回款哪里开始吃紧", "goal": "解释压力来源", "shape": "drivers"},
                        {"heading": "不同公司在怎么补这一课", "goal": "展开案例", "shape": "case"},
                        {"heading": "风险边界在哪里", "goal": "约束结论", "shape": "risks"},
                    ],
                    "must_cover_points": [],
                    "drop_points": [],
                }

                await plan_article_angle_node(state)

    messages = mock_prompt_class.from_messages.call_args.args[0]
    system_prompt = messages[0][1]
    assert "wechat" in system_prompt.lower()
    assert "section headings should be content-specific" in system_prompt.lower()
