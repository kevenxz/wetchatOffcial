# 2026-04-24 流程优化落地记录

## 背景

本次实现基于 `docs/xitong.md` 的整体方向，目标是把现有系统从“多条链路并存”收敛为一条可配置、可追踪、可审核、可进入公众号草稿箱的内容生产主链路。

优化后的主链路：

```text
热点捕获/透传主题
  -> 任务简报
  -> 流程规划
  -> 选题评估
  -> 研究规划
  -> 资料研究
  -> 证据包
  -> 文章角度
  -> 写作成稿
  -> 文章审核
  -> 图片规划
  -> 图片生成
  -> 图片审核
  -> 质量门禁
  -> 草稿箱推送或调度器统一推送
```

## 后端改动

- `workflow/graph.py`
  - 将 `capture_hot_topics` 接入 LangGraph 主入口。
  - 当前主链路改为新版 planner/research/writer/reviewer/visual/quality 节点。
  - 移除旧链路在主执行图中的连接，避免 `interpret_user_intent/build_article_blueprint/generate_article/generate_images` 与新版链路并行维护。
  - `skip_auto_push=True` 时，质量门禁通过后进入 `ui_feedback`，由 scheduler 统一处理账号和主题推送。
  - 最终回调结果补齐 `task_brief/planning_state/research_state/writing_state/visual_state/quality_state/quality_report/human_review_required`。

- `workflow/skills/intake_task_brief.py`
  - 任务简报中加入热点上下文：`selected_hotspot`、候选数量、抓取错误、是否使用回退。

- `workflow/skills/analyze_hotspot_opportunities.py`
  - 优先消费 `capture_hot_topics` 产出的真实候选。
  - 热点启用但无候选时不再生成占位热点。
  - 手动任务关闭热点时保留轻量手动主题候选，兼容后续研究链路。

- `api/models.py`
  - `CreateTaskRequest` 增加 `hotspot_capture_config`。
  - `TaskResponse` 增加 `hotspot_capture_error` 和 `human_review_required`。
  - 新增 `HotspotPreviewRequest` 与 `HotspotPreviewResponse`。

- `api/routers/hotspots.py`
  - 新增 `POST /api/hotspots/preview`。
  - 该接口只抓取和打分热点，不创建任务、不生成文章、不推送草稿箱。

- `api/workflow_sync.py`
  - 新增工作流结果同步 helper。
  - `api/routers/tasks.py` 与 `api/scheduler.py` 复用同一套落盘逻辑，避免字段不一致。

- `api/routers/tasks.py`
  - 手动创建任务时支持传入热点捕获配置。
  - 任务完成或失败时统一保存完整中间状态和质量报告。

- `api/scheduler.py`
  - 调度任务继续使用 `skip_auto_push=True`。
  - 工作流只负责生成内容，账号、主题样式和多账号推送由 scheduler 统一处理。

## 前端改动

- `frontend/src/api/index.ts`
  - 补齐任务、热点预览、质量报告和中间状态相关类型。
  - 新增 `previewHotspots` API 方法。

- `frontend/src/pages/TaskCreate.tsx`
  - 手动任务新增“本次任务启用热点捕获”开关。
  - 支持配置热点分类、最低命中分、每个平台抓取数量、偏好关键词、排除关键词。
  - 默认关闭热点捕获，保持原手动主题创建体验。

- `frontend/src/pages/ScheduleManage.tsx`
  - 热点分类改为中文业务标签展示，提交仍使用内部值。
  - 新增“预览热点命中”按钮，用于验证当前热点配置是否能抓到候选。

- `frontend/src/pages/TaskDetail.tsx`
  - 执行轨迹切换为新版主链路节点。
  - 展示热点候选、最终选题、质量报告、任务简报、研究状态和写作审核信息。
  - 任务完成但需要人工复核时，结果区显示 warning 状态。

- `frontend/src/components/workbench/WorkbenchShell.*`
  - 对齐主题变量测试：CSS 规则保留 `--app-bg-gradient`，运行时保持当前轻量布局的 `backgroundImage: none`。
  - 品牌卡片和激活导航使用 `--app-surface-strong` 语义变量。

## 接口变化

### 创建任务

```http
POST /api/tasks
```

新增可选字段：

```json
{
  "keywords": "人工智能 最新进展",
  "generation_config": {
    "audience_roles": ["泛科技读者"],
    "article_strategy": "auto",
    "style_hint": ""
  },
  "hotspot_capture_config": {
    "enabled": true,
    "source": "tophub",
    "categories": ["ai", "tech"],
    "platforms": [],
    "filters": {
      "top_n_per_platform": 10,
      "min_selection_score": 60,
      "exclude_keywords": [],
      "prefer_keywords": []
    },
    "fallback_topics": ["人工智能 最新进展"]
  }
}
```

`hotspot_capture_config` 为空或未传时，任务按手动主题直接执行。

### 热点预览

```http
POST /api/hotspots/preview
```

请求：

```json
{
  "keywords": "热点预览",
  "hotspot_capture": {
    "enabled": true,
    "source": "tophub",
    "categories": ["ai"],
    "platforms": [],
    "filters": {
      "top_n_per_platform": 10,
      "min_selection_score": 60,
      "exclude_keywords": [],
      "prefer_keywords": []
    },
    "fallback_topics": ["人工智能"]
  }
}
```

响应包含：

- `keywords`：最终命中的主题或回退主题。
- `hotspot_candidates`：候选池。
- `selected_hotspot`：最终选中热点。
- `hotspot_capture_error`：抓取失败或回退原因。

## 验证结果

已执行：

```bash
python -m compileall api workflow
pytest -q
pytest tests\test_graph_agent_redesign.py tests\test_scheduler_hotspot_capture.py tests\test_quality_gate.py -q
cd frontend
npm test -- --run
npm run build
```

结果：

- 后端全量测试：`120 passed`
- 前端测试：`44 passed, 1 skipped`
- 前端构建：通过
- Python 编译检查：通过

前端测试仍输出既有警告：

- React Router v7 future flag warning。
- AntD `destroyOnClose` deprecated warning。
- jsdom 对部分 `window.getComputedStyle(elt, pseudoElt)` 未实现的警告。

这些警告未导致测试失败。

## 注意事项

- `docs/xitong.md` 未在本次实现中修改。
- `docs/xitong.md` 当前终端读取存在编码乱码，后续如需继续维护，建议先统一文件编码为 UTF-8。
- 当前热点来源仍以 TopHub 为 MVP 来源，后续可按相同接口扩展 RSS、新闻源、社交趋势源。
- 质量门禁失败或标记 `human_review_required=true` 时，不应直接自动公开发布。
