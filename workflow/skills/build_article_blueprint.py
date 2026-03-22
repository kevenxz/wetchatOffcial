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


class BlueprintSection(BaseModel):
    heading: str = Field(description="Markdown h2 heading, must start with ## ")
    goal: str
    evidence_needed: list[str] = Field(default_factory=list)


class ArticleBlueprintOutput(BaseModel):
    title_strategy: str
    opening_goal: str
    reader_takeaway: str
    search_focuses: list[str]
    search_query_hints: list[str]
    ending_style: str
    planned_illustrations: int = Field(default=3, ge=2, le=4)
    section_outline: list[BlueprintSection]


def _fallback_blueprint(state: WorkflowState) -> dict:
    generation_config = normalize_generation_config(state.get("generation_config"))
    user_intent = state.get("user_intent", {})
    style_profile = state.get("style_profile", {})
    roles = generation_config["audience_roles"]
    resolved_strategy = user_intent.get("resolved_strategy", generation_config["article_strategy"])

    if resolved_strategy == "tech_breakdown":
        core_heading = "## 技术拆解：核心原理与能力边界"
        search_focuses = ["官方文档", "技术原理", "GitHub 或论文", "工程限制"]
    elif resolved_strategy == "application_review":
        core_heading = "## 应用评测：适用场景、体验与效果"
        search_focuses = ["产品功能", "使用场景", "对比案例", "优缺点"]
    else:
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
            "goal": "用最短的篇幅说明主题的重要性和当前时间点的意义",
            "evidence_needed": ["最新背景", "时间点", "关注原因"],
        },
        {
            "heading": "## 事实背景：这件事已经发展到哪一步",
            "goal": "交代公开资料里最关键的事实、发布节点和背景信息",
            "evidence_needed": ["官方信息", "关键时间线", "代表性事件"],
        },
        {
            "heading": core_heading,
            "goal": "展开本文最核心的分析部分，解释它到底意味着什么",
            "evidence_needed": search_focuses[:3],
        },
        {
            "heading": role_heading,
            "goal": "回应目标读者最关心的问题，给出不同角色的判断重点",
            "evidence_needed": roles,
        },
        {
            "heading": "## 局限与风险",
            "goal": "明确写出证据不足、落地阻碍、商业化风险或能力边界",
            "evidence_needed": ["争议点", "风险因素", "不确定性"],
        },
        {
            "heading": "## 行动建议",
            "goal": "给出读者下一步如何关注、试用、评估或跟踪的建议",
            "evidence_needed": ["跟踪指标", "观察清单", "行动建议"],
        },
    ]

    return {
        "title_strategy": style_profile.get("title_style", "标题突出价值点和核心判断"),
        "opening_goal": style_profile.get("opening_style", "开头解释为什么现在值得关注"),
        "reader_takeaway": user_intent.get("article_goal", ""),
        "search_focuses": search_focuses,
        "search_query_hints": [
            "official announcement",
            "official blog",
            "documentation",
            "latest news",
            "risk analysis",
        ],
        "ending_style": "结尾收束观点，给出具体行动建议，不空喊口号",
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
                        "你是中文科技公众号的内容策划。"
                        "你的任务是生成文章蓝图，而不是正文。"
                        "蓝图必须包含固定的二级标题结构、每节目标和搜索重点，"
                        "方便后续搜索和写作节点直接执行。"
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
                        "请生成一份适合公众号写作的结构化文章蓝图。"
                        "要求 section_outline 中每个 heading 都以 '## ' 开头，"
                        "并且必须包含一个风险/局限类章节，以及一个行动建议/下一步类章节。"
                    ),
                ),
            ]
        )
        llm = ChatOpenAI(
            model=text_model_config.model,
            api_key=text_model_config.api_key,
            base_url=text_model_config.base_url or None,
            max_tokens=1600,
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
            blueprint = {
                "title_strategy": result.title_strategy,
                "opening_goal": result.opening_goal,
                "reader_takeaway": result.reader_takeaway,
                "search_focuses": result.search_focuses,
                "search_query_hints": result.search_query_hints,
                "ending_style": result.ending_style,
                "planned_illustrations": result.planned_illustrations,
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
