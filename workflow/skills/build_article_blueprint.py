"""Build a structured article blueprint before web search."""
from __future__ import annotations

import time

import structlog
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from api.store import get_model_config
from workflow.article_generation import build_article_plan, normalize_generation_config, resolve_strategy_label
from workflow.model_logging import build_model_context, log_model_request, log_model_response
from workflow.state import WorkflowState

logger = structlog.get_logger(__name__)


FINANCE_TOPIC_MARKERS = (
    "oil",
    "crude",
    "brent",
    "wti",
    "gold",
    "copper",
    "commodity",
    "macro",
    "fx",
    "forex",
    "bond",
    "equity",
    "stock",
    "etf",
    "earnings",
    "market",
    "原油",
    "油价",
    "能源",
    "黄金",
    "铜",
    "大宗商品",
    "宏观",
    "汇率",
    "利率",
    "债券",
    "股市",
    "股票",
    "财报",
    "金融",
    "财经",
    "投资",
    "供需",
    "库存",
)


class BlueprintSection(BaseModel):
    heading: str = Field(description="Markdown h2 heading, must start with ## ")
    goal: str
    evidence_needed: list[str] = Field(default_factory=list)


class VisualizationPlanItem(BaseModel):
    title: str = Field(description="Chart title shown to the reader")
    chart_type: str = Field(description="Chart type, such as line, bar, area, comparison or mixed")
    insight_goal: str = Field(description="What the chart should help explain")
    data_source_hint: str = Field(description="Preferred data source or institution")
    placement_heading: str = Field(description="The H2 section where the chart should appear")


class ArticleBlueprintOutput(BaseModel):
    article_type: str
    structure_style: str
    title_strategy: str
    opening_goal: str
    reader_takeaway: str
    search_focuses: list[str]
    search_query_hints: list[str]
    ending_style: str
    markdown_requirements: list[str] = Field(default_factory=list)
    requires_data_visualization: bool = False
    visualization_plan: list[VisualizationPlanItem] = Field(default_factory=list)
    planned_illustrations: int = Field(default=3, ge=2, le=5)
    section_outline: list[BlueprintSection]


def _is_finance_or_market_article(state: WorkflowState) -> bool:
    user_intent = state.get("user_intent", {})
    topic = str(user_intent.get("topic") or state.get("keywords") or "").lower()
    return any(marker in topic for marker in FINANCE_TOPIC_MARKERS)


def _default_markdown_requirements(requires_data_visualization: bool) -> list[str]:
    requirements = [
        "Output the article in Markdown.",
        "Use H2 headings that start with ## for major sections.",
        "Use Markdown lists and tables where they improve readability.",
        "Do not output raw HTML in the article body.",
    ]
    if requires_data_visualization:
        requirements.extend(
            [
                "For each chart block, use `### 图表N：标题` followed by `[插图N]`.",
                "Under every chart block, include `- 数据来源：...` and `- 图表说明：...`.",
                "Finance and market articles should combine analysis with 3-5 chart blocks.",
            ]
        )
    return requirements


def _default_visualization_plan(topic: str) -> list[dict[str, str]]:
    normalized_topic = (topic or "主题").strip() or "主题"
    lowered = normalized_topic.lower()

    if any(marker in lowered for marker in ("oil", "crude", "brent", "wti", "原油", "油价")):
        return [
            {
                "title": "近5年国际原油价格走势图",
                "chart_type": "line",
                "insight_goal": "展示油价长期趋势、波动区间和最近的关键拐点。",
                "data_source_hint": "EIA, FRED, ICE, CME, World Bank commodity data",
                "placement_heading": "## 市场概况",
            },
            {
                "title": "主要产油国产量对比图",
                "chart_type": "bar",
                "insight_goal": "比较主要生产国供给格局和边际变化。",
                "data_source_hint": "OPEC monthly oil market report, IEA, EIA",
                "placement_heading": "## 价格驱动因素",
            },
            {
                "title": "全球原油库存变化趋势图",
                "chart_type": "area",
                "insight_goal": "观察库存去化或累库对价格的传导。",
                "data_source_hint": "EIA, IEA, OECD inventory data",
                "placement_heading": "## 数据图表观察",
            },
            {
                "title": "原油需求预测与实际需求对比图",
                "chart_type": "mixed",
                "insight_goal": "衡量需求预期偏差与市场修正风险。",
                "data_source_hint": "IEA, OPEC, IMF, World Bank",
                "placement_heading": "## 未来展望",
            },
        ]

    return [
        {
            "title": f"{normalized_topic}核心价格或估值趋势图",
            "chart_type": "line",
            "insight_goal": "帮助读者建立价格、估值或景气度的长期趋势感。",
            "data_source_hint": "Official statistics, exchange data, FRED, World Bank",
            "placement_heading": "## 市场概况",
        },
        {
            "title": f"{normalized_topic}关键供给与需求对比图",
            "chart_type": "bar",
            "insight_goal": "说明供需错配、市场份额或结构变化。",
            "data_source_hint": "Official reports, industry associations, company disclosures",
            "placement_heading": "## 关键驱动因素",
        },
        {
            "title": f"{normalized_topic}库存、现金流或景气指标趋势图",
            "chart_type": "area",
            "insight_goal": "展示中观指标变化与市场节奏。",
            "data_source_hint": "Official datasets, industry databases, company filings",
            "placement_heading": "## 数据图表观察",
        },
        {
            "title": f"{normalized_topic}预测值与实际值偏差图",
            "chart_type": "mixed",
            "insight_goal": "展示未来预期、现实落差和潜在风险点。",
            "data_source_hint": "Consensus estimates, official forecasts, institution reports",
            "placement_heading": "## 未来展望",
        },
    ]


def _fallback_blueprint(state: WorkflowState) -> dict:
    generation_config = normalize_generation_config(state.get("generation_config"))
    user_intent = state.get("user_intent", {})
    style_profile = state.get("style_profile", {})
    roles = generation_config["audience_roles"]
    resolved_strategy = user_intent.get("resolved_strategy", generation_config["article_strategy"])
    topic = str(user_intent.get("topic", state.get("keywords", "")) or "")
    is_finance_article = _is_finance_or_market_article(state)

    if is_finance_article:
        visualization_plan = _default_visualization_plan(topic)
        return {
            "article_type": "finance_market_deep_dive",
            "structure_style": "market brief + driver analysis + chart board + outlook + risk tracking",
            "title_strategy": style_profile.get("title_style", "标题先给结论，再点明关键变量和市场阶段"),
            "opening_goal": "开头先说明当前市场最值得关注的矛盾，再给出阶段性判断。",
            "reader_takeaway": user_intent.get("article_goal", ""),
            "search_focuses": ["官方统计", "供需数据", "库存变化", "机构预测", "风险因素"],
            "search_query_hints": [
                f"{topic} market supply demand data",
                f"{topic} inventory official data",
                f"{topic} outlook report",
                f"{topic} price drivers analysis",
                f"{topic} forecast vs actual demand",
            ],
            "ending_style": "结尾要收束观点，并给出后续跟踪指标与风险提醒。",
            "markdown_requirements": _default_markdown_requirements(True),
            "requires_data_visualization": True,
            "visualization_plan": visualization_plan,
            "planned_illustrations": min(max(len(visualization_plan), 3), 5),
            "section_outline": [
                {
                    "heading": "## 市场概况",
                    "goal": "交代当前市场所处阶段、核心价格区间、供需和库存的基线状态。",
                    "evidence_needed": ["官方统计", "供需数据", "库存数据"],
                },
                {
                    "heading": "## 价格驱动因素",
                    "goal": "拆解政策、地缘政治、经济周期、替代品和资金面如何影响价格。",
                    "evidence_needed": ["政策口径", "宏观数据", "行业报告"],
                },
                {
                    "heading": "## 数据图表观察",
                    "goal": "把最关键的图表集中呈现，并明确每张图说明了什么。",
                    "evidence_needed": ["时间序列数据", "同比/环比变化", "交叉对比数据"],
                },
                {
                    "heading": "## 未来展望",
                    "goal": "基于当前变量给出未来 6-12 个月的情景判断和关键跟踪点。",
                    "evidence_needed": ["预测数据", "机构预期", "边际变量"],
                },
                {
                    "heading": "## 风险与跟踪指标",
                    "goal": "明确判断可能失效的条件，以及接下来最值得跟踪的数据点。",
                    "evidence_needed": ["风险事件", "领先指标", "验证路径"],
                },
                {
                    "heading": "## 结论与行动建议",
                    "goal": "收束核心观点，告诉读者如何继续跟踪、验证和使用本文框架。",
                    "evidence_needed": ["关键结论", "行动建议"],
                },
            ],
            "resolved_strategy_label": resolve_strategy_label(resolved_strategy),
        }

    if resolved_strategy == "tech_breakdown":
        article_type = "technical_explainer"
        structure_style = "problem framing + mechanism breakdown + engineering limits + next steps"
        core_heading = "## 技术拆解：核心原理与能力边界"
        search_focuses = ["官方文档", "技术原理", "GitHub 或论文", "工程限制"]
    elif resolved_strategy == "application_review":
        article_type = "scenario_review"
        structure_style = "use case review + comparison + tradeoff analysis"
        core_heading = "## 应用评测：适用场景、体验与效果"
        search_focuses = ["产品功能", "使用场景", "对比案例", "优缺点"]
    else:
        article_type = "trend_analysis"
        structure_style = "hook + background + driver analysis + risk + action"
        core_heading = "## 趋势判断：行业变量、商业价值与节奏"
        search_focuses = ["官方发布", "权威媒体", "行业数据", "风险争议"]

    role_heading = (
        f"## 多角色视角：{' / '.join(roles)}"
        if len(roles) > 1
        else f"## {roles[0]}视角：最该关注什么"
    )
    section_outline = [
        {
            "heading": "## 开篇：为什么现在值得关注",
            "goal": "用最短篇幅解释这个主题当前的关注价值和现实意义。",
            "evidence_needed": ["最新背景", "时间节点", "关注原因"],
        },
        {
            "heading": "## 关键信息与背景",
            "goal": "交代公开资料里最关键的事实、时间线和背景信息。",
            "evidence_needed": ["官方信息", "关键时间线", "代表性事件"],
        },
        {
            "heading": core_heading,
            "goal": "展开本文最核心的分析部分，解释这件事到底意味着什么。",
            "evidence_needed": search_focuses[:3],
        },
        {
            "heading": role_heading,
            "goal": "回应目标读者最关心的问题，给出角色化判断重点。",
            "evidence_needed": roles,
        },
        {
            "heading": "## 风险与边界",
            "goal": "明确写出证据不足、落地阻碍、商业风险或能力边界。",
            "evidence_needed": ["争议点", "风险因素", "不确定性"],
        },
        {
            "heading": "## 结论与下一步",
            "goal": "给读者一个清晰结论，并说明接下来应该如何关注或验证。",
            "evidence_needed": ["跟踪指标", "行动建议"],
        },
    ]

    return {
        "article_type": article_type,
        "structure_style": structure_style,
        "title_strategy": style_profile.get("title_style", "标题突出价值点和核心判断"),
        "opening_goal": style_profile.get("opening_style", "开头解释为什么现在值得关注"),
        "reader_takeaway": user_intent.get("article_goal", ""),
        "search_focuses": search_focuses,
        "search_query_hints": [
            "official announcement",
            "official documentation",
            "latest news",
            "case study",
            "risk analysis",
        ],
        "ending_style": "结尾收束观点，并给出可执行的后续建议。",
        "markdown_requirements": _default_markdown_requirements(False),
        "requires_data_visualization": False,
        "visualization_plan": [],
        "planned_illustrations": 3,
        "section_outline": section_outline,
        "resolved_strategy_label": resolve_strategy_label(resolved_strategy),
    }


async def build_article_blueprint_node(state: WorkflowState) -> dict:
    """Use LLM to create the article structure, then derive backward-compatible article_plan."""
    task_id = state["task_id"]
    generation_config = normalize_generation_config(state.get("generation_config"))
    user_intent = state.get("user_intent", {})
    style_profile = state.get("style_profile", {})

    start_time = time.monotonic()
    logger.info(
        "skill_start",
        task_id=task_id,
        skill="build_article_blueprint",
        status="running",
    )

    blueprint = _fallback_blueprint(state)
    text_model_config = get_model_config().text
    if text_model_config.api_key:
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    (
                        "你是中文公众号内容策划。"
                        "你的任务是生成文章蓝图，而不是写正文。"
                        "请根据主题、读者角色、文章策略和风格画像，自主判断最合适的 article_type 和 structure_style。"
                        "蓝图必须面向 Markdown 写作，section_outline 中每个 heading 都必须以 '## ' 开头。"
                        "如果主题属于财经、金融、宏观、商品、市场、投资、能源或财报类，请主动规划 3-5 个图表位，"
                        "并在 visualization_plan 中写清图表标题、图表类型、用途、数据来源建议和放置章节。"
                        "蓝图里必须包含风险/边界类章节，以及结论/行动建议类章节。"
                    ),
                ),
                (
                    "human",
                    (
                        "主题：{topic}\n"
                        "目标角色：{roles}\n"
                        "文章策略：{strategy}\n"
                        "文章目标：{goal}\n"
                        "风格画像：{style_prompt}\n"
                        "用户补充风格：{style_hint}\n\n"
                        "请输出一份适合公众号写作的结构化文章蓝图。"
                    ),
                ),
            ]
        )
        llm = ChatOpenAI(
            model=text_model_config.model,
            api_key=text_model_config.api_key,
            base_url=text_model_config.base_url or None,
            max_tokens=2200,
            temperature=0.3,
        )
        chain = prompt | llm.with_structured_output(ArticleBlueprintOutput)
        invoke_payload = {
            "topic": user_intent.get("topic", state.get("keywords", "")),
            "roles": " / ".join(generation_config["audience_roles"]),
            "strategy": user_intent.get("resolved_strategy", generation_config["article_strategy"]),
            "goal": user_intent.get("article_goal", ""),
            "style_prompt": style_profile.get("style_prompt", ""),
            "style_hint": generation_config.get("style_hint", "") or "无",
        }
        model_context = build_model_context(
            model=text_model_config.model,
            base_url=text_model_config.base_url,
            api_key=text_model_config.api_key,
            structured_output="ArticleBlueprintOutput",
        )
        try:
            log_model_request(
                logger,
                task_id=task_id,
                skill="build_article_blueprint",
                context=model_context,
                request=invoke_payload,
            )
            result = await chain.ainvoke(invoke_payload)
            log_model_response(
                logger,
                task_id=task_id,
                skill="build_article_blueprint",
                context=model_context,
                response=result.model_dump(),
            )
            visualization_plan = [
                {
                    "title": item.title,
                    "chart_type": item.chart_type,
                    "insight_goal": item.insight_goal,
                    "data_source_hint": item.data_source_hint,
                    "placement_heading": item.placement_heading,
                }
                for item in result.visualization_plan
            ]
            requires_data_visualization = bool(result.requires_data_visualization)
            if requires_data_visualization and not visualization_plan:
                visualization_plan = _default_visualization_plan(invoke_payload["topic"])
            markdown_requirements = result.markdown_requirements or _default_markdown_requirements(
                requires_data_visualization
            )
            planned_illustrations = int(result.planned_illustrations or 3)
            if requires_data_visualization:
                planned_illustrations = min(max(planned_illustrations, len(visualization_plan), 3), 5)

            blueprint = {
                "article_type": result.article_type,
                "structure_style": result.structure_style,
                "title_strategy": result.title_strategy,
                "opening_goal": result.opening_goal,
                "reader_takeaway": result.reader_takeaway,
                "search_focuses": result.search_focuses,
                "search_query_hints": result.search_query_hints,
                "ending_style": result.ending_style,
                "markdown_requirements": markdown_requirements,
                "requires_data_visualization": requires_data_visualization,
                "visualization_plan": visualization_plan,
                "planned_illustrations": planned_illustrations,
                "section_outline": [
                    {
                        "heading": section.heading,
                        "goal": section.goal,
                        "evidence_needed": section.evidence_needed,
                    }
                    for section in result.section_outline
                ],
                "resolved_strategy_label": resolve_strategy_label(
                    user_intent.get("resolved_strategy", generation_config["article_strategy"])
                ),
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "build_article_blueprint_fallback",
                task_id=task_id,
                error=str(exc),
            )
    else:
        logger.info("build_article_blueprint_no_model_fallback", task_id=task_id)

    article_plan = build_article_plan(
        keywords=state.get("keywords", ""),
        generation_config=generation_config,
        user_intent=user_intent,
        style_profile=style_profile,
        article_blueprint=blueprint,
    )

    duration_ms = round((time.monotonic() - start_time) * 1000)
    logger.info(
        "skill_done",
        task_id=task_id,
        skill="build_article_blueprint",
        status="done",
        duration_ms=duration_ms,
        section_count=len(blueprint.get("section_outline", [])),
    )

    return {
        "status": "running",
        "current_skill": "build_article_blueprint",
        "progress": 35,
        "article_blueprint": blueprint,
        "article_plan": article_plan,
    }
