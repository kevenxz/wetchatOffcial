"""Research contract planning helpers."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


SEARCH_DEPTH_LIMITS: dict[str, dict[str, int]] = {
    "quick": {"min_sources": 3, "max_queries": 5, "max_rounds": 1, "fetch_per_query": 4},
    "standard": {"min_sources": 6, "max_queries": 8, "max_rounds": 2, "fetch_per_query": 6},
    "deep": {"min_sources": 10, "max_queries": 14, "max_rounds": 3, "fetch_per_query": 8},
    "strict": {"min_sources": 12, "max_queries": 18, "max_rounds": 3, "fetch_per_query": 8},
}

HIGH_RISK_CATEGORIES = {"finance", "military", "social"}
AUTHORITATIVE_TYPES = {"official", "documentation", "research", "institution", "media", "dataset"}


def normalize_research_policy(raw: Any) -> dict[str, Any]:
    """Normalize task-level research policy config."""
    policy = dict(raw or {}) if isinstance(raw, dict) else {}
    search_mode = str(policy.get("search_mode") or "standard").strip().lower()
    if search_mode not in SEARCH_DEPTH_LIMITS:
        search_mode = "standard"
    return {
        "search_mode": search_mode,
        "auto_deepen_for_sensitive_categories": bool(policy.get("auto_deepen_for_sensitive_categories", True)),
        "min_sources": max(1, min(int(policy.get("min_sources") or SEARCH_DEPTH_LIMITS[search_mode]["min_sources"]), 30)),
        "min_official_sources": max(0, min(int(policy.get("min_official_sources") or 1), 10)),
        "min_cross_sources": max(1, min(int(policy.get("min_cross_sources") or 3), 20)),
        "require_opposing_view": bool(policy.get("require_opposing_view", True)),
        "freshness_window_days": max(1, min(int(policy.get("freshness_window_days") or 7), 365)),
    }


def infer_research_category(topic: str, article_goal: str = "", selected_hotspot: dict[str, Any] | None = None) -> str:
    """Infer broad research category from topic and hotspot metadata."""
    text = f"{topic} {article_goal} {dict(selected_hotspot or {}).get('category', '')}".lower()
    if any(token in text for token in ("财报", "股价", "融资", "ipo", "营收", "利润", "估值", "交易所", "finance")):
        return "finance"
    if any(token in text for token in ("军事", "战争", "冲突", "导弹", "国防", "军方", "military")):
        return "military"
    if any(token in text for token in ("事故", "通报", "争议", "监管", "处罚", "社会", "舆情")):
        return "social"
    if any(token in text for token in ("消费", "品牌", "电商", "手机", "汽车", "家电")):
        return "consumer"
    if any(token in text for token in ("ai", "模型", "芯片", "机器人", "量子", "科技", "开源", "github", "论文")):
        return "technology"
    return "other"


def choose_search_depth(category: str, policy: dict[str, Any], selected_hotspot: dict[str, Any] | None = None) -> str:
    """Choose effective search depth with sensitive-category escalation."""
    requested = str(policy.get("search_mode") or "standard")
    if policy.get("auto_deepen_for_sensitive_categories", True):
        if category in {"finance", "military", "social"}:
            return "strict"
        if category == "technology" and requested == "quick":
            return "standard"
    if selected_hotspot and requested == "quick":
        return "standard"
    return requested if requested in SEARCH_DEPTH_LIMITS else "standard"


def default_query_plan(topic: str, category: str, *, selected_hotspot: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Build a multi-angle query matrix for the contract fallback."""
    base: list[dict[str, Any]] = [
        {
            "query": f"{topic} 官方 公告 原文",
            "purpose": "查找官方或一手来源",
            "source_type": "official",
            "priority": 1,
        },
        {
            "query": f"{topic} 最新 报道 解读",
            "purpose": "查找主流媒体报道和背景",
            "source_type": "media",
            "priority": 2,
        },
        {
            "query": f"{topic} 影响 分析",
            "purpose": "查找行业影响和解释性观点",
            "source_type": "analysis",
            "priority": 3,
        },
        {
            "query": f"{topic} 风险 争议 局限",
            "purpose": "查找反向观点和风险边界",
            "source_type": "opposing_view",
            "priority": 4,
        },
        {
            "query": f"{topic} 数据 时间线",
            "purpose": "查找关键数据、发布时间和事件线索",
            "source_type": "data",
            "priority": 5,
        },
    ]
    if category == "technology":
        base.extend(
            [
                {"query": f"{topic} API 文档 GitHub 论文", "purpose": "查找技术一手材料", "source_type": "documentation", "priority": 2},
                {"query": f"{topic} 对比 竞品 benchmark", "purpose": "查找竞品对比和能力边界", "source_type": "analysis", "priority": 4},
            ]
        )
    elif category == "finance":
        base.extend(
            [
                {"query": f"{topic} 财报 公告 PDF 交易所", "purpose": "查找财报、交易所或公司公告", "source_type": "official", "priority": 1},
                {"query": f"{topic} 分析师 评级 现金流 风险", "purpose": "查找市场反应和风险观点", "source_type": "analysis", "priority": 3},
            ]
        )
    elif category == "military":
        base.extend(
            [
                {"query": f"{topic} 官方通报 国际机构 声明", "purpose": "查找官方和国际机构说法", "source_type": "official", "priority": 1},
                {"query": f"{topic} 多方 声明 第三方 媒体", "purpose": "查找多方交叉验证", "source_type": "media", "priority": 2},
            ]
        )
    if selected_hotspot:
        platform = str(selected_hotspot.get("platform_name") or selected_hotspot.get("source") or "").strip()
        if platform:
            base.insert(
                1,
                {
                    "query": f"{topic} {platform} 原始来源",
                    "purpose": "核验热点榜单原始来源",
                    "source_type": "hotspot_verification",
                    "priority": 1,
                },
            )
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in sorted(base, key=lambda value: int(value.get("priority") or 99)):
        query = str(item.get("query") or "").strip()
        if not query or query in seen:
            continue
        seen.add(query)
        deduped.append(item)
    return deduped


def build_fallback_search_contract(
    *,
    task_id: str,
    topic: str,
    article_goal: str,
    selected_hotspot: dict[str, Any] | None,
    research_policy: dict[str, Any],
) -> dict[str, Any]:
    """Build a deterministic Search Contract when model planning is unavailable."""
    category = infer_research_category(topic, article_goal, selected_hotspot)
    depth = choose_search_depth(category, research_policy, selected_hotspot)
    limits = SEARCH_DEPTH_LIMITS[depth]
    is_hotspot = bool(selected_hotspot)
    min_sources = max(int(research_policy.get("min_sources") or 0), limits["min_sources"])
    min_official = int(research_policy.get("min_official_sources") or 1)
    min_cross = int(research_policy.get("min_cross_sources") or 3)
    requires_manual_review = depth == "strict" or category in HIGH_RISK_CATEGORIES
    must_find = ["事件的发布时间或最新时间点", "核心事实和背景", "至少一个风险或谨慎观点"]
    if min_official:
        must_find.append("官方公告、原始材料或权威一手来源")
    if is_hotspot:
        must_find.extend(["热点原始来源", "多源确认", "事件时间线"])
    return {
        "task_id": task_id,
        "topic": topic,
        "research_goal": article_goal or "判断该主题对微信公众号读者的真实影响和写作价值",
        "category": category,
        "search_depth": depth,
        "freshness_window_days": int(research_policy.get("freshness_window_days") or 7),
        "search_questions": [
            "这件事最可靠的一手来源是什么？",
            "核心事实、数据和时间线是什么？",
            "主流或行业媒体如何评价？",
            "有哪些风险、争议、局限或反向观点？",
            "对微信公众号读者真正有用的变化是什么？",
        ],
        "query_plan": default_query_plan(topic, category, selected_hotspot=selected_hotspot),
        "must_have_evidence": must_find,
        "source_rules": {
            "prefer": ["官方公告", "权威媒体", "行业报告", "一手数据", "主流机构"],
            "avoid": ["低质搬运站", "无来源自媒体", "标题党", "明显营销软文"],
        },
        "min_source_count": min_sources,
        "min_authoritative_source_count": max(min_official, 1),
        "min_cross_source_count": min_cross,
        "require_opposing_view": bool(research_policy.get("require_opposing_view", True)),
        "requires_manual_review": requires_manual_review,
        "hotspot_verification": {
            "require_original_source": is_hotspot,
            "require_multi_source_confirmation": is_hotspot,
            "require_timeline": is_hotspot,
            "require_risk_assessment": is_hotspot or category in HIGH_RISK_CATEGORIES,
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
        "planner_source": "fallback_rules",
    }


def normalize_search_contract(contract: dict[str, Any], *, fallback: dict[str, Any]) -> dict[str, Any]:
    """Validate and fill a model-produced contract with required defaults."""
    payload = dict(fallback)
    if isinstance(contract, dict):
        payload.update({key: value for key, value in contract.items() if value not in (None, "", [])})
    payload["category"] = str(payload.get("category") or fallback["category"])
    payload["search_depth"] = choose_search_depth(payload["category"], {"search_mode": payload.get("search_depth")}, None)
    payload["query_plan"] = [
        {
            "query": str(item.get("query") or "").strip(),
            "purpose": str(item.get("purpose") or item.get("intent") or "research").strip(),
            "source_type": str(item.get("source_type") or "unknown").strip(),
            "priority": max(1, int(item.get("priority") or index + 1)),
        }
        for index, item in enumerate(list(payload.get("query_plan") or []))
        if isinstance(item, dict) and str(item.get("query") or "").strip()
    ] or list(fallback["query_plan"])
    for numeric_key in ("freshness_window_days", "min_source_count", "min_authoritative_source_count", "min_cross_source_count"):
        payload[numeric_key] = max(0, int(payload.get(numeric_key) or fallback.get(numeric_key) or 0))
    payload["require_opposing_view"] = bool(payload.get("require_opposing_view", fallback.get("require_opposing_view", True)))
    payload["requires_manual_review"] = bool(payload.get("requires_manual_review", fallback.get("requires_manual_review", False)))
    return payload
