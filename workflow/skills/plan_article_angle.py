"""Build the dynamic article blueprint from task brief and article type."""
from __future__ import annotations

from typing import Any

import structlog
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from api.store import get_model_config
from workflow.model_logging import build_model_context, log_model_request, log_model_response
from workflow.state import WorkflowState

logger = structlog.get_logger(__name__)


class BlueprintOutput(BaseModel):
    """Structured article blueprint payload."""

    thesis: str = Field(description="Core thesis of the article")
    reader_value: str = Field(default="", description="Why the reader should care")
    sections: list[dict[str, str]] = Field(default_factory=list, description="Ordered H2 sections")
    must_cover_points: list[str] = Field(default_factory=list, description="Points that must be covered")
    drop_points: list[str] = Field(default_factory=list, description="Points intentionally left out")


def _topic_profile(topic: str) -> str:
    lowered = topic.lower()
    if "融资" in topic or "funding" in lowered or "investment" in lowered:
        return "funding"
    if "出海" in topic or "overseas" in lowered or "global" in lowered:
        return "expansion"
    if "发布" in topic or "launch" in lowered or "product" in lowered:
        return "launch"
    return "general"


def _build_dynamic_sections(topic: str, article_type: dict[str, Any], evidence_pack: dict[str, Any]) -> list[dict[str, str]]:
    profile = _topic_profile(topic)
    data_points = list(evidence_pack.get("usable_data_points") or [])
    cases = list(evidence_pack.get("usable_cases") or [])
    facts = list(evidence_pack.get("confirmed_facts") or [])

    if profile == "funding":
        sections = [
            {"heading": "这一轮融资潮先看什么", "goal": "先给结论，定义这轮热度的判断标准", "shape": "hook"},
            {"heading": "资金为什么重新流入", "goal": "解释驱动融资回暖的关键因素", "shape": "drivers"},
            {"heading": "资金流向了哪些方向", "goal": "结合数据看热点赛道和节奏", "shape": "evidence"},
            {"heading": "哪些公司真正吃到红利", "goal": "用案例区分热度和兑现能力", "shape": "case"},
            {"heading": "风险边界在哪里", "goal": "说明估值、交付和周期风险", "shape": "risks"},
        ]
    elif profile == "expansion":
        sections = [
            {"heading": "先看出海这件事值不值得做", "goal": "先判断主题的重要性", "shape": "hook"},
            {"heading": "海外市场到底缺什么", "goal": "解释需求侧差异", "shape": "drivers"},
            {"heading": "产品和渠道怎么分化", "goal": "看不同打法的结构差异", "shape": "evidence"},
            {"heading": "谁更有可能先跑出来", "goal": "结合案例判断胜率", "shape": "case"},
            {"heading": "风险边界在哪里", "goal": "说明本地化、成本和交付风险", "shape": "risks"},
        ]
    else:
        sections = [
            {"heading": "先给结论", "goal": "明确这件事为什么值得关注", "shape": "hook"},
            {"heading": "发生变化的核心原因", "goal": "解释驱动因素", "shape": "drivers"},
            {"heading": "哪些证据最值得看", "goal": "整合事实和数据", "shape": "evidence"},
            {"heading": "风险边界在哪里", "goal": "约束结论，说明不确定性", "shape": "risks"},
        ]

    if not data_points:
        sections = [section for section in sections if section["shape"] != "evidence"] + [
            {"heading": "还缺哪些关键验证", "goal": "指出证据不足的部分", "shape": "next_steps"}
        ]
    if not cases:
        sections = [section for section in sections if section["shape"] != "case"]
    if not facts and len(sections) < 4:
        sections.insert(1, {"heading": "背景里真正发生了什么", "goal": "补齐必要事实背景", "shape": "context"})

    return sections[:6]


def _build_fallback_blueprint(topic: str, article_type: dict[str, Any], evidence_pack: dict[str, Any]) -> BlueprintOutput:
    profile = _topic_profile(topic)
    thesis_map = {
        "funding": f"{topic}正在从热度走向分化判断",
        "expansion": f"{topic}的关键不在热闹，而在能否完成本地化落地",
        "launch": f"{topic}更值得看的是真实影响，而不是发布动作本身",
        "general": f"{topic}需要从主题和证据两侧重新组织判断",
    }
    reader_value_map = {
        "funding": "帮助读者判断这一轮融资热度的含金量",
        "expansion": "帮助读者判断出海机会和落地难点",
        "launch": "帮助读者判断新动作背后的真实价值",
        "general": "帮助读者快速建立主题判断框架",
    }
    sections = _build_dynamic_sections(topic, article_type, evidence_pack)
    must_cover_points = [section["heading"] for section in sections[:3]]
    drop_points = ["泛泛背景复述"] if profile in {"funding", "expansion"} else []
    return BlueprintOutput(
        thesis=thesis_map[profile],
        reader_value=reader_value_map[profile],
        sections=sections,
        must_cover_points=must_cover_points,
        drop_points=drop_points,
    )


def _build_evidence_summary(evidence_pack: dict[str, Any]) -> str:
    lines: list[str] = []
    for label in ("confirmed_facts", "usable_data_points", "usable_cases", "risk_points"):
        items = list(evidence_pack.get(label) or [])
        if not items:
            continue
        claims = [str(item.get("claim") or "").strip() for item in items[:4] if str(item.get("claim") or "").strip()]
        if claims:
            lines.append(f"{label}: " + " | ".join(claims))
    return "\n".join(lines)


async def plan_article_angle_node(state: WorkflowState) -> dict[str, Any]:
    """Create a dynamic section plan for the current article."""
    planning_state = dict(state.get("planning_state") or {})
    article_type = dict(planning_state.get("article_type") or {})
    topic = str(state.get("task_brief", {}).get("topic", "")).strip()
    research_state = dict(state.get("research_state") or {})
    evidence_pack = dict(research_state.get("evidence_pack") or {})

    text_model_config = get_model_config().text
    if not text_model_config.api_key:
        blueprint = _build_fallback_blueprint(topic, article_type, evidence_pack)
    else:
        system_prompt = (
            "You are a planning agent for Chinese long-form content. "
            "Generate a dynamic article blueprint based on topic, article type, and evidence density. "
            "Keep 4 to 6 H2 sections. Always include one risk-boundary section. "
            "Do not output a fixed template."
        )
        human_prompt = (
            "topic:\n{topic}\n\n"
            "article_type:\n{article_type}\n\n"
            "evidence_pack:\n{evidence_pack}\n"
        )
        prompt = ChatPromptTemplate.from_messages([("system", system_prompt), ("human", human_prompt)])
        llm = ChatOpenAI(
            model=text_model_config.model,
            api_key=text_model_config.api_key,
            base_url=text_model_config.base_url or None,
            max_tokens=1800,
            temperature=0.35,
        )
        chain = prompt | llm.with_structured_output(BlueprintOutput)
        payload = {
            "topic": topic,
            "article_type": article_type,
            "evidence_pack": _build_evidence_summary(evidence_pack),
        }
        model_context = build_model_context(
            model=text_model_config.model,
            base_url=text_model_config.base_url,
            api_key=text_model_config.api_key,
            structured_output="BlueprintOutput",
        )
        log_model_request(
            logger,
            task_id=str(state.get("task_id") or ""),
            skill="plan_article_angle",
            context=model_context,
            request=payload,
        )
        try:
            result = await chain.ainvoke(payload)
            blueprint = result if isinstance(result, BlueprintOutput) else BlueprintOutput(**dict(result))
            log_model_response(
                logger,
                task_id=str(state.get("task_id") or ""),
                skill="plan_article_angle",
                context=model_context,
                response=blueprint.model_dump(),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "plan_article_angle_fallback",
                task_id=str(state.get("task_id") or ""),
                error=str(exc),
            )
            blueprint = _build_fallback_blueprint(topic, article_type, evidence_pack)

    planning_state["article_blueprint"] = blueprint.model_dump()
    return {
        "status": "running",
        "current_skill": "plan_article_angle",
        "progress": 44,
        "planning_state": planning_state,
    }
