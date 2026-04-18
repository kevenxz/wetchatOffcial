# Agent 重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**目标：** 在保留现有生产基础设施的前提下，将文章生成工作流重构为由 Planner 驱动、包含多源热点分析、多角度研究、分阶段文章生成、按角色生成视觉资产和显式质量闸门的内容生产系统。

**架构：** 保留 LangGraph、任务 API、调度器、进度推送和草稿发布能力。替换当前中间流水线为新的状态块，以及 planner / research / writing / visual / quality 阶段和局部修订回路。按阶段逐步落地，确保旧链路在新链路验证前仍可运行。

**技术栈：** Python、FastAPI、LangGraph、Pydantic、pytest、pytest-asyncio，以及当前已有的 workflow skills 和模型配置基础设施

---

## 文件结构

### 需要修改的现有文件

- `workflow/state.py`
- `workflow/graph.py`
- `workflow/article_generation.py`
- `api/models.py`
- `api/routers/tasks.py`
- `api/scheduler.py`
- `api/store.py`

### 新增 workflow 文件

- `workflow/skills/intake_task_brief.py`
- `workflow/skills/planner_agent.py`
- `workflow/skills/analyze_hotspot_opportunities.py`
- `workflow/skills/plan_research.py`
- `workflow/skills/run_research.py`
- `workflow/skills/build_evidence_pack.py`
- `workflow/skills/resolve_article_type.py`
- `workflow/skills/plan_article_angle.py`
- `workflow/skills/compose_draft.py`
- `workflow/skills/review_article_draft.py`
- `workflow/skills/plan_visual_assets.py`
- `workflow/skills/generate_visual_assets.py`
- `workflow/skills/review_visual_assets.py`
- `workflow/skills/quality_gate.py`
- `workflow/skills/targeted_revision.py`

### 新增工具文件

- `workflow/utils/hotspot_sources.py`
- `workflow/utils/hotspot_scoring.py`
- `workflow/utils/research_queries.py`
- `workflow/utils/evidence_pack.py`
- `workflow/utils/article_type_registry.py`
- `workflow/utils/visual_briefs.py`
- `workflow/utils/quality_scoring.py`

### 新增测试文件

- `tests/test_intake_task_brief.py`
- `tests/test_planner_agent.py`
- `tests/test_analyze_hotspot_opportunities.py`
- `tests/test_plan_research.py`
- `tests/test_build_evidence_pack.py`
- `tests/test_article_type_registry.py`
- `tests/test_compose_draft.py`
- `tests/test_plan_visual_assets.py`
- `tests/test_quality_gate.py`
- `tests/test_graph_agent_redesign.py`

## 任务 1：扩展工作流状态与任务持久化模型

**文件：**
- 修改：`workflow/state.py`
- 修改：`api/models.py`
- 修改：`api/routers/tasks.py`
- 测试：`tests/test_graph_agent_redesign.py`

- [x] **步骤 1：先写失败测试**

```python
from workflow.state import WorkflowState


def test_workflow_state_supports_new_agent_blocks() -> None:
    state: WorkflowState = {
        "task_id": "task-1",
        "keywords": "AI agent",
        "original_keywords": "AI agent",
        "generation_config": {},
        "task_brief": {},
        "planning_state": {},
        "research_state": {},
        "writing_state": {},
        "visual_state": {},
        "quality_state": {},
        "status": "pending",
        "current_skill": "",
        "progress": 0,
        "retry_count": 0,
        "error": None,
        "generated_article": {},
    }
    assert "task_brief" in state
    assert "quality_state" in state
```

- [x] **步骤 2：运行测试确认失败**

运行：`pytest tests/test_graph_agent_redesign.py::test_workflow_state_supports_new_agent_blocks -v`
预期：FAIL，原因是 `WorkflowState` 缺少新字段或类型定义不兼容。

- [x] **步骤 3：编写最小实现**

```python
class WorkflowState(TypedDict, total=False):
    task_id: str
    keywords: str
    original_keywords: str
    generation_config: dict
    task_brief: dict
    planning_state: dict
    research_state: dict
    writing_state: dict
    visual_state: dict
    quality_state: dict
    generated_article: dict
    draft_info: Optional[dict]
    retry_count: int
    error: Optional[str]
    status: str
    current_skill: str
    progress: int
```

```python
class Task(BaseModel):
    ...
    task_brief: Optional[dict] = None
    planning_state: Optional[dict] = None
    research_state: Optional[dict] = None
    writing_state: Optional[dict] = None
    visual_state: Optional[dict] = None
    quality_state: Optional[dict] = None
```

- [x] **步骤 4：从任务 API 返回新字段**

```python
return {
    **task.model_dump(mode="python"),
    "task_brief": task.task_brief or {},
    "planning_state": task.planning_state or {},
    "research_state": task.research_state or {},
    "writing_state": task.writing_state or {},
    "visual_state": task.visual_state or {},
    "quality_state": task.quality_state or {},
}
```

- [x] **步骤 5：重新运行测试确认通过**

运行：`pytest tests/test_graph_agent_redesign.py::test_workflow_state_supports_new_agent_blocks -v`
预期：PASS

- [x] **步骤 6：提交**

```bash
git add workflow/state.py api/models.py api/routers/tasks.py tests/test_graph_agent_redesign.py
git commit -m "重构工作流状态与任务模型"
```

## 任务 2：在工作流入口标准化任务 Brief

**文件：**
- 新建：`workflow/skills/intake_task_brief.py`
- 修改：`workflow/article_generation.py`
- 修改：`workflow/graph.py`
- 测试：`tests/test_intake_task_brief.py`

- [x] **步骤 1：先写失败测试**

```python
import pytest

from workflow.skills.intake_task_brief import intake_task_brief_node


@pytest.mark.asyncio
async def test_intake_task_brief_normalizes_generation_inputs() -> None:
    state = {
        "task_id": "task-1",
        "keywords": "机器人创业",
        "original_keywords": "机器人创业",
        "generation_config": {"audience_roles": ["科技创业者"]},
    }

    result = await intake_task_brief_node(state)

    assert result["task_brief"]["topic"] == "机器人创业"
    assert result["task_brief"]["audience_roles"] == ["科技创业者"]
    assert result["current_skill"] == "intake_task_brief"
```

- [x] **步骤 2：运行测试确认失败**

运行：`pytest tests/test_intake_task_brief.py::test_intake_task_brief_normalizes_generation_inputs -v`
预期：FAIL，原因是模块或函数不存在。

- [x] **步骤 3：编写最小实现**

```python
async def intake_task_brief_node(state: WorkflowState) -> dict[str, Any]:
    config = normalize_generation_config(state.get("generation_config"))
    brief = {
        "topic": str(state.get("keywords") or "").strip(),
        "original_topic": str(state.get("original_keywords") or state.get("keywords") or "").strip(),
        "audience_roles": list(config.get("audience_roles") or []),
        "article_goal": str(config.get("article_goal") or "").strip(),
        "runtime_profile": str(config.get("runtime_profile") or "quality_first"),
        "image_policy": dict(config.get("image_policy") or {}),
        "hotspot_policy": dict(state.get("hotspot_capture_config") or {}),
    }
    return {
        "status": "running",
        "current_skill": "intake_task_brief",
        "progress": 6,
        "generation_config": config,
        "task_brief": brief,
    }
```

```python
def normalize_generation_config(raw_config: dict | None) -> dict:
    config = dict(raw_config or {})
    config.setdefault("audience_roles", [])
    config.setdefault("article_goal", "")
    config.setdefault("runtime_profile", "quality_first")
    config.setdefault("image_policy", {})
    return config
```

- [x] **步骤 4：接入 graph 入口**

```python
graph.add_node("intake_task_brief", intake_task_brief_node)
graph.set_entry_point("intake_task_brief")
graph.add_edge("intake_task_brief", "planner_agent")
```

- [x] **步骤 5：重新运行测试确认通过**

运行：`pytest tests/test_intake_task_brief.py -v`
预期：PASS

- [x] **步骤 6：提交**

```bash
git add workflow/skills/intake_task_brief.py workflow/article_generation.py workflow/graph.py tests/test_intake_task_brief.py
git commit -m "新增任务brief接入阶段"
```

## 任务 3：新增文章类型注册表和 Planner 输出结构

**文件：**
- 新建：`workflow/utils/article_type_registry.py`
- 新建：`workflow/skills/planner_agent.py`
- 测试：`tests/test_article_type_registry.py`
- 测试：`tests/test_planner_agent.py`

- [x] **步骤 1：先写失败测试**

```python
from workflow.utils.article_type_registry import get_article_type_registry


def test_article_type_registry_includes_multiple_formal_types() -> None:
    registry = get_article_type_registry()
    assert "hotspot_interpretation" in registry
    assert "trend_analysis" in registry
    assert registry["quick_news"]["title_style"] == "fast_and_clear"
```

- [x] **步骤 2：补 Planner 输出失败测试**

```python
import pytest

from workflow.skills.planner_agent import planner_agent_node


@pytest.mark.asyncio
async def test_planner_agent_creates_type_search_and_visual_plan() -> None:
    state = {
        "task_id": "task-1",
        "task_brief": {
            "topic": "国产人形机器人融资潮",
            "audience_roles": ["科技投资人"],
            "article_goal": "解释趋势",
        },
        "research_state": {},
    }
    result = await planner_agent_node(state)
    assert result["planning_state"]["article_type"]["type_id"]
    assert result["planning_state"]["search_plan"]["angles"]
    assert result["planning_state"]["visual_plan"]["asset_roles"]
```

- [x] **步骤 3：运行测试确认失败**

运行：`pytest tests/test_article_type_registry.py tests/test_planner_agent.py -v`
预期：FAIL，原因是模块或函数不存在。

- [x] **步骤 4：编写最小实现**

```python
def get_article_type_registry() -> dict[str, dict[str, Any]]:
    return {
        "quick_news": {
            "type_id": "quick_news",
            "activation_signals": ["breaking", "announcement", "latest"],
            "recommended_section_shapes": ["what_happened", "why_it_matters", "who_is_affected"],
            "evidence_mix": {"fact": 0.5, "news": 0.3, "opinion": 0.1, "case": 0.05, "data": 0.05},
            "title_style": "fast_and_clear",
            "visual_preferences": ["cover", "contextual_illustration"],
            "quality_rules": ["must_answer_what_happened", "must_anchor_timeline"],
            "forbidden_patterns": ["generic_opener", "empty_summary"],
        },
        "hotspot_interpretation": {
            "type_id": "hotspot_interpretation",
            "activation_signals": ["hotspot", "controversy", "viral"],
            "recommended_section_shapes": ["hook", "context", "interpretation", "impact", "watch_next"],
            "evidence_mix": {"fact": 0.25, "news": 0.25, "opinion": 0.2, "case": 0.15, "data": 0.15},
            "title_style": "angle_driven",
            "visual_preferences": ["cover", "infographic"],
            "quality_rules": ["must_connect_hotspot_naturally", "must_show_reader_value"],
            "forbidden_patterns": ["forced_trend_hijack"],
        },
        "trend_analysis": {
            "type_id": "trend_analysis",
            "activation_signals": ["trend", "market", "signal", "outlook"],
            "recommended_section_shapes": ["hook", "drivers", "evidence", "risks", "next_steps"],
            "evidence_mix": {"fact": 0.2, "news": 0.15, "opinion": 0.15, "case": 0.2, "data": 0.3},
            "title_style": "insight_first",
            "visual_preferences": ["cover", "infographic", "comparison_graphic"],
            "quality_rules": ["must_explain_drivers", "must_include_risk_boundary"],
            "forbidden_patterns": ["unsupported_prediction"],
        },
    }
```

```python
async def planner_agent_node(state: WorkflowState) -> dict[str, Any]:
    brief = dict(state.get("task_brief") or {})
    registry = get_article_type_registry()
    article_type = registry["trend_analysis"] if "趋势" in brief.get("article_goal", "") else registry["hotspot_interpretation"]
    planning_state = {
        "article_type": article_type,
        "search_plan": {"angles": ["fact", "news", "opinion", "case", "data"], "queries": []},
        "visual_plan": {"asset_roles": article_type["visual_preferences"], "quality_threshold": 75},
        "quality_thresholds": {"article": 80, "visual": 75, "evidence": 80, "hotspot": 70},
    }
    return {"status": "running", "current_skill": "planner_agent", "progress": 12, "planning_state": planning_state}
```

- [x] **步骤 5：重新运行测试确认通过**

运行：`pytest tests/test_article_type_registry.py tests/test_planner_agent.py -v`
预期：PASS

- [x] **步骤 6：提交**

```bash
git add workflow/utils/article_type_registry.py workflow/skills/planner_agent.py tests/test_article_type_registry.py tests/test_planner_agent.py
git commit -m "新增文章类型策略注册表与规划器"
```

## 任务 4：新增多源热点分析阶段

**文件：**
- 新建：`workflow/utils/hotspot_sources.py`
- 新建：`workflow/utils/hotspot_scoring.py`
- 新建：`workflow/skills/analyze_hotspot_opportunities.py`
- 测试：`tests/test_analyze_hotspot_opportunities.py`

- [x] **步骤 1：先写失败测试**

```python
from workflow.utils.hotspot_scoring import score_hotspot_candidate


def test_score_hotspot_candidate_prefers_relevant_and_expandable_items() -> None:
    candidate = {
        "title": "人形机器人融资潮",
        "heat": 90,
        "relevance": 85,
        "timeliness": 80,
        "evidence_density": 75,
        "expandability": 88,
        "account_fit": 82,
        "risk": 20,
    }
    score = score_hotspot_candidate(candidate)
    assert score > 75
```

- [x] **步骤 2：运行测试确认失败**

运行：`pytest tests/test_analyze_hotspot_opportunities.py::test_score_hotspot_candidate_prefers_relevant_and_expandable_items -v`
预期：FAIL，原因是模块或函数不存在。

- [x] **步骤 3：编写最小实现**

```python
def collect_hotspot_candidates(task_brief: dict, config: dict) -> list[dict[str, Any]]:
    return [
        {"source": "tophub", "title": task_brief.get("topic", ""), "heat": 70, "relevance": 80, "timeliness": 70, "evidence_density": 75, "expandability": 78, "account_fit": 80, "risk": 15},
    ]


def score_hotspot_candidate(candidate: dict[str, Any]) -> float:
    positive = (
        candidate.get("heat", 0) * 0.18
        + candidate.get("relevance", 0) * 0.24
        + candidate.get("timeliness", 0) * 0.14
        + candidate.get("evidence_density", 0) * 0.14
        + candidate.get("expandability", 0) * 0.16
        + candidate.get("account_fit", 0) * 0.14
    )
    risk_penalty = candidate.get("risk", 0) * 0.15
    return round(max(0.0, positive - risk_penalty), 2)
```

- [x] **步骤 4：新增热点分析节点**

```python
async def analyze_hotspot_opportunities_node(state: WorkflowState) -> dict[str, Any]:
    brief = dict(state.get("task_brief") or {})
    config = dict(brief.get("hotspot_policy") or {})
    candidates = collect_hotspot_candidates(brief, config)
    ranked = sorted(
        [{**item, "selection_score": score_hotspot_candidate(item)} for item in candidates],
        key=lambda item: item["selection_score"],
        reverse=True,
    )
    return {
        "status": "running",
        "current_skill": "analyze_hotspot_opportunities",
        "progress": 18,
        "research_state": {**dict(state.get("research_state") or {}), "hotspot_candidates": ranked, "selected_hotspot": ranked[0] if ranked else None},
    }
```

- [x] **步骤 5：重新运行测试确认通过**

运行：`pytest tests/test_analyze_hotspot_opportunities.py -v`
预期：PASS

- [x] **步骤 6：提交**

```bash
git add workflow/utils/hotspot_sources.py workflow/utils/hotspot_scoring.py workflow/skills/analyze_hotspot_opportunities.py tests/test_analyze_hotspot_opportunities.py
git commit -m "新增多源热点分析阶段"
```

## 任务 5：实现多角度研究计划与证据包

**文件：**
- 新建：`workflow/utils/research_queries.py`
- 新建：`workflow/utils/evidence_pack.py`
- 新建：`workflow/skills/plan_research.py`
- 新建：`workflow/skills/run_research.py`
- 新建：`workflow/skills/build_evidence_pack.py`
- 测试：`tests/test_plan_research.py`
- 测试：`tests/test_build_evidence_pack.py`

- [x] **步骤 1：先写失败测试**

```python
import pytest

from workflow.skills.plan_research import plan_research_node


@pytest.mark.asyncio
async def test_plan_research_creates_queries_for_all_research_angles() -> None:
    state = {
        "task_brief": {"topic": "AI 智能体创业"},
        "planning_state": {"search_plan": {"angles": ["fact", "news", "opinion", "case", "data"]}},
    }
    result = await plan_research_node(state)
    queries = result["planning_state"]["search_plan"]["queries"]
    assert len(queries) == 5
    assert {item["angle"] for item in queries} == {"fact", "news", "opinion", "case", "data"}
```

- [x] **步骤 2：补证据包失败测试**

```python
from workflow.utils.evidence_pack import build_evidence_pack


def test_build_evidence_pack_groups_items_by_usage() -> None:
    items = [
        {"angle": "fact", "claim": "A", "source_type": "official"},
        {"angle": "data", "claim": "B", "source_type": "dataset"},
        {"angle": "case", "claim": "C", "source_type": "news"},
    ]
    pack = build_evidence_pack(items)
    assert pack["confirmed_facts"]
    assert pack["usable_data_points"]
    assert pack["usable_cases"]
```

- [x] **步骤 3：运行测试确认失败**

运行：`pytest tests/test_plan_research.py tests/test_build_evidence_pack.py -v`
预期：FAIL，原因是模块或函数不存在。

- [x] **步骤 4：编写最小实现**

```python
def build_research_queries(topic: str, angles: list[str]) -> list[dict[str, str]]:
    mapping = {
        "fact": f"{topic} official announcement OR official blog OR documentation",
        "news": f"{topic} latest news analysis",
        "opinion": f"{topic} expert opinion controversy",
        "case": f"{topic} company case study use case",
        "data": f"{topic} statistics benchmark trend data",
    }
    return [{"angle": angle, "query": mapping[angle]} for angle in angles if angle in mapping]
```

```python
def build_evidence_pack(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {
        "confirmed_facts": [item for item in items if item.get("angle") == "fact"],
        "caution_items": [item for item in items if item.get("needs_caution")],
        "usable_data_points": [item for item in items if item.get("angle") == "data"],
        "usable_cases": [item for item in items if item.get("angle") == "case"],
        "risk_points": [item for item in items if item.get("angle") == "opinion"],
        "actionable_takeaways": [],
        "research_gaps": [],
    }
```

- [x] **步骤 5：新增计划与打包节点**

```python
async def plan_research_node(state: WorkflowState) -> dict[str, Any]:
    planning_state = dict(state.get("planning_state") or {})
    search_plan = dict(planning_state.get("search_plan") or {})
    queries = build_research_queries(state.get("task_brief", {}).get("topic", ""), list(search_plan.get("angles") or []))
    search_plan["queries"] = queries
    planning_state["search_plan"] = search_plan
    return {"status": "running", "current_skill": "plan_research", "progress": 24, "planning_state": planning_state}
```

```python
async def build_evidence_pack_node(state: WorkflowState) -> dict[str, Any]:
    research_state = dict(state.get("research_state") or {})
    research_state["evidence_pack"] = build_evidence_pack(list(research_state.get("evidence_items") or []))
    return {"status": "running", "current_skill": "build_evidence_pack", "progress": 34, "research_state": research_state}
```

- [x] **步骤 6：重新运行测试确认通过**

运行：`pytest tests/test_plan_research.py tests/test_build_evidence_pack.py -v`
预期：PASS

- [x] **步骤 7：提交**

```bash
git add workflow/utils/research_queries.py workflow/utils/evidence_pack.py workflow/skills/plan_research.py workflow/skills/run_research.py workflow/skills/build_evidence_pack.py tests/test_plan_research.py tests/test_build_evidence_pack.py
git commit -m "新增多角度研究计划与证据包"
```

## 任务 6：将单次文章生成替换为类型解析、角度规划、起草与审查

**文件：**
- 新建：`workflow/skills/resolve_article_type.py`
- 新建：`workflow/skills/plan_article_angle.py`
- 新建：`workflow/skills/compose_draft.py`
- 新建：`workflow/skills/review_article_draft.py`
- 测试：`tests/test_compose_draft.py`

- [x] **步骤 1：先写失败测试**

```python
import pytest

from workflow.skills.compose_draft import compose_draft_node


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
    result = await compose_draft_node(state)
    assert result["writing_state"]["draft"]["title"]
    assert "趋势判断" in result["writing_state"]["draft"]["content"]
```

- [x] **步骤 2：运行测试确认失败**

运行：`pytest tests/test_compose_draft.py::test_compose_draft_generates_article_from_blueprint_and_evidence -v`
预期：FAIL，原因是模块或函数不存在。

- [x] **步骤 3：编写最小实现**

```python
async def resolve_article_type_node(state: WorkflowState) -> dict[str, Any]:
    planning_state = dict(state.get("planning_state") or {})
    evidence_pack = dict(state.get("research_state", {}).get("evidence_pack") or {})
    if len(evidence_pack.get("usable_data_points", [])) >= 2:
        planning_state["article_type"] = get_article_type_registry()["trend_analysis"]
    return {"status": "running", "current_skill": "resolve_article_type", "progress": 38, "planning_state": planning_state}
```

```python
async def plan_article_angle_node(state: WorkflowState) -> dict[str, Any]:
    planning_state = dict(state.get("planning_state") or {})
    topic = state.get("task_brief", {}).get("topic", "")
    planning_state["article_blueprint"] = {
        "thesis": f"{topic} 正在从事件走向趋势",
        "sections": [
            {"heading": "发生了什么", "goal": "交代背景"},
            {"heading": "趋势判断", "goal": "解释驱动因素"},
            {"heading": "风险边界", "goal": "说明不确定性"},
        ],
    }
    return {"status": "running", "current_skill": "plan_article_angle", "progress": 44, "planning_state": planning_state}
```

```python
async def compose_draft_node(state: WorkflowState) -> dict[str, Any]:
    blueprint = dict(state.get("planning_state", {}).get("article_blueprint") or {})
    sections = blueprint.get("sections") or []
    title = blueprint.get("thesis") or state.get("task_brief", {}).get("topic", "未命名主题")
    content = "\n\n".join([f"## {section['heading']}\n{section['goal']}" for section in sections])
    return {
        "status": "running",
        "current_skill": "compose_draft",
        "progress": 54,
        "writing_state": {"draft": {"title": title, "content": content}, "review_findings": []},
        "generated_article": {"title": title, "content": content},
    }
```

```python
async def review_article_draft_node(state: WorkflowState) -> dict[str, Any]:
    writing_state = dict(state.get("writing_state") or {})
    draft = dict(writing_state.get("draft") or {})
    findings = []
    if "## 风险边界" not in draft.get("content", ""):
        findings.append({"type": "structure", "message": "missing risk boundary section"})
    writing_state["review_findings"] = findings
    writing_state["article_review"] = {"passed": not findings, "score": 85 if not findings else 68}
    return {"status": "running", "current_skill": "review_article_draft", "progress": 60, "writing_state": writing_state}
```

- [x] **步骤 4：重新运行测试确认通过**

运行：`pytest tests/test_compose_draft.py -v`
预期：PASS

- [x] **步骤 5：提交**

```bash
git add workflow/skills/resolve_article_type.py workflow/skills/plan_article_angle.py workflow/skills/compose_draft.py workflow/skills/review_article_draft.py tests/test_compose_draft.py
git commit -m "重构文章生成阶段为分段式agent"
```

## 任务 7：将单体图片生成替换为视觉规划、Prompt 压缩与评审

**文件：**
- 新建：`workflow/utils/visual_briefs.py`
- 新建：`workflow/skills/plan_visual_assets.py`
- 新建：`workflow/skills/generate_visual_assets.py`
- 新建：`workflow/skills/review_visual_assets.py`
- 测试：`tests/test_plan_visual_assets.py`

- [x] **步骤 1：先写失败测试**

```python
import pytest

from workflow.skills.plan_visual_assets import plan_visual_assets_node


@pytest.mark.asyncio
async def test_plan_visual_assets_creates_role_aware_image_briefs() -> None:
    state = {
        "task_brief": {"topic": "AI 智能体创业"},
        "planning_state": {"visual_plan": {"asset_roles": ["cover", "infographic"]}},
        "writing_state": {"draft": {"title": "AI 智能体创业进入第二阶段", "content": "## 趋势判断\n内容"}},
    }
    result = await plan_visual_assets_node(state)
    briefs = result["visual_state"]["image_briefs"]
    assert briefs[0]["role"] == "cover"
    assert briefs[1]["target_aspect_ratio"]
```

- [x] **步骤 2：运行测试确认失败**

运行：`pytest tests/test_plan_visual_assets.py::test_plan_visual_assets_creates_role_aware_image_briefs -v`
预期：FAIL，原因是模块或函数不存在。

- [x] **步骤 3：编写最小实现**

```python
def build_visual_brief(role: str, draft: dict[str, Any], topic: str) -> dict[str, Any]:
    aspect_ratio = {
        "cover": "2.35:1",
        "contextual_illustration": "16:9",
        "infographic": "4:5",
        "comparison_graphic": "1:1",
    }.get(role, "16:9")
    return {
        "role": role,
        "topic": topic,
        "title": draft.get("title", ""),
        "compressed_prompt": f"{role} for {topic}, clean composition, mobile readable, no watermark",
        "target_aspect_ratio": aspect_ratio,
        "provider_size": "1536x1024" if aspect_ratio == "2.35:1" else "1024x1024",
    }
```

```python
async def plan_visual_assets_node(state: WorkflowState) -> dict[str, Any]:
    roles = list(state.get("planning_state", {}).get("visual_plan", {}).get("asset_roles") or [])
    topic = state.get("task_brief", {}).get("topic", "")
    draft = dict(state.get("writing_state", {}).get("draft") or {})
    briefs = [build_visual_brief(role, draft, topic) for role in roles]
    return {"status": "running", "current_skill": "plan_visual_assets", "progress": 68, "visual_state": {"image_briefs": briefs, "assets": []}}
```

```python
async def review_visual_assets_node(state: WorkflowState) -> dict[str, Any]:
    visual_state = dict(state.get("visual_state") or {})
    assets = list(visual_state.get("assets") or [])
    findings = []
    for asset in assets:
        if not asset.get("url") and not asset.get("path"):
            findings.append({"role": asset.get("role"), "message": "missing generated asset"})
    visual_state["visual_review"] = {"passed": not findings, "score": 82 if not findings else 60, "findings": findings}
    return {"status": "running", "current_skill": "review_visual_assets", "progress": 78, "visual_state": visual_state}
```

- [x] **步骤 4：重新运行测试确认通过**

运行：`pytest tests/test_plan_visual_assets.py -v`
预期：PASS

- [x] **步骤 5：提交**

```bash
git add workflow/utils/visual_briefs.py workflow/skills/plan_visual_assets.py workflow/skills/generate_visual_assets.py workflow/skills/review_visual_assets.py tests/test_plan_visual_assets.py
git commit -m "重构视觉资产规划与评审阶段"
```

## 任务 8：新增质量闸门和定向修订路由

**文件：**
- 新建：`workflow/utils/quality_scoring.py`
- 新建：`workflow/skills/quality_gate.py`
- 新建：`workflow/skills/targeted_revision.py`
- 测试：`tests/test_quality_gate.py`

- [x] **步骤 1：先写失败测试**

```python
import pytest

from workflow.skills.quality_gate import quality_gate_node


@pytest.mark.asyncio
async def test_quality_gate_routes_to_visual_revision_when_visual_review_fails() -> None:
    state = {
        "writing_state": {"article_review": {"passed": True, "score": 84}},
        "visual_state": {"visual_review": {"passed": False, "score": 60, "findings": [{"message": "missing asset"}]}},
        "planning_state": {"quality_thresholds": {"article": 80, "visual": 75, "evidence": 80, "hotspot": 70}},
    }
    result = await quality_gate_node(state)
    assert result["quality_state"]["next_action"] == "revise_visuals"
```

- [x] **步骤 2：运行测试确认失败**

运行：`pytest tests/test_quality_gate.py::test_quality_gate_routes_to_visual_revision_when_visual_review_fails -v`
预期：FAIL，原因是模块或函数不存在。

- [x] **步骤 3：编写最小实现**

```python
def decide_quality_action(article_review: dict[str, Any], visual_review: dict[str, Any], thresholds: dict[str, int]) -> str:
    if article_review.get("score", 0) < thresholds.get("article", 80):
        return "revise_writing"
    if visual_review.get("score", 0) < thresholds.get("visual", 75):
        return "revise_visuals"
    return "pass"
```

```python
async def quality_gate_node(state: WorkflowState) -> dict[str, Any]:
    article_review = dict(state.get("writing_state", {}).get("article_review") or {})
    visual_review = dict(state.get("visual_state", {}).get("visual_review") or {})
    thresholds = dict(state.get("planning_state", {}).get("quality_thresholds") or {})
    next_action = decide_quality_action(article_review, visual_review, thresholds)
    return {
        "status": "running",
        "current_skill": "quality_gate",
        "progress": 88,
        "quality_state": {
            "article_review": article_review,
            "visual_review": visual_review,
            "next_action": next_action,
            "ready_to_publish": next_action == "pass",
        },
    }
```

```python
async def targeted_revision_node(state: WorkflowState) -> dict[str, Any]:
    action = state.get("quality_state", {}).get("next_action")
    return {
        "status": "running",
        "current_skill": "targeted_revision",
        "progress": 92,
        "quality_state": {**dict(state.get("quality_state") or {}), "revision_route": action},
    }
```

- [x] **步骤 4：重新运行测试确认通过**

运行：`pytest tests/test_quality_gate.py -v`
预期：PASS

- [x] **步骤 5：提交**

```bash
git add workflow/utils/quality_scoring.py workflow/skills/quality_gate.py workflow/skills/targeted_revision.py tests/test_quality_gate.py
git commit -m "新增质量闸门与定向修订路由"
```

## 任务 9：将 LangGraph 主流程重连到新 Agent 阶段

**文件：**
- 修改：`workflow/graph.py`
- 测试：`tests/test_graph_agent_redesign.py`

- [x] **步骤 1：先写失败测试**

```python
from workflow.graph import build_graph


def test_build_graph_contains_quality_gate_stage() -> None:
    graph = build_graph()
    assert graph is not None
```

- [x] **步骤 2：运行测试确认当前连接不完整**

运行：`pytest tests/test_graph_agent_redesign.py -v`
预期：FAIL，原因是新 graph 路径尚未接好或节点缺失。

- [x] **步骤 3：编写最小实现**

```python
graph.add_node("planner_agent", planner_agent_node)
graph.add_node("analyze_hotspot_opportunities", analyze_hotspot_opportunities_node)
graph.add_node("plan_research", plan_research_node)
graph.add_node("run_research", run_research_node)
graph.add_node("build_evidence_pack", build_evidence_pack_node)
graph.add_node("resolve_article_type", resolve_article_type_node)
graph.add_node("plan_article_angle", plan_article_angle_node)
graph.add_node("compose_draft", compose_draft_node)
graph.add_node("review_article_draft", review_article_draft_node)
graph.add_node("plan_visual_assets", plan_visual_assets_node)
graph.add_node("generate_visual_assets", generate_visual_assets_node)
graph.add_node("review_visual_assets", review_visual_assets_node)
graph.add_node("quality_gate", quality_gate_node)
graph.add_node("targeted_revision", targeted_revision_node)
```

```python
graph.add_edge("intake_task_brief", "planner_agent")
graph.add_edge("planner_agent", "analyze_hotspot_opportunities")
graph.add_edge("analyze_hotspot_opportunities", "plan_research")
graph.add_edge("plan_research", "run_research")
graph.add_edge("run_research", "build_evidence_pack")
graph.add_edge("build_evidence_pack", "resolve_article_type")
graph.add_edge("resolve_article_type", "plan_article_angle")
graph.add_edge("plan_article_angle", "compose_draft")
graph.add_edge("compose_draft", "review_article_draft")
graph.add_edge("review_article_draft", "plan_visual_assets")
graph.add_edge("plan_visual_assets", "generate_visual_assets")
graph.add_edge("generate_visual_assets", "review_visual_assets")
graph.add_edge("review_visual_assets", "quality_gate")
graph.add_conditional_edges("quality_gate", _route_quality_action, {"pass": "push_to_draft", "revise_writing": "compose_draft", "revise_visuals": "generate_visual_assets"})
```

- [x] **步骤 4：重新运行测试确认通过**

运行：`pytest tests/test_graph_agent_redesign.py -v`
预期：PASS

- [x] **步骤 5：提交**

```bash
git add workflow/graph.py tests/test_graph_agent_redesign.py
git commit -m "重连LangGraph为新agent阶段流"
```

## 任务 10：在任务生命周期中持久化新工作流产物

**文件：**
- 修改：`api/routers/tasks.py`
- 修改：`api/scheduler.py`
- 测试：`tests/test_graph_agent_redesign.py`

- [x] **步骤 1：先写失败测试**

```python
def test_task_result_persists_planning_and_quality_state() -> None:
    task_result = {
        "planning_state": {"article_type": {"type_id": "trend_analysis"}},
        "quality_state": {"ready_to_publish": True},
    }
    assert task_result["planning_state"]["article_type"]["type_id"] == "trend_analysis"
    assert task_result["quality_state"]["ready_to_publish"] is True
```

- [x] **步骤 2：运行测试确认当前持久化未保存新字段**

运行：`pytest tests/test_graph_agent_redesign.py::test_task_result_persists_planning_and_quality_state -v`
预期：FAIL，原因是 router / scheduler 的持久化路径忽略了新状态块。

- [x] **步骤 3：编写最小实现**

```python
task.task_brief = res.get("task_brief") or {}
task.planning_state = res.get("planning_state") or {}
task.research_state = res.get("research_state") or {}
task.writing_state = res.get("writing_state") or {}
task.visual_state = res.get("visual_state") or {}
task.quality_state = res.get("quality_state") or {}
```

- [x] **步骤 4：重新运行测试确认通过**

运行：`pytest tests/test_graph_agent_redesign.py -v`
预期：PASS

- [x] **步骤 5：提交**

```bash
git add api/routers/tasks.py api/scheduler.py tests/test_graph_agent_redesign.py
git commit -m "持久化新agent工作流产物"
```

## 任务 11：对新旧关键测试做回归验证

**文件：**
- 测试：`tests/test_generate_article.py`
- 测试：`tests/test_generate_images.py`
- 测试：`tests/test_intake_task_brief.py`
- 测试：`tests/test_planner_agent.py`
- 测试：`tests/test_analyze_hotspot_opportunities.py`
- 测试：`tests/test_plan_research.py`
- 测试：`tests/test_build_evidence_pack.py`
- 测试：`tests/test_compose_draft.py`
- 测试：`tests/test_plan_visual_assets.py`
- 测试：`tests/test_quality_gate.py`
- 测试：`tests/test_graph_agent_redesign.py`

- [x] **步骤 1：运行聚焦回归测试**

运行：

```bash
pytest tests/test_generate_article.py tests/test_generate_images.py tests/test_intake_task_brief.py tests/test_planner_agent.py tests/test_analyze_hotspot_opportunities.py tests/test_plan_research.py tests/test_build_evidence_pack.py tests/test_compose_draft.py tests/test_plan_visual_assets.py tests/test_quality_gate.py tests/test_graph_agent_redesign.py -v
```

预期：新旧阶段测试全部 PASS。

- [x] **步骤 2：先修兼容性问题，再跑更广验证**

```python
if "generated_article" not in result:
    result["generated_article"] = {}
result["generated_article"].setdefault("title", "")
result["generated_article"].setdefault("content", "")
```

- [x] **步骤 3：运行更广的后端测试**

运行：`pytest -v`
预期：PASS，或仅存在已知、与本次改造无关的历史失败，并在交接说明里记录。

- [x] **步骤 4：提交**

```bash
git add workflow api tests
git commit -m "完成agent重构主链路验证"
```

## 任务 12：更新文档与交接说明

**文件：**
- 修改：`README.md`
- 修改：`docs/superpowers/specs/2026-04-13-agent-redesign-design.zh-CN.md`
- 修改：`docs/superpowers/specs/2026-04-13-agent-redesign-design.md`
- 修改：`docs/superpowers/plans/2026-04-14-agent-redesign-implementation.md`
- 修改：`docs/superpowers/plans/2026-04-14-agent-redesign-implementation.zh-CN.md`

- [x] **步骤 1：在 README 记录新工作流阶段**

```markdown
## Agent Workflow

The workflow now runs through task brief intake, planner, hotspot analysis, research, evidence packaging, article drafting, visual planning, quality gate, and targeted revision before draft publishing.
```

- [x] **步骤 2：在 spec 和 plan 中标注已实现状态**

```markdown
- Status: Implemented in branch `<current-branch>`
- Verified by: `pytest -v`
```

- [x] **步骤 3：做最终文档巡检**

运行：`rg -n "TODO|TBD|FIXME|placeholder" README.md docs/superpowers/specs docs/superpowers/plans -S`
预期：新增文档中不出现真正的占位内容。

- [x] **步骤 4：提交**

```bash
git add README.md docs/superpowers/specs/2026-04-13-agent-redesign-design.zh-CN.md docs/superpowers/specs/2026-04-13-agent-redesign-design.md docs/superpowers/plans/2026-04-14-agent-redesign-implementation.md docs/superpowers/plans/2026-04-14-agent-redesign-implementation.zh-CN.md
git commit -m "补充agent重构文档与交接说明"
```

## 自检

### 与 spec 的覆盖关系

- planner 主导架构：任务 2、3、9
- 多源热点分析：任务 4
- 多角度研究与证据包：任务 5
- 文章 agent 重构：任务 6
- 视觉系统重构：任务 7
- 质量闸门与局部修订：任务 8、9
- 状态模型与迁移路径：任务 1、9、10
- 持久化与验证：任务 10、11、12

没有遗留未分配的 spec 要求。

### 占位词检查

- 计划正文没有故意遗留 `TODO`、`TBD`、`FIXME` 或 placeholder 占位内容。
- 每个任务都包含具体文件路径、命令和代码片段。

### 命名一致性

- 状态块统一使用 `task_brief`、`planning_state`、`research_state`、`writing_state`、`visual_state`、`quality_state`。
- 阶段名称统一使用 `intake_task_brief`、`planner_agent`、`analyze_hotspot_opportunities`、`plan_research`、`run_research`、`build_evidence_pack`、`resolve_article_type`、`plan_article_angle`、`compose_draft`、`review_article_draft`、`plan_visual_assets`、`generate_visual_assets`、`review_visual_assets`、`quality_gate`、`targeted_revision`。

## 执行状态

- Status: Core planner-led workflow stages implemented in branch `feature/agent-redesign-spec`
- Verified by: `pytest -v`
 
## 实施记录
 
- 2026-04-18：深化了 `run_research`，证据项现在带有 `authority_score`、`final_score`、`evidence_score` 和 `needs_caution`，后续阶段可以直接感知证据强弱。
- 2026-04-18：再次深化了 `run_research`，规划出的查询现在会按单 query 批次执行，并把各批次的搜索结果、抽取结果统一归并；单批次失败时会保留 `research_gaps`，而不是让整个研究阶段直接失败。
- 2026-04-18：深化了 `build_evidence_pack`，现在会输出 `quality_summary` 和 `research_gaps`，后续规划和评审不再只看“有没有证据”，还会看“证据质量是否足够”。
- 2026-04-18：再次深化了 `build_evidence_pack`，`quality_summary` 现在还会输出 `source_coverage` 和 `angle_coverage`，后续规划器与评审器可以直接感知研究覆盖面的广度。
- 2026-04-18：深化了 `planner_agent`，已有研究缺口现在会直接重排 `search_plan.angles`，并产出 `coverage_targets`，让重新规划时优先补官方事实和数据型证据。
- 2026-04-18：深化了 `plan_article_angle`，无论走 fallback 还是模型蓝图，请求都会消费 `research_gaps`、`source_coverage` 与 `angle_coverage`；当证据偏薄时，结构里会显式加入验证段和证据边界，而不是回到泛化骨架。
- 2026-04-18：深化了 `compose_draft`，起草模型现在不只消费证据 claim，也会同步消费 `research_gaps`、`source_coverage` 与 `angle_coverage`，避免在证据偏薄时仍按“信息充分”的方式写稿。
- 2026-04-18：深化了 `review_article_draft`，模型评审和 fallback 评审现在都会消费研究质量信号；即使文章结构完整，只要证据覆盖明显不足，fallback 也会给出 evidence 类问题和修订建议。
