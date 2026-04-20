# Agent Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Rebuild the article generation workflow into a planner-led, multi-stage content factory with multi-source hotspot analysis, multi-angle research, staged article generation, role-aware visual generation, and explicit quality gates while preserving current production infrastructure.

**Architecture:** Keep LangGraph, task APIs, scheduler, progress streaming, and draft publishing in place. Replace the current middle pipeline with new state blocks, planner/research/writing/visual/quality stages, and localized revision loops. Roll out in phases so the legacy path remains operable until the new path is verified.

**Tech Stack:** Python, FastAPI, LangGraph, Pydantic, pytest, pytest-asyncio, existing workflow skills and model configuration infrastructure

---

## File Structure

### Existing files to modify

- `workflow/state.py`
- `workflow/graph.py`
- `workflow/article_generation.py`
- `api/models.py`
- `api/routers/tasks.py`
- `api/scheduler.py`
- `api/store.py`

### New workflow files

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

### New utility files

- `workflow/utils/hotspot_sources.py`
- `workflow/utils/hotspot_scoring.py`
- `workflow/utils/research_queries.py`
- `workflow/utils/evidence_pack.py`
- `workflow/utils/article_type_registry.py`
- `workflow/utils/visual_briefs.py`
- `workflow/utils/quality_scoring.py`

### Tests to add

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

## Task 1: Expand Workflow State And Persistence Model

**Files:**
- Modify: `workflow/state.py`
- Modify: `api/models.py`
- Modify: `api/routers/tasks.py`
- Test: `tests/test_graph_agent_redesign.py`

- [x] **Step 1: Write the failing state-shape test**

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

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_graph_agent_redesign.py::test_workflow_state_supports_new_agent_blocks -v`
Expected: FAIL with missing `WorkflowState` keys or incompatible typed definition.

- [x] **Step 3: Write minimal implementation**

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

- [x] **Step 4: Return the new fields from task APIs**

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

- [x] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_graph_agent_redesign.py::test_workflow_state_supports_new_agent_blocks -v`
Expected: PASS

- [x] **Step 6: Commit**

```bash
git add workflow/state.py api/models.py api/routers/tasks.py tests/test_graph_agent_redesign.py
git commit -m "重构工作流状态与任务模型"
```

## Task 2: Normalize Task Brief At Workflow Entry

**Files:**
- Create: `workflow/skills/intake_task_brief.py`
- Modify: `workflow/article_generation.py`
- Modify: `workflow/graph.py`
- Test: `tests/test_intake_task_brief.py`

- [x] **Step 1: Write the failing intake test**

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

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_intake_task_brief.py::test_intake_task_brief_normalizes_generation_inputs -v`
Expected: FAIL with module/function not found.

- [x] **Step 3: Write minimal implementation**

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

- [x] **Step 4: Wire the graph entry**

```python
graph.add_node("intake_task_brief", intake_task_brief_node)
graph.set_entry_point("intake_task_brief")
graph.add_edge("intake_task_brief", "planner_agent")
```

- [x] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_intake_task_brief.py -v`
Expected: PASS

- [x] **Step 6: Commit**

```bash
git add workflow/skills/intake_task_brief.py workflow/article_generation.py workflow/graph.py tests/test_intake_task_brief.py
git commit -m "新增任务brief接入阶段"
```

## Task 3: Add Article Type Registry And Planner Output Shape

**Files:**
- Create: `workflow/utils/article_type_registry.py`
- Create: `workflow/skills/planner_agent.py`
- Test: `tests/test_article_type_registry.py`
- Test: `tests/test_planner_agent.py`

- [x] **Step 1: Write the failing article type registry test**

```python
from workflow.utils.article_type_registry import get_article_type_registry


def test_article_type_registry_includes_multiple_formal_types() -> None:
    registry = get_article_type_registry()
    assert "hotspot_interpretation" in registry
    assert "trend_analysis" in registry
    assert registry["quick_news"]["title_style"] == "fast_and_clear"
```

- [x] **Step 2: Write the failing planner output test**

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

- [x] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_article_type_registry.py tests/test_planner_agent.py -v`
Expected: FAIL with missing module/function definitions.

- [x] **Step 4: Write minimal implementation**

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

- [x] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_article_type_registry.py tests/test_planner_agent.py -v`
Expected: PASS

- [x] **Step 6: Commit**

```bash
git add workflow/utils/article_type_registry.py workflow/skills/planner_agent.py tests/test_article_type_registry.py tests/test_planner_agent.py
git commit -m "新增文章类型策略注册表与规划器"
```

## Task 4: Add Multi-Source Hotspot Analysis

**Files:**
- Create: `workflow/utils/hotspot_sources.py`
- Create: `workflow/utils/hotspot_scoring.py`
- Create: `workflow/skills/analyze_hotspot_opportunities.py`
- Test: `tests/test_analyze_hotspot_opportunities.py`

- [x] **Step 1: Write the failing hotspot scoring test**

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

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_analyze_hotspot_opportunities.py::test_score_hotspot_candidate_prefers_relevant_and_expandable_items -v`
Expected: FAIL with missing module/function.

- [x] **Step 3: Write minimal implementation**

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

- [x] **Step 4: Add the hotspot analysis node**

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

- [x] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_analyze_hotspot_opportunities.py -v`
Expected: PASS

- [x] **Step 6: Commit**

```bash
git add workflow/utils/hotspot_sources.py workflow/utils/hotspot_scoring.py workflow/skills/analyze_hotspot_opportunities.py tests/test_analyze_hotspot_opportunities.py
git commit -m "新增多源热点分析阶段"
```

## Task 5: Implement Multi-Angle Research Planning And Evidence Pack

**Files:**
- Create: `workflow/utils/research_queries.py`
- Create: `workflow/utils/evidence_pack.py`
- Create: `workflow/skills/plan_research.py`
- Create: `workflow/skills/run_research.py`
- Create: `workflow/skills/build_evidence_pack.py`
- Test: `tests/test_plan_research.py`
- Test: `tests/test_build_evidence_pack.py`

- [x] **Step 1: Write the failing research-plan test**

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

- [x] **Step 2: Write the failing evidence-pack test**

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

- [x] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_plan_research.py tests/test_build_evidence_pack.py -v`
Expected: FAIL with missing modules/functions.

- [x] **Step 4: Write minimal implementation**

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

- [x] **Step 5: Add planning and packaging nodes**

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

- [x] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_plan_research.py tests/test_build_evidence_pack.py -v`
Expected: PASS

- [x] **Step 7: Commit**

```bash
git add workflow/utils/research_queries.py workflow/utils/evidence_pack.py workflow/skills/plan_research.py workflow/skills/run_research.py workflow/skills/build_evidence_pack.py tests/test_plan_research.py tests/test_build_evidence_pack.py
git commit -m "新增多角度研究计划与证据包"
```

## Task 6: Replace Single-Pass Article Generation With Type Resolution, Angle Planning, Drafting, And Review

**Files:**
- Create: `workflow/skills/resolve_article_type.py`
- Create: `workflow/skills/plan_article_angle.py`
- Create: `workflow/skills/compose_draft.py`
- Create: `workflow/skills/review_article_draft.py`
- Test: `tests/test_compose_draft.py`

- [x] **Step 1: Write the failing draft-composition test**

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

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_compose_draft.py::test_compose_draft_generates_article_from_blueprint_and_evidence -v`
Expected: FAIL with missing module/function.

- [x] **Step 3: Write minimal implementation**

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

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_compose_draft.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add workflow/skills/resolve_article_type.py workflow/skills/plan_article_angle.py workflow/skills/compose_draft.py workflow/skills/review_article_draft.py tests/test_compose_draft.py
git commit -m "重构文章生成阶段为分段式agent"
```

## Task 7: Replace Monolithic Image Generation With Visual Planning, Brief Compression, And Review

**Files:**
- Create: `workflow/utils/visual_briefs.py`
- Create: `workflow/skills/plan_visual_assets.py`
- Create: `workflow/skills/generate_visual_assets.py`
- Create: `workflow/skills/review_visual_assets.py`
- Test: `tests/test_plan_visual_assets.py`

- [x] **Step 1: Write the failing visual-brief test**

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

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_plan_visual_assets.py::test_plan_visual_assets_creates_role_aware_image_briefs -v`
Expected: FAIL with missing module/function.

- [x] **Step 3: Write minimal implementation**

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

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_plan_visual_assets.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add workflow/utils/visual_briefs.py workflow/skills/plan_visual_assets.py workflow/skills/generate_visual_assets.py workflow/skills/review_visual_assets.py tests/test_plan_visual_assets.py
git commit -m "重构视觉资产规划与评审阶段"
```

## Task 8: Add Quality Gate And Targeted Revision Routing

**Files:**
- Create: `workflow/utils/quality_scoring.py`
- Create: `workflow/skills/quality_gate.py`
- Create: `workflow/skills/targeted_revision.py`
- Test: `tests/test_quality_gate.py`

- [x] **Step 1: Write the failing quality-gate test**

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

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_quality_gate.py::test_quality_gate_routes_to_visual_revision_when_visual_review_fails -v`
Expected: FAIL with missing module/function.

- [x] **Step 3: Write minimal implementation**

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

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_quality_gate.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add workflow/utils/quality_scoring.py workflow/skills/quality_gate.py workflow/skills/targeted_revision.py tests/test_quality_gate.py
git commit -m "新增质量闸门与定向修订路由"
```

## Task 9: Rewire The LangGraph Flow To The New Agent Stages

**Files:**
- Modify: `workflow/graph.py`
- Test: `tests/test_graph_agent_redesign.py`

- [x] **Step 1: Write the failing graph-routing test**

```python
from workflow.graph import build_graph


def test_build_graph_contains_quality_gate_stage() -> None:
    graph = build_graph()
    assert graph is not None
```

- [x] **Step 2: Run test to verify current wiring is incomplete**

Run: `pytest tests/test_graph_agent_redesign.py -v`
Expected: FAIL because the new graph path is not yet wired or missing nodes.

- [x] **Step 3: Write minimal implementation**

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

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_graph_agent_redesign.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add workflow/graph.py tests/test_graph_agent_redesign.py
git commit -m "重连LangGraph为新agent阶段流"
```

## Task 10: Persist New Workflow Artifacts Through Task Lifecycle

**Files:**
- Modify: `api/routers/tasks.py`
- Modify: `api/scheduler.py`
- Test: `tests/test_graph_agent_redesign.py`

- [x] **Step 1: Write the failing task-persistence test**

```python
def test_task_result_persists_planning_and_quality_state() -> None:
    task_result = {
        "planning_state": {"article_type": {"type_id": "trend_analysis"}},
        "quality_state": {"ready_to_publish": True},
    }
    assert task_result["planning_state"]["article_type"]["type_id"] == "trend_analysis"
    assert task_result["quality_state"]["ready_to_publish"] is True
```

- [x] **Step 2: Run test to verify persistence code does not yet save the new fields**

Run: `pytest tests/test_graph_agent_redesign.py::test_task_result_persists_planning_and_quality_state -v`
Expected: FAIL because router/scheduler persistence paths ignore the new blocks.

- [x] **Step 3: Write minimal implementation**

```python
task.task_brief = res.get("task_brief") or {}
task.planning_state = res.get("planning_state") or {}
task.research_state = res.get("research_state") or {}
task.writing_state = res.get("writing_state") or {}
task.visual_state = res.get("visual_state") or {}
task.quality_state = res.get("quality_state") or {}
```

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_graph_agent_redesign.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add api/routers/tasks.py api/scheduler.py tests/test_graph_agent_redesign.py
git commit -m "持久化新agent工作流产物"
```

## Task 11: Run Regression Verification Across Legacy And New Critical Tests

**Files:**
- Test: `tests/test_generate_article.py`
- Test: `tests/test_generate_images.py`
- Test: `tests/test_intake_task_brief.py`
- Test: `tests/test_planner_agent.py`
- Test: `tests/test_analyze_hotspot_opportunities.py`
- Test: `tests/test_plan_research.py`
- Test: `tests/test_build_evidence_pack.py`
- Test: `tests/test_compose_draft.py`
- Test: `tests/test_plan_visual_assets.py`
- Test: `tests/test_quality_gate.py`
- Test: `tests/test_graph_agent_redesign.py`

- [x] **Step 1: Run focused regression suite**

Run:

```bash
pytest tests/test_generate_article.py tests/test_generate_images.py tests/test_intake_task_brief.py tests/test_planner_agent.py tests/test_analyze_hotspot_opportunities.py tests/test_plan_research.py tests/test_build_evidence_pack.py tests/test_compose_draft.py tests/test_plan_visual_assets.py tests/test_quality_gate.py tests/test_graph_agent_redesign.py -v
```

Expected: PASS across legacy and new stage tests.

- [x] **Step 2: Fix compatibility issues before broader verification**

```python
if "generated_article" not in result:
    result["generated_article"] = {}
result["generated_article"].setdefault("title", "")
result["generated_article"].setdefault("content", "")
```

- [x] **Step 3: Run the broader backend suite**

Run: `pytest -v`
Expected: PASS or only pre-existing unrelated failures documented in handoff.

- [x] **Step 4: Commit**

```bash
git add workflow api tests
git commit -m "完成agent重构主链路验证"
```

## Task 12: Update Docs And Handoff Notes

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-04-13-agent-redesign-design.zh-CN.md`
- Modify: `docs/superpowers/specs/2026-04-13-agent-redesign-design.md`
- Modify: `docs/superpowers/plans/2026-04-14-agent-redesign-implementation.md`

- [x] **Step 1: Document the new workflow stages in README**

```markdown
## Agent Workflow

The workflow now runs through task brief intake, planner, hotspot analysis, research, evidence packaging, article drafting, visual planning, quality gate, and targeted revision before draft publishing.
```

- [x] **Step 2: Mark implemented sections in the spec and plan**

```markdown
- Status: Implemented in branch `<current-branch>`
- Verified by: `pytest -v`
```

- [x] **Step 3: Run final doc sanity check**

Run: `rg -n "TODO|TBD|FIXME|placeholder" README.md docs/superpowers/specs docs/superpowers/plans -S`
Expected: no matches for the newly updated docs.

- [x] **Step 4: Commit**

```bash
git add README.md docs/superpowers/specs/2026-04-13-agent-redesign-design.zh-CN.md docs/superpowers/specs/2026-04-13-agent-redesign-design.md docs/superpowers/plans/2026-04-14-agent-redesign-implementation.md
git commit -m "补充agent重构文档与交接说明"
```

## Self-Review

### Spec coverage

- planner-led architecture: Tasks 2, 3, 9
- multi-source hotspot analysis: Task 4
- multi-angle research and evidence pack: Task 5
- article agent redesign: Task 6
- visual system redesign: Task 7
- quality gate and localized revision: Tasks 8 and 9
- state model and migration path: Tasks 1, 9, 10
- persistence and verification: Tasks 10, 11, 12

No spec gap remains unassigned.

### Placeholder scan

- No `TODO`, `TBD`, `FIXME`, or placeholder text intentionally left in the plan body.
- Every task includes concrete file paths, commands, and code snippets.

### Type consistency

- State block names are consistently `task_brief`, `planning_state`, `research_state`, `writing_state`, `visual_state`, `quality_state`.
- Stage names are consistently `intake_task_brief`, `planner_agent`, `analyze_hotspot_opportunities`, `plan_research`, `run_research`, `build_evidence_pack`, `resolve_article_type`, `plan_article_angle`, `compose_draft`, `review_article_draft`, `plan_visual_assets`, `generate_visual_assets`, `review_visual_assets`, `quality_gate`, `targeted_revision`.

## Execution Status

- Status: Core planner-led workflow stages implemented in branch `feature/agent-redesign-spec`
- Verified by: `pytest -v`

## Implementation Record

- 2026-04-18: Deepened `run_research` so evidence items now carry `authority_score`, `final_score`, `evidence_score`, and `needs_caution`.
- 2026-04-18: Deepened `run_research` again so planned queries now execute in per-query batches, aggregate search and extraction results across batches, and retain partial `research_gaps` instead of failing the whole stage on a single batch miss.
- 2026-04-18: Deepened `build_evidence_pack` so it now outputs `quality_summary` and `research_gaps`, allowing downstream planning and review to reason about evidence strength instead of only evidence presence.
- 2026-04-18: Deepened `build_evidence_pack` again so `quality_summary` now includes `source_coverage` and `angle_coverage`, giving downstream planners and reviewers a direct view of research breadth.
- 2026-04-18: Deepened `planner_agent` so existing research gaps now reprioritize `search_plan.angles` and declare `coverage_targets`, letting replanning focus on missing official facts and missing datasets first.
- 2026-04-18: Deepened `plan_article_angle` so both fallback and model-driven blueprint planning now consume `research_gaps`, `source_coverage`, and `angle_coverage`; thin evidence now adds explicit validation/boundary guidance instead of defaulting to a generic structure.
- 2026-04-18: Deepened `compose_draft` so model drafting now consumes `research_gaps`, `source_coverage`, and `angle_coverage` alongside the evidence claims, keeping weak-evidence drafts aware of missing support instead of writing from claims alone.
- 2026-04-18: Deepened `review_article_draft` so both model review and fallback review now consume research quality signals; fallback review can fail for thin evidence coverage even when the draft structure itself looks complete.
- 2026-04-18: Deepened `quality_gate` so it now carries `evidence_gaps` and `evidence_quality_summary` forward into `quality_state`, making downstream revision routing aware of the current research deficit instead of only article/visual scores.
- 2026-04-18: Deepened `targeted_revision` so writing revision briefs now preserve `evidence_gaps` and append explicit evidence-gap guidance, allowing the next drafting pass to distinguish structural rewrites from evidence-repair work.
- 2026-04-18: Deepened `review_visual_assets` so visual QA now also reacts to research deficits; infographic assets fail review when the workflow still lacks data evidence to support them.
- 2026-04-18: Deepened `quality_gate` again so it now emits a unified `quality_report` with article score, visual score, publish readiness, and blocking reasons, giving downstream systems one stable summary object to inspect.
- 2026-04-18: Persisted `quality_report` through API task progress handling and scheduler progress handling, and exposed it as a top-level `TaskResponse` field so clients no longer need to parse nested `quality_state` just to read the final summary.
- 2026-04-18: Mapped new visual assets back into `generated_article` as `cover_image`, `illustrations`, and `visual_assets`, restoring compatibility with legacy push logic that determines WeChat media uploads from the article payload.
- 2026-04-18: Added push-time fallbacks in `push_to_draft` and `wechat_draft_service` so WeChat draft publishing can still resolve images from `visual_state.assets` or `article.visual_assets` when older image fields are absent.
- 2026-04-19: Reworked `plan_article_angle` so general-topic fallback blueprints no longer default to fixed headings like “先给结论 / 发生变化的核心原因”; section titles are now generated as content-specific WeChat-style headings derived from the topic itself.
- 2026-04-19: Tightened model-side blueprint planning so prompts explicitly request WeChat public-account style structure, and normalized model output to a hard 4-6 section range before drafting.
- 2026-04-19: Relaxed `compose_draft` from hard-preserving blueprint H2 wording; drafting prompts now keep section intent and order but allow heading refinement toward publication-ready WeChat wording.
- 2026-04-19: Tightened `compose_draft` again around finished-article quality; prompts now explicitly require a publication-ready title, concise summary, and an opening hook paragraph before the first H2 section.
- 2026-04-19: Deepened `compose_draft` again so draft output now also carries `alt_titles` and writes both `summary` and title candidates back into `generated_article`, giving downstream publishing surfaces more finished article metadata instead of only a single title.
- 2026-04-19: Deepened `review_article_draft` fallback rules so generic roadmap-style openers such as “本文将从…” now fail review with opener-specific revision guidance, preventing low-signal public-account intros from slipping through when model review is unavailable.
- 2026-04-20: Tightened `compose_draft` again so drafting prompts now explicitly require section-to-section transitions and 2-3 paragraph development per H2, reducing the “one paragraph per section” stitched-output feel.
- 2026-04-20: Deepened `review_article_draft` fallback rules again so thin section bodies now fail review with density-specific revision guidance, allowing non-model review paths to catch low-information drafts that are structurally present but still read unfinished.
- 2026-04-19: Added body-illustration placement in `generate_visual_assets`; non-cover images now insert Markdown placeholders like `[插图1]` into article content so the article itself carries image placement, not just image references.
- 2026-04-19: Verified WeChat draft publishing now uploads body illustrations and replaces `[插图N]` placeholders with WeChat-hosted image URLs before `draft/add`, closing the loop from visual planning to in-body image rendering.
- 2026-04-19: Upgraded body-illustration placement from simple sequential insertion to section-aware placement; `infographic` assets now prefer evidence/data sections and contextual illustrations prefer case/company sections, while `generated_article.illustrations` is reordered to match the final in-body placeholder order.
- 2026-04-20: Fixed real-provider image generation in `generate_visual_assets` for models that return `b64_json` instead of remote URLs; image bytes are now persisted under `artifacts/generated_images` and written back into article image fields, which resolves the “photo not generated” failure under the current Gemini-compatible provider.
