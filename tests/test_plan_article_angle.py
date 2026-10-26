from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from workflow import runtime_settings
from workflow.nodes.plan_article_angle import plan_article_angle_node


@pytest.mark.asyncio
async def test_plan_article_angle_builds_beats_from_evidence_instead_of_topic_template() -> None:
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

    assert funding_sections
    assert expansion_sections
    assert [section["heading"] for section in funding_sections] == [section["heading"] for section in expansion_sections]
    assert [section["shape"] for section in funding_sections] == [section["shape"] for section in expansion_sections]
    assert all(section["shape"] != "risks" for section in funding_sections)


@pytest.mark.asyncio
async def test_plan_article_angle_uses_quantum_skill_fallback_framework() -> None:
    state = {
        "task_brief": {"topic": "量子计算芯片突破"},
        "planning_state": {
            "article_type": {"type_id": "trend_analysis"},
            "selected_skill": {
                "skill_id": "quantum_tech_explainer",
                "name": "量子科技深度解读",
                "framework": "量子科技深度解读",
            },
        },
        "research_state": {"evidence_pack": {"confirmed_facts": [{"claim": "量子芯片保真度提升"}]}},
    }

    with patch("workflow.model_factory.get_model_config") as mock_get_model_config:
        model_config = MagicMock()
        model_config.text.api_key = ""
        mock_get_model_config.return_value = model_config
        result = await plan_article_angle_node(state)
    blueprint = result["planning_state"]["article_blueprint"]
    headings = [section["heading"] for section in blueprint["sections"]]

    assert blueprint["selected_skill"]["skill_id"] == "quantum_tech_explainer"
    assert "量子" in blueprint["framework"]
    assert any("工程指标" in heading or "量子" in heading for heading in headings)
    assert "量子玄学化表达" in blueprint["drop_points"]


@pytest.mark.asyncio
async def test_plan_article_angle_fallback_uses_skill_guidance_for_wechat_blueprint() -> None:
    state = {
        "task_brief": {"topic": "36氪 AI 融资榜单"},
        "planning_state": {
            "article_type": {"type_id": "trend_analysis"},
            "selected_skill": {
                "skill_id": "general_tech_explainer",
                "name": "通用科技解读",
                "framework": "Define why the event matters, then explain drivers, evidence, scenes, and risk boundaries.",
                "section_guidance": [
                    "Clarify the core event or technical change first.",
                    "Use evidence, drivers, and cases to support the judgment.",
                    "Keep a risk-boundary or next-observation section.",
                ],
                "evidence_policy": "Prefer official materials and verifiable industry data.",
                "writing_constraints": ["Every major judgment needs evidence or an explicit evidence boundary."],
            },
        },
        "research_state": {"evidence_pack": {"research_gaps": ["missing_data_evidence"]}},
    }

    with patch("workflow.model_factory.get_model_config") as mock_get_model_config:
        model_config = MagicMock()
        model_config.text.api_key = ""
        mock_get_model_config.return_value = model_config
        result = await plan_article_angle_node(state)
    blueprint = result["planning_state"]["article_blueprint"]
    headings = [section["heading"] for section in blueprint["sections"]]

    assert blueprint["framework"].startswith("Define why the event matters")
    assert any("36氪 AI 融资榜单" in heading for heading in headings)
    assert "Prefer official materials and verifiable industry data." in blueprint["must_cover_points"]
    assert "补齐官方或数据证据" in blueprint["must_cover_points"]


@pytest.mark.asyncio
async def test_plan_article_angle_fallback_uses_neutral_title_candidates() -> None:
    state = {
        "task_brief": {"topic": "36氪 AI 融资榜单"},
        "planning_state": {"article_type": {"type_id": "trend_analysis"}},
        "research_state": {
            "evidence_items": [
                {
                    "angle": "news",
                    "title": "AI 公司融资数量回升",
                    "claim": "榜单显示多家 AI 应用公司获得新融资。",
                    "source_type": "news",
                    "url": "https://example.com/a",
                }
            ],
            "evidence_pack": {"confirmed_facts": [{"claim": "多家 AI 应用公司获得新融资"}]},
        },
    }

    with patch("workflow.model_factory.get_model_config") as mock_get_model_config:
        model_config = MagicMock()
        model_config.text.api_key = ""
        mock_get_model_config.return_value = model_config
        result = await plan_article_angle_node(state)

    titles = result["planning_state"]["article_blueprint"]["title_candidates"]
    joined_titles = " ".join(titles)
    assert titles
    assert "AI 公司融资数量回升" not in joined_titles
    assert "36氪 AI 融资榜单" in joined_titles
    assert "真正值得" not in joined_titles
    assert "热闹" not in joined_titles
    assert "别把" not in joined_titles


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

    with patch("workflow.model_factory.get_model_config") as mock_get_model_config:
        with patch("workflow.nodes.plan_article_angle.ChatPromptTemplate") as mock_prompt_class:
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
    messages = mock_prompt_class.from_messages.call_args.args[0]
    assert "WeChat public account articles" in messages[0][1]
    assert "selected_skill" in messages[1][1]
    assert "source_context" in messages[1][1]
    llm_kwargs = mock_chat_openai.call_args.kwargs
    assert llm_kwargs["model"] == "text-model"
    assert llm_kwargs["api_key"] == "text-key"
    assert llm_kwargs["base_url"] == "https://text.example.com/v1"
    assert llm_kwargs["max_tokens"] == runtime_settings.budget_for_tier("plan_article_angle", "strong")
    assert llm_kwargs["temperature"] == 0.35
    # The factory always applies a bounded timeout and retry budget.
    assert llm_kwargs["timeout"] > 0
    assert llm_kwargs["max_retries"] >= 0


@pytest.mark.asyncio
async def test_plan_article_angle_keeps_model_decided_section_count() -> None:
    state = {
        "task_id": "task-flexible-count",
        "keywords": "AI 榜单变化",
        "task_brief": {"topic": "AI 榜单变化"},
        "planning_state": {"article_type": {"type_id": "trend_analysis"}},
        "research_state": {"evidence_pack": {"confirmed_facts": [{"claim": "榜单显示 AI 应用升温"}]}},
    }
    model_sections = [
        {"heading": f"模型自定章节 {index}", "goal": f"展开第 {index} 个判断", "shape": "custom"}
        for index in range(1, 8)
    ]

    with patch("workflow.model_factory.get_model_config") as mock_get_model_config:
        with patch("workflow.nodes.plan_article_angle.ChatPromptTemplate") as mock_prompt_class:
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
                    "thesis": "结构由模型决定",
                    "reader_value": "帮助读者理解榜单变化",
                    "sections": model_sections,
                    "must_cover_points": [],
                    "drop_points": [],
                }

                result = await plan_article_angle_node(state)

    blueprint = result["planning_state"]["article_blueprint"]
    messages = mock_prompt_class.from_messages.call_args.args[0]
    assert len(blueprint["sections"]) == 7
    assert "whether H2 sections are needed at all" in messages[0][1]
    assert "candidate narrative beats" in messages[0][1]
    assert "Keep 4 to 6" not in messages[0][1]


@pytest.mark.asyncio
async def test_plan_article_angle_does_not_add_boundary_when_evidence_is_sufficient() -> None:
    state = {
        "task_id": "task-no-boundary",
        "keywords": "AI 销售工具",
        "task_brief": {"topic": "AI 销售工具"},
        "planning_state": {"article_type": {"type_id": "trend_analysis"}},
        "research_state": {"evidence_pack": {"confirmed_facts": [{"claim": "企业正在测试 AI 销售工具"}]}},
    }

    with patch("workflow.model_factory.get_model_config") as mock_get_model_config:
        with patch("workflow.nodes.plan_article_angle.ChatPromptTemplate") as mock_prompt_class:
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
                    "thesis": "AI 销售工具正在进入试点阶段",
                    "reader_value": "帮助读者理解采用节奏",
                    "sections": [{"heading": "模型只写一个判断", "goal": "解释试点阶段", "shape": "analysis"}],
                    "must_cover_points": [],
                    "drop_points": [],
                }

                result = await plan_article_angle_node(state)

    headings = [section["heading"] for section in result["planning_state"]["article_blueprint"]["sections"]]
    assert headings == ["模型只写一个判断"]


@pytest.mark.asyncio
async def test_plan_article_angle_adds_boundary_without_forcing_validation_section() -> None:
    state = {
        "task_id": "task-thin-evidence-adaptive-structure",
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

    with patch("workflow.model_factory.get_model_config") as mock_get_model_config:
        with patch("workflow.nodes.plan_article_angle.ChatPromptTemplate") as mock_prompt_class:
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
                    "thesis": "机器人出海仍只有零散信号",
                    "reader_value": "帮助读者识别目前能确认的变化",
                    "sections": [{"heading": "订单之外的一个信号", "goal": "沿单一线索展开", "shape": "essay"}],
                    "must_cover_points": [],
                    "drop_points": [],
                }

                result = await plan_article_angle_node(state)
    blueprint = result["planning_state"]["article_blueprint"]
    headings = [section["heading"] for section in blueprint["sections"]]

    assert headings == ["订单之外的一个信号"]
    assert any(point.startswith("补齐官方或数据证据") for point in blueprint["must_cover_points"])
    assert any("条件化表达" in point for point in blueprint["must_cover_points"])


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

    with patch("workflow.model_factory.get_model_config") as mock_get_model_config:
        with patch("workflow.nodes.plan_article_angle.ChatPromptTemplate") as mock_prompt_class:
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

    with patch("workflow.model_factory.get_model_config") as mock_get_model_config:
        with patch("workflow.nodes.plan_article_angle.ChatPromptTemplate") as mock_prompt_class:
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
    assert "specific to this story" in system_prompt.lower()
    # The prompt must explicitly forbid the fixed placeholder headings.
    assert "先确认发生了什么" in system_prompt


@pytest.mark.asyncio
async def test_plan_article_angle_builds_framework_from_search_materials() -> None:
    state = {
        "task_brief": {"topic": "AI sales workflow"},
        "planning_state": {
            "article_type": {
                "type_id": "trend_analysis",
                "recommended_section_shapes": ["hook", "drivers", "evidence", "case", "risks"],
            }
        },
        "research_state": {
            "evidence_items": [
                {
                    "angle": "fact",
                    "title": "Enterprise buyers slow AI agent rollout",
                    "claim": "Large companies are delaying AI agent rollout because integration costs remain high.",
                    "source_type": "news",
                    "domain": "example.com",
                    "url": "https://example.com/a",
                },
                {
                    "angle": "data",
                    "title": "AI sales tools face longer payback cycles",
                    "claim": "Survey data shows payback cycles for AI sales tools are lengthening.",
                    "source_type": "dataset",
                    "domain": "data.example.com",
                    "url": "https://example.com/b",
                },
            ],
            "evidence_pack": {
                "confirmed_facts": [
                    {"claim": "Large companies are delaying AI agent rollout because integration costs remain high."}
                ],
                "usable_data_points": [
                    {"claim": "Survey data shows payback cycles for AI sales tools are lengthening."}
                ],
                "usable_cases": [],
            },
        },
    }

    result = await plan_article_angle_node(state)
    blueprint = result["planning_state"]["article_blueprint"]
    headings = [section["heading"] for section in blueprint["sections"]]

    assert blueprint["source_driven_framework"]
    assert blueprint["evidence_map"]
    assert headings, "material must produce at least one narrative beat"
    # Headings must never echo a raw source title or URL.
    assert all("Enterprise buyers slow AI agent rollout" not in heading for heading in headings)
    assert all("AI sales tools face longer payback cycles" not in heading for heading in headings)
    assert all("http" not in heading for heading in headings)
    # Headings must be derived from this story's own material rather than a fixed
    # placeholder set (the old implementation always emitted the same four).
    assert any(
        "payback" in heading.lower() or "companies" in heading.lower() or "sales" in heading.lower()
        for heading in headings
    )


@pytest.mark.asyncio
async def test_plan_article_angle_clusters_many_sources_into_a_few_narrative_jobs() -> None:
    evidence_items = [
        {
            "angle": "fact" if index < 5 else "analysis" if index < 9 else "risk",
            "title": f"搜索来源标题 {index}",
            "claim": f"第 {index} 条可核验材料说明了一个不同侧面的变化。",
            "source_type": "official" if index < 5 else "news",
            "url": f"https://example.com/{index}",
        }
        for index in range(12)
    ]
    state = {
        "task_brief": {"topic": "Kimi 新版本"},
        "planning_state": {"article_type": {"type_id": "trend_analysis"}},
        "research_state": {"evidence_items": evidence_items, "evidence_pack": {}},
    }

    result = await plan_article_angle_node(state)
    sections = result["planning_state"]["article_blueprint"]["sections"]

    assert 1 <= len(sections) <= 4
    assert all("搜索来源标题" not in section["heading"] for section in sections)
    assert all("https://" not in section["heading"] for section in sections)


@pytest.mark.asyncio
async def test_plan_article_angle_passes_search_materials_to_model() -> None:
    state = {
        "task_id": "task-search-materials",
        "task_brief": {"topic": "AI sales workflow"},
        "planning_state": {
            "article_type": {
                "type_id": "trend_analysis",
                "recommended_section_shapes": ["hook", "drivers", "evidence", "case", "risks"],
            }
        },
        "research_state": {
            "evidence_items": [
                {
                    "angle": "fact",
                    "title": "Enterprise buyers slow AI agent rollout",
                    "claim": "Large companies delay AI agent rollout because integration costs remain high.",
                    "source_type": "news",
                    "domain": "example.com",
                }
            ],
            "evidence_pack": {"confirmed_facts": [{"claim": "Large companies delay AI agent rollout."}]},
        },
    }

    with patch("workflow.model_factory.get_model_config") as mock_get_model_config:
        with patch("workflow.nodes.plan_article_angle.ChatPromptTemplate") as mock_prompt_class:
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
                    "thesis": "Search content should shape the article.",
                    "reader_value": "Help readers understand the signal.",
                    "sections": [
                        {"heading": "Search signal one", "goal": "Explain source one", "shape": "hook"},
                        {"heading": "Search signal two", "goal": "Explain source two", "shape": "drivers"},
                        {"heading": "Search signal three", "goal": "Explain source three", "shape": "evidence"},
                        {"heading": "Risk boundary", "goal": "Explain uncertainty", "shape": "risks"},
                    ],
                    "must_cover_points": [],
                    "drop_points": [],
                }

                result = await plan_article_angle_node(state)

    payload = chain.ainvoke.await_args.args[0]
    blueprint = result["planning_state"]["article_blueprint"]
    assert "search_materials" in payload
    assert "Enterprise buyers slow AI agent rollout" in payload["search_materials"]
    assert blueprint["source_driven_framework"]
    assert blueprint["evidence_map"]


@pytest.mark.asyncio
async def test_plan_article_angle_passes_extracted_source_context_to_model() -> None:
    extracted_text = (
        "The source explains that enterprise AI sales workflow adoption is blocked by CRM integration, "
        "security review, unclear ownership between sales ops and IT, and longer proof-of-value cycles."
    )
    state = {
        "task_id": "task-source-context",
        "task_brief": {"topic": "AI sales workflow"},
        "planning_state": {
            "article_type": {
                "type_id": "trend_analysis",
                "recommended_section_shapes": ["hook", "drivers", "evidence", "case", "risks"],
            }
        },
        "research_state": {
            "extracted_contents": [
                {
                    "title": "AI sales workflow adoption slows down",
                    "url": "https://example.com/source",
                    "text": extracted_text,
                    "source_meta": {
                        "query": "AI sales workflow adoption",
                        "query_intent": "drivers",
                        "source_type": "news",
                        "domain": "example.com",
                    },
                }
            ],
            "search_results": [
                {
                    "title": "Search result should also be visible",
                    "url": "https://example.com/search",
                    "snippet": "Search snippet for AI sales workflow.",
                    "domain": "example.com",
                }
            ],
            "evidence_pack": {
                "confirmed_facts": [{"claim": "Enterprise adoption is slowed by integration work."}],
                "risk_points": [{"claim": "Vendor claims may overstate deployment speed."}],
            },
        },
    }

    with patch("workflow.model_factory.get_model_config") as mock_get_model_config:
        with patch("workflow.nodes.plan_article_angle.ChatPromptTemplate") as mock_prompt_class:
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
                    "thesis": "Extracted search content should shape the outline.",
                    "reader_value": "Help readers see what the sources actually support.",
                    "sections": [
                        {"heading": "Integration is the first blocker", "goal": "Use extracted source content", "shape": "hook"},
                        {"heading": "Security review changes the sales cycle", "goal": "Use source evidence", "shape": "drivers"},
                        {"heading": "Proof-of-value cycles are getting longer", "goal": "Use source evidence", "shape": "evidence"},
                        {"heading": "The risk is vendor overclaiming", "goal": "Explain boundary", "shape": "risks"},
                    ],
                    "must_cover_points": [],
                    "drop_points": [],
                }

                await plan_article_angle_node(state)

    payload = chain.ainvoke.await_args.args[0]
    assert "source_context" in payload
    assert extracted_text in payload["source_context"]
    assert "https://example.com/source" in payload["source_context"]
    assert "Enterprise adoption is slowed by integration work." in payload["source_context"]
