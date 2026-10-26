from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from workflow import runtime_settings
from workflow.agents.writer import compose_draft_node


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

    with patch("workflow.model_factory.get_model_config") as mock_get_model_config:
        model_config = MagicMock()
        model_config.text.api_key = ""
        mock_get_model_config.return_value = model_config

        result = await compose_draft_node(state)

    assert result["writing_state"]["draft"]["title"]
    assert "趋势判断" in result["writing_state"]["draft"]["content"]


@pytest.mark.asyncio
async def test_compose_draft_passes_selected_skill_to_model_prompt() -> None:
    state = {
        "task_id": "task-quantum-writer",
        "task_brief": {"topic": "量子计算芯片突破"},
        "planning_state": {
            "selected_skill": {
                "skill_id": "quantum_tech_explainer",
                "name": "量子科技深度解读",
                "writing_constraints": ["必须区分科学原理、工程样机和商业化产品"],
            },
            "article_type": {"type_id": "trend_analysis"},
            "article_blueprint": {
                "thesis": "量子计算芯片突破需要看工程指标",
                "sections": [
                    {"heading": "工程指标为什么重要", "goal": "解释量子技术验证边界"},
                    {"heading": "风险边界在哪里", "goal": "说明不确定性"},
                ],
            },
        },
        "research_state": {"evidence_pack": {"confirmed_facts": [{"claim": "保真度指标提升"}]}},
    }

    with patch("workflow.model_factory.get_model_config") as mock_get_model_config:
        with patch("workflow.agents.writer.ChatPromptTemplate") as mock_prompt_class:
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
                    "title": "量子计算芯片突破，先看工程指标",
                    "alt_titles": [],
                    "content": "开头\n\n## 工程指标为什么重要\n\n正文足够长。" * 80,
                    "summary": "解释量子技术边界",
                }

                await compose_draft_node(state)

    payload = chain.ainvoke.await_args.args[0]
    assert payload["selected_skill"]["skill_id"] == "quantum_tech_explainer"
    messages = mock_prompt_class.from_messages.call_args.args[0]
    assert "selected_skill" in messages[1][1]


@pytest.mark.asyncio
async def test_compose_draft_fallback_writes_complete_wechat_article_from_outline() -> None:
    state = {
        "task_brief": {"topic": "AI 搜索产品"},
        "planning_state": {
            "article_type": {"type_id": "trend_analysis"},
            "article_blueprint": {
                "thesis": "AI 搜索产品进入体验竞争阶段",
                "sections": [
                    {"heading": "为什么 AI 搜索重新变热", "goal": "解释用户需求和产品变化"},
                    {"heading": "哪些证据能说明变化", "goal": "结合数据和案例说明趋势"},
                    {"heading": "风险和证据边界在哪里", "goal": "说明不确定性"},
                ],
            },
            "outline_result": {
                "title_candidates": ["AI 搜索产品，真正的竞争才刚开始"],
                "reader_value": "帮助读者判断 AI 搜索产品的真实变化。",
                "outline": [
                    {
                        "section": "为什么 AI 搜索重新变热",
                        "goal": "解释用户需求和产品变化",
                        "shape": "drivers",
                        "key_points": ["用户开始把搜索当成任务入口。"],
                    },
                    {
                        "section": "哪些证据能说明变化",
                        "goal": "结合数据和案例说明趋势",
                        "shape": "evidence",
                        "key_points": ["多家公司开始把 AI 搜索放到核心入口。"],
                    },
                    {
                        "section": "风险和证据边界在哪里",
                        "goal": "说明不确定性",
                        "shape": "risks",
                        "key_points": ["留存和商业化仍需要验证。"],
                    },
                ],
            },
        },
        "research_state": {
            "evidence_pack": {
                "confirmed_facts": [{"claim": "多家公司开始上线 AI 搜索入口。"}],
                "usable_data_points": ["用户搜索行为开始向对话式入口迁移。"],
            }
        },
    }

    with patch("workflow.model_factory.get_model_config") as mock_get_model_config:
        model_config = MagicMock()
        model_config.text.api_key = ""
        mock_get_model_config.return_value = model_config

        result = await compose_draft_node(state)

    content = result["generated_article"]["content"]
    assert result["generated_article"]["title"] == "AI 搜索产品，真正的竞争才刚开始"
    assert len(content) > 600
    assert "## 为什么 AI 搜索重新变热" in content
    assert "## 哪些证据能说明变化" in content
    assert "## 风险和证据边界在哪里" in content
    assert "微信公众号语境" not in content
    assert "这一节要解决的问题" not in content
    assert "把这条线索放进正文" not in content


@pytest.mark.asyncio
async def test_compose_draft_repairs_thin_model_output_before_using_fallback() -> None:
    state = {
        "task_id": "task-thin",
        "task_brief": {"topic": "AI 搜索产品"},
        "planning_state": {
            "article_type": {"type_id": "trend_analysis"},
            "article_blueprint": {
                "thesis": "AI 搜索产品进入体验竞争阶段",
                "sections": [
                    {"heading": "为什么重新变热", "goal": "解释变化"},
                    {"heading": "风险在哪里", "goal": "说明边界"},
                ],
            },
            "outline_result": {
                "outline": [
                    {"section": "为什么重新变热", "goal": "解释变化", "key_points": ["入口变化"]},
                    {"section": "风险在哪里", "goal": "说明边界", "key_points": ["商业化未验证"]},
                ]
            },
        },
        "research_state": {"evidence_pack": {"confirmed_facts": [{"claim": "AI 搜索入口增加。"}]}},
        "writing_state": {},
    }

    with patch("workflow.model_factory.get_model_config") as mock_get_model_config:
        with patch("workflow.agents.writer.ChatPromptTemplate") as mock_prompt_class:
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
                chain.ainvoke.side_effect = [
                    {
                        "title": "AI 搜索产品大纲",
                        "content": "## 为什么重新变热\n解释变化\n\n## 风险在哪里\n说明边界",
                        "summary": "大纲",
                    },
                    {
                        "title": "AI 搜索正在从答案竞争转向任务竞争",
                        "content": (
                            "用户不再只想得到一条链接，而是希望搜索入口继续完成比较、归纳和执行。" * 18
                            + "\n\n## 入口变化背后是任务边界扩大\n"
                            + "越来越多产品把连续对话和工具调用放进搜索流程，这改变了用户对结果完整性的预期。" * 18
                            + "\n\n## 真正的门槛仍在留存和成本\n"
                            + "入口增加不等于商业模式已经成立，留存、推理成本和付费意愿仍需长期数据验证。" * 18
                            + "\n\n"
                            + "最终决定产品位置的，不是一次发布带来的声量，而是用户是否愿意把完整任务留在这里。" * 12
                        ),
                        "summary": "AI 搜索的竞争重心正从返回答案转向完成任务。",
                    },
                ]

                result = await compose_draft_node(state)

    assert len(result["generated_article"]["content"]) > 600
    assert result["generated_article"]["title"] == "AI 搜索正在从答案竞争转向任务竞争"
    assert result["writing_state"]["draft_generation_mode"] == "model_repair"
    assert chain.ainvoke.await_count == 2


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

    with patch("workflow.model_factory.get_model_config") as mock_get_model_config:
        with patch("workflow.agents.writer.ChatPromptTemplate") as mock_prompt_class:
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
                    "title": "机器人融资潮进入第二阶段",
                    "alt_titles": ["资本又开始押注机器人，但逻辑已经变了", "机器人融资回暖后，真正该看的不是热度"],
                    "content": "## 趋势判断\n" + ("融资从个案走向密集出现，这一变化需要结合资金流向和交付节奏理解。" * 10) + "\n\n" + ("资金偏好正在分化，单一事件还不足以定义整个周期。" * 10) + "\n\n## 尚未收束的判断\n" + ("估值和量产仍有不确定性，后续证据可能改变当前结论。" * 10) + "\n\n" + ("更稳妥的做法是继续观察订单、交付和现金流。" * 10),
                    "summary": "融资热度提升，但兑现仍需观察。",
                }

                result = await compose_draft_node(state)

    assert result["writing_state"]["draft"]["title"] == "机器人融资潮进入第二阶段"
    assert result["writing_state"]["draft"]["alt_titles"] == [
        "资本又开始押注机器人，但逻辑已经变了",
        "机器人融资回暖后，真正该看的不是热度",
    ]
    assert "## 趋势判断" in result["generated_article"]["content"]
    assert result["writing_state"]["draft"]["summary"] == "融资热度提升，但兑现仍需观察。"
    assert result["generated_article"]["alt_titles"] == [
        "资本又开始押注机器人，但逻辑已经变了",
        "机器人融资回暖后，真正该看的不是热度",
    ]
    llm_kwargs = mock_chat_openai.call_args.kwargs
    assert llm_kwargs["model"] == "text-model"
    assert llm_kwargs["api_key"] == "text-key"
    assert llm_kwargs["base_url"] == "https://text.example.com/v1"
    # Budget is tier-aware: widened when the stage lands on a reasoning model, whose
    # hidden reasoning would otherwise consume the whole completion budget and return
    # no parseable JSON.
    assert llm_kwargs["max_tokens"] == runtime_settings.budget_for_tier("compose_draft", "strong")
    assert llm_kwargs["temperature"] == 0.45
    # The factory always applies a bounded timeout and retry budget.
    assert llm_kwargs["timeout"] > 0
    assert llm_kwargs["max_retries"] >= 0


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

    with patch("workflow.model_factory.get_model_config") as mock_get_model_config:
        with patch("workflow.agents.writer.ChatPromptTemplate") as mock_prompt_class:
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
                        "title": "修订后的机器人融资潮判断",
                        "content": "## 趋势判断\n" + ("补充数据后可以看出融资节奏正在变化，但仍需区分个案与趋势。" * 10) + "\n\n" + ("不同公司的资金用途并不相同，不能直接合并为同一种信号。" * 10) + "\n\n## 尚未收束的判断\n" + ("现有证据只能支撑有限判断，因此结论表述已按来源强度收紧。" * 10) + "\n\n" + ("后续仍需用订单和交付数据检查当前判断。" * 10),
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

    with patch("workflow.model_factory.get_model_config") as mock_get_model_config:
        with patch("workflow.agents.writer.ChatPromptTemplate") as mock_prompt_class:
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

    with patch("workflow.model_factory.get_model_config") as mock_get_model_config:
        with patch("workflow.agents.writer.ChatPromptTemplate") as mock_prompt_class:
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


@pytest.mark.asyncio
async def test_compose_draft_model_prompt_requests_wechat_ready_title_summary_and_hook() -> None:
    state = {
        "task_id": "task-5",
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

    with patch("workflow.model_factory.get_model_config") as mock_get_model_config:
        with patch("workflow.agents.writer.ChatPromptTemplate") as mock_prompt_class:
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
                    "title": "机器人公司开始重做销售，不只是组织调整",
                    "content": "开头段\n\n## 销售为什么突然成了头号问题\n内容\n\n## 风险边界在哪里\n内容",
                    "summary": "摘要",
                }

                await compose_draft_node(state)

    messages = mock_prompt_class.from_messages.call_args.args[0]
    system_prompt = messages[0][1].lower()
    assert "title" in system_prompt
    assert "summary" in system_prompt
    assert "opening hook" in system_prompt


@pytest.mark.asyncio
async def test_compose_draft_model_prompt_requests_alt_titles_and_non_generic_hook() -> None:
    state = {
        "task_id": "task-6",
        "task_brief": {"topic": "机器人公司为什么开始重做销售体系"},
        "planning_state": {
            "article_type": {"type_id": "trend_analysis", "title_style": "insight_first"},
            "article_blueprint": {
                "thesis": "销售体系重做背后是商业化压力上升",
                "sections": [
                    {"heading": "为什么销售 suddenly became the real bottleneck", "goal": "定义问题"},
                    {"heading": "风险边界在哪里", "goal": "约束结论"},
                ],
            },
        },
        "research_state": {"evidence_pack": {"confirmed_facts": [{"claim": "公司开始扩销售"}]}},
        "writing_state": {},
    }

    with patch("workflow.model_factory.get_model_config") as mock_get_model_config:
        with patch("workflow.agents.writer.ChatPromptTemplate") as mock_prompt_class:
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
                    "title": "机器人公司开始重做销售，不只是组织问题",
                    "alt_titles": ["机器人公司重做销售，真正暴露的是商业化压力", "销售体系重做背后，机器人公司开始面对同一堵墙"],
                    "content": "一个开头。\n\n## 为什么销售 suddenly became the real bottleneck\n内容\n\n## 风险边界在哪里\n内容",
                    "summary": "摘要",
                }

                await compose_draft_node(state)

    system_prompt = mock_prompt_class.from_messages.call_args.args[0][0][1].lower()
    assert "alternative title" in system_prompt
    assert "avoid generic opener" in system_prompt


@pytest.mark.asyncio
async def test_compose_draft_model_prompt_requests_section_transitions_and_paragraph_density() -> None:
    state = {
        "task_id": "task-7",
        "task_brief": {"topic": "机器人公司为什么开始重做销售体系"},
        "planning_state": {
            "article_type": {"type_id": "trend_analysis", "title_style": "insight_first"},
            "article_blueprint": {
                "thesis": "销售体系重做背后是商业化压力上升",
                "sections": [
                    {"heading": "为什么销售 suddenly became the real bottleneck", "goal": "定义问题"},
                    {"heading": "风险边界在哪里", "goal": "约束结论"},
                ],
            },
        },
        "research_state": {"evidence_pack": {"confirmed_facts": [{"claim": "公司开始扩销售"}]}},
        "writing_state": {},
    }

    with patch("workflow.model_factory.get_model_config") as mock_get_model_config:
        with patch("workflow.agents.writer.ChatPromptTemplate") as mock_prompt_class:
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
                    "title": "机器人公司开始重做销售，不只是组织问题",
                    "alt_titles": ["机器人公司重做销售，真正暴露的是商业化压力", "销售体系重做背后，机器人公司开始面对同一堵墙"],
                    "content": "一个开头。\n\n## 为什么销售 suddenly became the real bottleneck\n内容\n\n## 风险边界在哪里\n内容",
                    "summary": "摘要",
                }

                await compose_draft_node(state)

    system_prompt = mock_prompt_class.from_messages.call_args.args[0][0][1].lower()
    assert "transition" in system_prompt
    assert "as many or as few sections" in system_prompt
    assert "avoid single-sentence fragments" in system_prompt


@pytest.mark.asyncio
async def test_compose_draft_preserves_a_developed_essay_without_h2() -> None:
    state = {
        "task_id": "task-adaptive-essay",
        "task_brief": {"topic": "机器人公司重做销售体系"},
        "planning_state": {
            "article_type": {"type_id": "trend_analysis"},
            "article_blueprint": {
                "thesis": "销售体系变化反映商业化压力",
                "sections": [
                    {"heading": "原计划章节一", "goal": "解释变化"},
                    {"heading": "原计划章节二", "goal": "说明边界"},
                ],
            },
        },
        "research_state": {"evidence_pack": {"confirmed_facts": [{"claim": "多家公司扩充销售团队"}]}},
        "writing_state": {},
    }
    paragraphs = [
        "表面看，这只是一次组织调整；但把招聘、订单周期和客户决策放在一起，销售体系的变化更像商业化阶段切换的结果。" * 6,
        "第一条线索来自团队配置。过去依靠创始人和产品负责人推动的试点项目，开始需要更稳定的行业销售与交付协作。" * 6,
        "第二条线索来自客户一侧。企业采购不只问模型效果，还会追问部署成本、责任边界和后续维护，这让成交链条明显变长。" * 6,
        "不过，现有公开信息仍需更多订单和回款数据验证，因此这里能确认的是经营动作发生了变化，还不能断言整个行业已经跨过规模化门槛。" * 6,
        "真正值得继续观察的，不是哪家公司又发布了新产品，而是谁能把销售承诺、交付能力和现金流放进同一套可重复的经营系统。" * 6,
    ]

    with patch("workflow.model_factory.get_model_config") as mock_get_model_config:
        with patch("workflow.agents.writer.ChatPromptTemplate") as mock_prompt_class:
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
                    "title": "机器人公司重做销售，暴露的不是组织问题",
                    "content": "\n\n".join(paragraphs),
                    "summary": "从经营动作理解商业化阶段变化。",
                }

                result = await compose_draft_node(state)

    draft = result["writing_state"]["draft"]
    assert draft["title"] == "机器人公司重做销售，暴露的不是组织问题"
    assert "## " not in draft["content"]
    assert "原计划章节" not in draft["content"]
