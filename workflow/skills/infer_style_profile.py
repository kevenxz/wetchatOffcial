"""Generate or infer an article style profile."""
from __future__ import annotations

import time

import structlog
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from api.store import get_model_config
from workflow.article_generation import infer_style_archetype, normalize_generation_config, style_archetype_profile
from workflow.model_logging import build_model_context, log_model_request, log_model_response
from workflow.state import WorkflowState

logger = structlog.get_logger(__name__)


class StyleProfileOutput(BaseModel):
    style_archetype: str = Field(description="One of finance_rational, tech_deep_explainer, product_review, trend_commentary")
    tone: str
    title_style: str
    opening_style: str
    paragraph_style: str
    evidence_style: str
    term_explanation_rule: str
    reference_direction: str
    focus_points: list[str]
    forbidden_patterns: list[str]
    style_prompt: str = Field(description="A compact instruction paragraph for the writing model")


def _fallback_style_profile(state: WorkflowState) -> dict:
    generation_config = normalize_generation_config(state.get("generation_config"))
    user_intent = state.get("user_intent", {})
    resolved_strategy = user_intent.get("resolved_strategy") or generation_config["article_strategy"]
    archetype = infer_style_archetype(
        state.get("keywords", ""),
        generation_config["audience_roles"],
        resolved_strategy,
    )
    profile = style_archetype_profile(archetype)
    style_hint = generation_config.get("style_hint", "")
    if style_hint:
        profile["style_source"] = "auto_plus_user_hint"
        profile["reference_direction"] = f"{profile['reference_direction']}；另外融合用户补充风格：{style_hint}"
        profile["style_prompt"] = f"{profile['style_prompt']} 另外融合用户补充风格：{style_hint}。"
    return profile


async def infer_style_profile_node(state: WorkflowState) -> dict:
    """Use LLM to derive a stable style profile, with heuristic fallback."""
    task_id = state["task_id"]
    generation_config = normalize_generation_config(state.get("generation_config"))
    user_intent = state.get("user_intent", {})

    start_time = time.monotonic()
    logger.info(
        "skill_start",
        task_id=task_id,
        skill="infer_style_profile",
        status="running",
    )

    profile = _fallback_style_profile(state)
    text_model_config = get_model_config().text
    if text_model_config.api_key:
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    (
                        "你是中文科技公众号的写作策略顾问。"
                        "你的任务不是写正文，而是根据主题、读者角色和文章类型，生成一份稳定的风格画像。"
                        "风格画像要抽象为可执行写作规则，不要模仿具体账号原句。"
                        "如果用户给了补充风格要求，要把它融合进风格画像。"
                    ),
                ),
                (
                    "human",
                    (
                        "主题：{topic}\n"
                        "目标角色：{roles}\n"
                        "文章策略：{strategy}\n"
                        "文章目标：{goal}\n"
                        "用户补充风格：{style_hint}\n\n"
                        "可选风格原型：finance_rational、tech_deep_explainer、product_review、trend_commentary。\n"
                        "请输出适合中文科技公众号的结构化风格画像。"
                    ),
                ),
            ]
        )
        llm = ChatOpenAI(
            model=text_model_config.model,
            api_key=text_model_config.api_key,
            base_url=text_model_config.base_url or None,
            max_tokens=1200,
            temperature=0.3,
        )
        chain = prompt | llm.with_structured_output(StyleProfileOutput)
        invoke_payload = {
            "topic": user_intent.get("topic", state.get("keywords", "")),
            "roles": " / ".join(generation_config["audience_roles"]),
            "strategy": user_intent.get("resolved_strategy", generation_config["article_strategy"]),
            "goal": user_intent.get("article_goal", ""),
            "style_hint": generation_config.get("style_hint", "") or "无",
        }
        model_context = build_model_context(
            model=text_model_config.model,
            base_url=text_model_config.base_url,
            api_key=text_model_config.api_key,
            structured_output="StyleProfileOutput",
        )
        try:
            log_model_request(
                logger,
                task_id=task_id,
                skill="infer_style_profile",
                context=model_context,
                request=invoke_payload,
            )
            result = await chain.ainvoke(invoke_payload)
            log_model_response(
                logger,
                task_id=task_id,
                skill="infer_style_profile",
                context=model_context,
                response=result.model_dump(),
            )
            profile = {
                "style_source": "llm_generated" if not generation_config.get("style_hint") else "llm_plus_user_hint",
                "style_archetype": result.style_archetype,
                "tone": result.tone,
                "title_style": result.title_style,
                "opening_style": result.opening_style,
                "paragraph_style": result.paragraph_style,
                "evidence_style": result.evidence_style,
                "term_explanation_rule": result.term_explanation_rule,
                "reference_direction": result.reference_direction,
                "focus_points": result.focus_points,
                "forbidden_patterns": result.forbidden_patterns,
                "style_prompt": result.style_prompt,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "infer_style_profile_fallback",
                task_id=task_id,
                error=str(exc),
            )
    else:
        logger.info("infer_style_profile_no_model_fallback", task_id=task_id)

    duration_ms = round((time.monotonic() - start_time) * 1000)
    logger.info(
        "skill_done",
        task_id=task_id,
        skill="infer_style_profile",
        status="done",
        duration_ms=duration_ms,
        style_archetype=profile.get("style_archetype"),
        style_source=profile.get("style_source"),
    )

    return {
        "status": "running",
        "current_skill": "infer_style_profile",
        "progress": 25,
        "style_profile": profile,
    }
