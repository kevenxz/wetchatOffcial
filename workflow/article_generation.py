"""Shared helpers for article generation config, style inference and planning."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

DEFAULT_AUDIENCE_ROLE = "泛科技读者"
DEFAULT_AUDIENCE_ROLES = [DEFAULT_AUDIENCE_ROLE]
DEFAULT_ARTICLE_STRATEGY = "auto"
DEFAULT_STYLE_HINT = ""

ARTICLE_STRATEGY_VALUES = (
    "auto",
    "tech_breakdown",
    "application_review",
    "trend_outlook",
)
ARTICLE_STRATEGY_LABELS: dict[str, str] = {
    "auto": "自动判断",
    "tech_breakdown": "技术揭秘式",
    "application_review": "应用评测式",
    "trend_outlook": "趋势展望式",
}

ROLE_FOCUS_MAP: dict[str, list[str]] = {
    "泛科技读者": [
        "这件事为什么现在值得关注",
        "它会如何影响普通读者的工作与生活",
        "需要避免哪些常见误解",
    ],
    "开发者": [
        "核心原理、系统架构和能力边界",
        "实现成本、工程约束与落地难点",
        "下一步适合学习什么、怎么验证",
    ],
    "产品经理": [
        "用户价值、体验差异和适配场景",
        "适合切入的产品机会与指标变化",
        "真实可落地的功能设计与避坑点",
    ],
    "投资者": [
        "市场空间、商业化路径与行业节奏",
        "竞争格局、关键变量与估值逻辑",
        "短期风险与中长期机会在哪里",
    ],
    "企业管理者": [
        "对组织效率、成本结构和收入的影响",
        "试点路径、资源投入和落地门槛",
        "什么阶段适合投入，什么阶段先观望",
    ],
}

STYLE_ARCHETYPES: dict[str, dict[str, Any]] = {
    "finance_rational": {
        "tone": "理性克制，少煽动，多判断",
        "title_style": "标题突出价值判断与关键变量，不做夸张情绪化表达",
        "opening_style": "开头先说明为什么这个主题现在值得关注，再给出阶段性结论",
        "paragraph_style": "短段落，高信息密度，结论先行",
        "evidence_style": "优先使用数据、案例、对比和风险提示支撑论点",
        "term_rule": "术语首次出现时，采用“术语 + 中文解释 + 一句话类比”",
        "reference_direction": "参考财经类公众号常见的克制分析写法，但不模仿具体账号措辞",
        "focus_points": ["商业价值", "增长逻辑", "竞争格局", "风险因素", "行动窗口"],
        "forbidden_patterns": ["空泛赞美", "强营销口号", "没有依据的乐观判断"],
    },
    "tech_deep_explainer": {
        "tone": "专业、克制、解释清晰",
        "title_style": "标题突出原理拆解、能力边界或关键机制",
        "opening_style": "开头先点明核心问题，再告诉读者本文会拆解什么",
        "paragraph_style": "段落短，层次分明，优先解释再下结论",
        "evidence_style": "优先使用官方文档、论文、代码仓库和技术案例",
        "term_rule": "术语首次出现时，采用“术语 + 中文解释 + 一句话类比”",
        "reference_direction": "参考科技深度解读账号的表达方式，强调降维解释和结构清晰",
        "focus_points": ["技术原理", "实现方式", "性能边界", "成本约束", "适用场景"],
        "forbidden_patterns": ["玄学式描述", "不解释术语", "把能力吹成万能"],
    },
    "product_review": {
        "tone": "客观直接，强调体验和结论",
        "title_style": "标题突出场景、对比结果和实用价值",
        "opening_style": "开头先给使用场景和核心判断，再进入比较",
        "paragraph_style": "多用短句和小结，方便公众号阅读",
        "evidence_style": "优先使用功能对比、体验细节和真实使用案例",
        "term_rule": "术语首次出现时，采用“术语 + 中文解释 + 一句话类比”",
        "reference_direction": "参考工具评测型科技账号的表达方式，重点讲清适合谁、不适合谁",
        "focus_points": ["典型场景", "优缺点", "成本收益", "适用人群", "替代方案"],
        "forbidden_patterns": ["流水账式罗列", "只夸不讲缺点", "没有比较基准"],
    },
    "trend_commentary": {
        "tone": "克制、敏锐、强调结构变化",
        "title_style": "标题突出行业变化、关键变量和未来影响",
        "opening_style": "开头先解释时间点，再讲为什么值得持续跟踪",
        "paragraph_style": "段落紧凑，观点和依据交替出现",
        "evidence_style": "优先使用行业新闻、官方发布、研究机构和第三方案例交叉验证",
        "term_rule": "术语首次出现时，采用“术语 + 中文解释 + 一句话类比”",
        "reference_direction": "参考科技趋势观察类公众号的写法，强调变化方向和判断框架",
        "focus_points": ["行业变化", "驱动因素", "受益方", "潜在风险", "后续观察点"],
        "forbidden_patterns": ["口号化趋势判断", "只谈未来不谈证据", "忽略不确定性"],
    },
}


def normalize_generation_config(config: Mapping[str, Any] | None) -> dict[str, Any]:
    """Normalize generation config so workflow and persistence share one shape."""
    roles: list[str] = []
    strategy = DEFAULT_ARTICLE_STRATEGY
    style_hint = DEFAULT_STYLE_HINT

    if isinstance(config, Mapping):
        raw_roles = config.get("audience_roles")
        if isinstance(raw_roles, (list, tuple)):
            for role in raw_roles:
                if not isinstance(role, str):
                    continue
                cleaned = role.strip()
                if cleaned and cleaned not in roles:
                    roles.append(cleaned)

        raw_strategy = config.get("article_strategy")
        if isinstance(raw_strategy, str):
            strategy = raw_strategy.strip() or DEFAULT_ARTICLE_STRATEGY

        raw_style_hint = config.get("style_hint")
        if isinstance(raw_style_hint, str):
            style_hint = raw_style_hint.strip()

    if not roles:
        roles = list(DEFAULT_AUDIENCE_ROLES)
    if strategy not in ARTICLE_STRATEGY_VALUES:
        strategy = DEFAULT_ARTICLE_STRATEGY

    return {
        "audience_roles": roles,
        "article_strategy": strategy,
        "style_hint": style_hint,
    }


def role_focus_points(role: str) -> list[str]:
    """Return focus points for a given role, with a generic fallback."""
    return ROLE_FOCUS_MAP.get(
        role,
        [
            "这件事最重要的价值和变化",
            "它对目标读者意味着什么",
            "有哪些必须冷静看待的风险与边界",
        ],
    )


def infer_article_strategy(keywords: str, audience_roles: list[str]) -> str:
    """Infer article strategy from topic and audience."""
    text = f"{keywords} {' '.join(audience_roles)}".lower()
    if any(token in text for token in ("vs", "pk", "对比", "评测", "横评", "测评", "review")):
        return "application_review"
    if any(token in text for token in ("原理", "架构", "技术", "源码", "解析", "拆解", "benchmark")):
        return "tech_breakdown"
    if any(token in text for token in ("趋势", "前景", "机会", "投资", "市场", "格局", "融资")):
        return "trend_outlook"

    primary_role = audience_roles[0] if audience_roles else ""
    if primary_role in {"开发者"}:
        return "tech_breakdown"
    if primary_role in {"投资者", "企业管理者"}:
        return "trend_outlook"
    return "application_review"


def resolve_strategy_label(strategy: str) -> str:
    return ARTICLE_STRATEGY_LABELS.get(strategy, strategy)


def infer_style_archetype(keywords: str, audience_roles: list[str], strategy: str) -> str:
    """Infer a style archetype from roles and strategy."""
    text = f"{keywords} {' '.join(audience_roles)}".lower()
    primary_role = audience_roles[0] if audience_roles else DEFAULT_AUDIENCE_ROLE

    if primary_role == "投资者" or any(token in text for token in ("投资", "融资", "估值", "财报", "商业化")):
        return "finance_rational"
    if strategy == "tech_breakdown" or primary_role == "开发者":
        return "tech_deep_explainer"
    if strategy == "application_review" or primary_role == "产品经理":
        return "product_review"
    return "trend_commentary"


def style_archetype_profile(archetype: str) -> dict[str, Any]:
    """Return a copy of the baseline profile for one style archetype."""
    profile = STYLE_ARCHETYPES.get(archetype) or STYLE_ARCHETYPES["trend_commentary"]
    return {
        "style_archetype": archetype if archetype in STYLE_ARCHETYPES else "trend_commentary",
        "style_source": "auto_inferred",
        "tone": profile["tone"],
        "title_style": profile["title_style"],
        "opening_style": profile["opening_style"],
        "paragraph_style": profile["paragraph_style"],
        "evidence_style": profile["evidence_style"],
        "term_explanation_rule": profile["term_rule"],
        "reference_direction": profile["reference_direction"],
        "focus_points": list(profile["focus_points"]),
        "forbidden_patterns": list(profile["forbidden_patterns"]),
        "style_prompt": (
            f"整体采用“{profile['tone']}”的科技公众号写法，"
            f"{profile['opening_style']}；{profile['paragraph_style']}；"
            f"{profile['evidence_style']}；{profile['term_rule']}。"
        ),
    }


def build_article_plan(
    *,
    keywords: str,
    generation_config: Mapping[str, Any],
    user_intent: Mapping[str, Any],
    style_profile: Mapping[str, Any],
    article_blueprint: Mapping[str, Any],
) -> dict[str, Any]:
    """Build backward-compatible article_plan from newer intent/style/blueprint states."""
    normalized_generation_config = normalize_generation_config(generation_config)
    requested_strategy = normalized_generation_config["article_strategy"]
    audience_roles = normalized_generation_config["audience_roles"]
    resolved_strategy = str(
        user_intent.get("resolved_strategy")
        or user_intent.get("article_type")
        or infer_article_strategy(keywords, audience_roles)
    )
    section_outline = [
        section.get("heading", "").strip()
        for section in article_blueprint.get("section_outline", [])
        if isinstance(section, Mapping) and section.get("heading")
    ]
    planned_illustrations = int(article_blueprint.get("planned_illustrations", 3) or 3)
    return {
        "primary_role": audience_roles[0] if audience_roles else DEFAULT_AUDIENCE_ROLE,
        "audience_roles": audience_roles,
        "requested_strategy": requested_strategy,
        "resolved_strategy": resolved_strategy,
        "resolved_strategy_label": resolve_strategy_label(resolved_strategy),
        "title_strategy": article_blueprint.get("title_strategy") or style_profile.get("title_style", ""),
        "section_outline": section_outline,
        "role_focuses": [
            {"role": role, "focus_points": role_focus_points(role)}
            for role in audience_roles
        ],
        "planned_illustrations": planned_illustrations,
        "tone": style_profile.get("tone", "理性兴奋"),
        "style_archetype": style_profile.get("style_archetype", "trend_commentary"),
        "search_focuses": list(article_blueprint.get("search_focuses", [])),
    }
