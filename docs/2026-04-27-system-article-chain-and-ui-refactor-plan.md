# 2026-04-27 文章链路与后台系统重构细化方案

## 0. 文档目标

本方案基于 `docs/xitong.md`、当前仓库实现，以及 Figma 原型链接：

`https://www.figma.com/make/FCrUYwAbP0RszBiGCCBZ6N/后台系统页面设计?t=xSeUZh6lWC0fRLnU-1`

目标是把系统继续收敛为一套 **Workflow/Harness 主导、多 Agent 协作、可配置、可审核、可发布到公众号草稿箱** 的内容生产后台。

需要重点解决两件事：

1. 文章生成链路变更：拆成多 Agent、多节点、小闭环，去掉旧版“单节点写完整文章”的残留。
2. 系统模块和前端页面变更：按后台原型重新整理导航、页面、组件、接口和数据状态。

说明：当前无法直接读取 Figma 画布内容，因此本文先按后台系统原型的典型信息架构和现有页面能力做落地拆分。正式开发前需要从 Figma 导出页面截图、组件标注、颜色/间距/字号规范，补进“视觉验收标准”。

---

## 1. 当前系统现状判断

### 1.1 已经完成的基础

当前主链路已经接近 `docs/xitong.md` 的目标架构：

```text
capture_hot_topics
  -> intake_task_brief
  -> planner_agent
  -> analyze_hotspot_opportunities
  -> plan_research
  -> run_research
  -> build_evidence_pack
  -> resolve_article_type
  -> outline_planner
  -> compose_draft
  -> review_article_draft
  -> plan_visual_assets
  -> image_agent
  -> review_visual_assets
  -> quality_gate
  -> targeted_revision | assemble_article
  -> push_to_draft | ui_feedback
```

后端已有：

- `workflow/config.py`：生成 `config_snapshot`。
- `workflow/state.py`：保存共享状态。
- `workflow/skills/*`：当前拆分后的 Agent/节点，后续需要按职责重命名和重新分类。
- `api/models.py`：任务、热点、排期、账号、发布等模型。
- `frontend/src/pages/*`：已有创作台、任务详情、历史、文章库、排期、配置、账号、用户等页面。

### 1.2 当前主要问题

1. 新旧链路共存，旧模块仍散落在 `workflow/skills`、`tests`、`docs` 中。
2. 前端页面仍以“任务创建/任务详情”为中心，没有形成“内容生产控制台”的完整操作闭环。
3. 文章链路的 Agent 边界还需要再清晰：Planner、Outline、Writer、Reviewer、Image、Publisher 的输入输出要稳定。
4. 人工审核、候选选题池、质量报告、发布决策还没有成为独立的一等页面模块。
5. 配置项已经进入任务表单，但缺少可复用的“账号定位 / 模板 / 审核策略 / 图片风格 / 发布策略”预设管理。

---

## 2. 总体目标架构

### 2.1 架构范式

采用：

```text
Workflow/Harness 编排
  + Shared State 共享状态
  + Specialist Agents 专职 Agent
  + Tool Nodes 工具节点
  + Quality Gate 质量门禁
  + Human Review 人工兜底
```

原则：

- Workflow 决定顺序、分支、重试和终止。
- Agent 只负责局部智能决策。
- Tool Node 只负责确定性工具调用。
- 每个节点只读 `config_snapshot`，不直接读取动态配置。
- 所有节点只写自己的状态分区，减少互相覆盖。

### 2.2 新系统模块图

```text
后台前端
  ├─ 工作台总览
  ├─ 选题中心
  ├─ 创作任务
  ├─ 审核中心
  ├─ 文章库
  ├─ 发布中心
  ├─ 自动化排期
  └─ 系统配置

API 层
  ├─ tasks
  ├─ topics
  ├─ hotspots
  ├─ articles
  ├─ reviews
  ├─ schedules
  ├─ accounts
  └─ config

Workflow/Harness
  ├─ 热点链路
  ├─ 选题链路
  ├─ 研究链路
  ├─ 写作链路
  ├─ 图片链路
  ├─ 审核链路
  └─ 发布链路

基础服务
  ├─ 热点源适配器
  ├─ 搜索与抽取
  ├─ 模型调用
  ├─ 图片生成
  ├─ 微信草稿箱
  ├─ 存储
  └─ WebSocket 进度推送
```

---

## 3. 文章生成链路变更方案

### 3.1 链路拆分总览

新文章链路拆成 9 个小阶段：

```text
01 任务触发
02 热点捕获
03 选题决策
04 研究检索
05 证据包构建
06 提纲规划
07 正文写作
08 图片规划与生成
09 审核、修订、组装、入草稿箱
```

手动任务和自动热点任务只在前两步不同，后续共用同一套内容生产链路。

---

## 4. 多 Agent 拆分

### 4.1 Orchestrator / Harness

定位：流程控制器，不写文章。

职责：

- 初始化 `config_snapshot`。
- 控制节点顺序。
- 根据 `quality_gate.next_action` 决定继续、改写、人工复核或发布。
- 记录每个节点的进度、耗时、失败原因。

对应模块：

- `workflow/graph.py`
- `workflow/state.py`
- `workflow/config.py`

验收：

- 每个任务都有完整 `config_snapshot`。
- 每个节点输出可在任务详情页追踪。
- 失败节点能被定位到具体阶段。

### 4.2 Hotspot Agent / 热点捕获与聚合

定位：把外部热点变成候选事件，不直接写文章。

拆分小点：

1. Source Adapter：抓取 TopHub、RSS、新闻源、搜索趋势。
2. Cleaner：清洗广告、空标题、重复链接。
3. Clusterer：相似标题与关键词聚类。
4. Scorer：热度、时效、多源确认、账号匹配、风险扣分。
5. Topicizer：把事件转成可写选题。

输入：

- `hotspot_capture_config`
- `config_snapshot.account_profile`
- `config_snapshot.review_policy`

输出：

- `hotspot_candidates`
- `selected_hotspot`
- `selected_topic`

保留模块：

- `workflow/skills/capture_hot_topics.py`
- `workflow/skills/analyze_hotspot_opportunities.py`
- `workflow/utils/tophub_client.py`
- `workflow/utils/hotspot_sources.py`
- `workflow/utils/hotspot_scoring.py`
- `workflow/utils/hotspot_ranker.py`

新增建议：

- `workflow/skills/cluster_hotspots.py`
- `workflow/skills/topicize_hotspot.py`
- `api/routers/topics.py`

### 4.3 Planner Agent / 内容策略规划

定位：决定“写什么、给谁看、用什么结构写”。

拆分小点：

1. 账号匹配：判断选题是否适合当前账号。
2. 文章类型选择：快讯、解读、科普、评论、盘点、复盘、趋势。
3. 写作角度：确定主论点、切入点、读者收益。
4. 检索计划：确定需要查证的问题。
5. 图片意图草案：预估封面和文内图需求。

输入：

- `task_brief`
- `selected_topic`
- `config_snapshot.account_profile`
- `config_snapshot.content_template`

输出：

- `planning_state`
- `article_type`
- `research_plan`
- `visual_plan_seed`

保留模块：

- `workflow/skills/planner_agent.py`
- `workflow/skills/resolve_article_type.py`
- `workflow/utils/article_type_registry.py`

### 4.4 Research Agent / 研究检索

定位：查资料和构建证据，不负责写作。

拆分小点：

1. Query Planner：生成检索词。
2. Search Tool：调用搜索源。
3. Extract Tool：抽取网页正文。
4. Source Ranker：可信度、相关度、时效性排序。
5. Evidence Builder：整理事实、引用、争议点、资料缺口。

输入：

- `planning_state.research_plan`
- `selected_topic`

输出：

- `research_state`
- `search_queries`
- `search_results`
- `extracted_contents`
- `evidence_pack`

保留模块：

- `workflow/skills/plan_research.py`
- `workflow/skills/run_research.py`
- `workflow/skills/search_web.py`
- `workflow/skills/fetch_extract.py`
- `workflow/skills/build_evidence_pack.py`
- `workflow/utils/research_queries.py`
- `workflow/utils/evidence_pack.py`

注意：`search_web.py` 和 `fetch_extract.py` 虽属于旧文件名，但当前被 `run_research.py` 间接调用，不能直接删除。

### 4.5 Outline Agent / 提纲规划

定位：把证据包变成可执行文章结构。

拆分小点：

1. 标题候选。
2. 章节结构。
3. 每节写作目标。
4. 每节证据映射。
5. 风险段落预警。
6. 图片插入点建议。

输入：

- `evidence_pack`
- `content_template`
- `article_type`

输出：

- `outline_result`
- `article_plan`

保留模块：

- `workflow/skills/outline_planner.py`

### 4.6 Writer Agent / 正文写作

定位：只按提纲和证据写正文，不做自由发挥。

拆分小点：

1. 标题生成。
2. 摘要生成。
3. 导语生成。
4. 分章节正文生成。
5. 结尾生成。
6. 引用与事实约束检查。

输入：

- `outline_result`
- `evidence_pack`
- `config_snapshot.account_profile`
- `config_snapshot.content_template`

输出：

- `writing_state.draft`
- `generated_article`

保留模块：

- `workflow/skills/compose_draft.py`

### 4.7 Reviewer Agent / 审核与改写

定位：审文章，不写新文章；需要改写时输出修订指令。

拆分小点：

1. 合规审核：政治、违法、医疗、金融、军事等风险。
2. 表达审核：极限词、夸张承诺、标题党。
3. 事实审核：无依据结论、引用缺失。
4. 结构审核：是否跑题、是否段落缺失。
5. 品牌审核：是否符合账号定位和语气。
6. 修订建议：定位到标题、摘要、段落、图片文案。

输入：

- `generated_article`
- `evidence_pack`
- `review_policy`

输出：

- `writing_state.review`
- `quality_state`
- `quality_report`
- `human_review_required`

保留模块：

- `workflow/skills/review_article_draft.py`
- `workflow/skills/quality_gate.py`
- `workflow/skills/targeted_revision.py`
- `workflow/utils/quality_scoring.py`

### 4.8 Image Agent / 图片规划、生成、审核

定位：图片 Agent 不是简单出图工具，而是理解文章内容的视觉生产节点。

拆分小点：

1. Image Planner：决定封面、文内图数量和位置。
2. Prompt Composer：将文章段落转成图片提示词。
3. Generator：调用图片模型。
4. Asset Mapper：把图片映射到封面和文章段落。
5. Image Reviewer：审核图片主题、合规、封面可读性。

输入：

- `generated_article`
- `outline_result`
- `visual_plan_seed`
- `config_snapshot.image_policy`

输出：

- `visual_state.briefs`
- `visual_state.assets`
- `visual_state.review`

保留模块：

- `workflow/skills/plan_visual_assets.py`
- `workflow/skills/image_agent.py`
- `workflow/skills/generate_visual_assets.py`
- `workflow/skills/review_visual_assets.py`
- `workflow/utils/visual_briefs.py`

可合并：

- `workflow/skills/generate_images.py` 作为旧图片生成节点，应逐步并入 `generate_visual_assets.py` 或删除。

### 4.9 Publisher Node / 成稿与发布

定位：确定性发布节点，不负责智能决策。

拆分小点：

1. 组装标题、摘要、正文、封面、文内图。
2. 生成 `publish_decision`。
3. 判断是否允许自动入草稿箱。
4. 调用公众号草稿箱 API。
5. 记录 `draft_id`、账号、主题样式、失败原因。

输入：

- `generated_article`
- `visual_state.assets`
- `quality_report`
- `publish_policy`

输出：

- `final_article`
- `draft_info`
- `push_records`

保留模块：

- `workflow/skills/assemble_article.py`
- `workflow/skills/push_to_draft.py`
- `workflow/utils/wechat_api.py`
- `workflow/utils/wechat_draft_service.py`
- `workflow/utils/markdown_to_wechat.py`

---

## 5. 共享状态重构

### 5.1 状态分区

建议把 `WorkflowState` 分为稳定分区：

```json
{
  "identity": {
    "task_id": "xxx",
    "mode": "manual|auto_hotspot",
    "keywords": "xxx",
    "original_keywords": "xxx"
  },
  "config_snapshot": {},
  "topic_state": {
    "hotspot_candidates": [],
    "selected_hotspot": {},
    "selected_topic": {}
  },
  "planning_state": {},
  "research_state": {},
  "writing_state": {},
  "visual_state": {},
  "quality_state": {},
  "publish_state": {
    "final_article": {},
    "draft_info": {},
    "push_records": []
  },
  "runtime": {
    "status": "running",
    "current_skill": "compose_draft",
    "progress": 62,
    "error": null,
    "revision_count": 0
  }
}
```

### 5.2 兼容策略

短期不强制迁移旧任务 JSON。

执行时：

- 旧字段继续读取。
- 新字段优先写入分区对象。
- API 返回兼容旧字段。
- 前端展示优先使用新字段，缺失时回退旧字段。

---

## 6. 需要删除、合并、保留或重命名的代码

### 6.1 目录命名调整目标

当前 `workflow/skills` 名称过宽，里面混放了 Agent、工具节点、审核节点、发布节点和旧链路代码。后续建议将 `skills` 文件夹重命名并拆分为更贴合系统规划的结构。

目标目录：

```text
workflow/
  graph.py
  state.py
  config.py
  agents/
    planner.py
    outline.py
    writer.py
    reviewer.py
    image.py
    hotspot.py
  nodes/
    intake.py
    topic_decision.py
    research_plan.py
    evidence_pack.py
    visual_plan.py
    quality_gate.py
    targeted_revision.py
    assemble_article.py
    ui_feedback.py
  tools/
    search_web.py
    fetch_extract.py
    hotspot_sources.py
    image_generation.py
    wechat_draft.py
  services/
    model_config.py
    workflow_run_log.py
    topic_pool.py
    review_queue.py
  utils/
    article_type_registry.py
    evidence_pack.py
    quality_scoring.py
    research_queries.py
    visual_briefs.py
```

命名规则：

- `agents/`：保留有 LLM 决策能力的专职 Agent，例如规划、写作、审核、图片理解。
- `nodes/`：Workflow/Harness 中的确定性编排节点，例如组装、质量门禁、状态反馈。
- `tools/`：外部工具或 IO 能力，例如搜索、网页抽取、热点源、图片生成、微信草稿箱。
- `services/`：业务服务和持久化封装，例如选题池、审核队列、运行日志。
- `utils/`：无状态纯函数、规则表、评分函数、格式转换。

迁移步骤：

1. 先新增目标目录，保留旧 `workflow/skills` 作为兼容层。
2. 将主图 `workflow/graph.py` 的导入逐步改为新目录。
3. 每迁移一个节点，同步迁移对应测试引用。
4. 所有主链路引用完成后，删除 `workflow/skills` 目录。
5. 文档和 README 统一使用新目录名称，不再出现“skill 节点”表述。

### 6.2 建议迁移后的文件映射

| 当前文件 | 目标文件 | 处理方式 |
| --- | --- | --- |
| `workflow/skills/capture_hot_topics.py` | `workflow/agents/hotspot.py` 或 `workflow/nodes/hotspot_capture.py` | 保留并改名 |
| `workflow/skills/analyze_hotspot_opportunities.py` | `workflow/nodes/topic_decision.py` | 保留并改名 |
| `workflow/skills/intake_task_brief.py` | `workflow/nodes/intake.py` | 保留并改名 |
| `workflow/skills/planner_agent.py` | `workflow/agents/planner.py` | 保留并改名 |
| `workflow/skills/resolve_article_type.py` | `workflow/nodes/resolve_article_type.py` | 保留并改名 |
| `workflow/skills/outline_planner.py` | `workflow/agents/outline.py` | 保留并改名 |
| `workflow/skills/compose_draft.py` | `workflow/agents/writer.py` | 保留并改名 |
| `workflow/skills/review_article_draft.py` | `workflow/agents/reviewer.py` | 保留并改名 |
| `workflow/skills/plan_research.py` | `workflow/nodes/research_plan.py` | 保留并改名 |
| `workflow/skills/run_research.py` | `workflow/nodes/run_research.py` | 保留并改名 |
| `workflow/skills/search_web.py` | `workflow/tools/search_web.py` | 保留并迁移 |
| `workflow/skills/fetch_extract.py` | `workflow/tools/fetch_extract.py` | 保留并迁移 |
| `workflow/skills/build_evidence_pack.py` | `workflow/nodes/evidence_pack.py` | 保留并改名 |
| `workflow/skills/plan_visual_assets.py` | `workflow/nodes/visual_plan.py` | 保留并改名 |
| `workflow/skills/image_agent.py` | `workflow/agents/image.py` | 保留并改名 |
| `workflow/skills/generate_visual_assets.py` | `workflow/tools/image_generation.py` | 保留并迁移 |
| `workflow/skills/review_visual_assets.py` | `workflow/agents/visual_reviewer.py` | 保留并改名 |
| `workflow/skills/quality_gate.py` | `workflow/nodes/quality_gate.py` | 保留并改名 |
| `workflow/skills/targeted_revision.py` | `workflow/nodes/targeted_revision.py` | 保留并改名 |
| `workflow/skills/assemble_article.py` | `workflow/nodes/assemble_article.py` | 保留并改名 |
| `workflow/skills/push_to_draft.py` | `workflow/tools/wechat_draft.py` | 保留并迁移 |
| `workflow/skills/ui_feedback.py` | `workflow/nodes/ui_feedback.py` | 保留并改名 |
| `workflow/skills/error_handler.py` | `workflow/nodes/error_handler.py` | 保留并改名 |

### 6.3 建议删除的旧链路节点

以下模块不应再进入主 workflow，可在确认测试迁移后删除：

- `workflow/skills/interpret_user_intent.py`
- `workflow/skills/infer_style_profile.py`
- `workflow/skills/build_article_blueprint.py`
- `workflow/skills/plan_article_strategy.py`
- `workflow/skills/generate_article.py`
- `workflow/skills/generate_images.py`
- `workflow/skills/rank_sources.py`

对应旧测试也需要删除或迁移：

- `tests/test_article_blueprint_flow.py`
- `tests/test_plan_article_strategy.py`
- `tests/test_generate_article.py`
- `tests/test_generate_images.py`

### 6.4 暂时保留的基础工具节点

以下虽然名称来自旧链路，但当前仍是研究链路的一部分，不能直接删除：

- `workflow/skills/search_web.py`
- `workflow/skills/fetch_extract.py`

后续可改名为：

- `workflow/tools/search_web.py`
- `workflow/tools/fetch_extract.py`

### 6.5 文档清理

建议将旧方案文档归档到 `docs/archive/`：

- `demand.md`
- `walkthrough.md`
- `docs/article-generation-strategy-upgrade.md`
- 早期 `superpowers/specs` 和 `superpowers/plans` 中与旧链路冲突的内容

保留并更新：

- `docs/xitong.md`
- `docs/2026-04-24-workflow-full-refactor-plan.md`
- `docs/2026-04-25-workflow-full-refactor-changelog.md`
- 本文档

---

## 7. 后端模块变更

### 7.1 API 路由拆分

现有路由：

- `tasks`
- `articles`
- `hotspots`
- `schedules`
- `accounts`
- `config`
- `users`
- `auth`

建议新增：

- `topics`：候选选题池、人工选题、选题入任务。
- `reviews`：人工审核、驳回、批准入草稿箱。
- `workflow-runs`：节点运行记录、耗时、失败重试。
- `templates`：文章模板预设。
- `profiles`：账号定位预设。

### 7.2 数据模型新增

建议新增模型：

```text
TopicCandidate
  - topic_id
  - source_cluster
  - title
  - angle
  - category
  - hot_score
  - account_fit_score
  - risk_score
  - status

ReviewDecision
  - review_id
  - task_id
  - reviewer
  - decision: approve|reject|revise
  - comment
  - created_at

WorkflowRunStep
  - task_id
  - node_name
  - status
  - started_at
  - finished_at
  - duration_ms
  - error

ContentTemplatePreset
  - template_id
  - name
  - article_type
  - sections
  - tone
  - image_strategy
```

### 7.3 存储演进

当前以 JSON 文件持久化为主。短期可继续使用，但需要按集合拆分：

- `data/tasks.json`
- `data/topics.json`
- `data/reviews.json`
- `data/templates.json`
- `data/profiles.json`
- `data/workflow_runs.json`

中期建议迁移 SQLite/PostgreSQL，原因：

- 任务和节点日志会增长很快。
- 候选选题需要筛选、排序、状态流转。
- 人工审核和发布记录需要可追溯。

---

## 8. 前端页面变更方案

### 8.1 导航结构调整

结合后台原型，建议导航从“任务驱动”调整为“内容生产流水线驱动”：

```text
工作台
选题中心
创作任务
审核中心
文章库
发布中心
自动化排期
配置中心
系统账号
```

现有页面映射：

| 新页面 | 现有页面/模块 | 处理方式 |
| --- | --- | --- |
| 工作台 | 暂无独立页 | 新增 |
| 选题中心 | hotspots + schedules 部分能力 | 新增 |
| 创作任务 | TaskCreate / TaskDetail / History | 拆分重组 |
| 审核中心 | TaskDetail 中的质量状态 | 新增 |
| 文章库 | ArticleManage | 保留增强 |
| 发布中心 | ArticleManage 推送能力 | 新增或从文章库拆出 |
| 自动化排期 | ScheduleManage | 保留增强 |
| 配置中心 | StyleConfig / ModelConfig / AccountConfig | 合并为分组配置 |
| 系统账号 | UserManage / Auth | 保留，作为独立系统账号模块，不并入配置中心 |

### 8.2 工作台

目标：进入后台后先看生产状态，而不是直接进表单。

模块拆分：

1. 今日任务概览：运行中、待审核、已入草稿箱、失败。
2. 热点机会榜：高分候选选题。
3. 生产漏斗：选题、研究、写作、出图、审核、发布。
4. 风险提醒：高风险、审核失败、发布失败。
5. 快捷操作：新建任务、抓取热点、创建排期、进入审核。

接口：

- `GET /dashboard/summary`
- `GET /topics?status=candidate&limit=10`
- `GET /reviews?status=pending`

### 8.3 选题中心

目标：把热点和人工选题变成独立资产。

模块拆分：

1. 热点抓取配置。
2. 热点候选列表。
3. 选题评分面板。
4. 账号匹配说明。
5. 风险标签。
6. 一键生成文章任务。
7. 加入选题池 / 忽略 / 黑名单。

页面状态：

- `candidate`
- `selected`
- `ignored`
- `converted_to_task`

核心操作：

- 预览热点
- 执行抓取
- 生成选题
- 选题入任务

### 8.4 创作任务

目标：保留手动任务，但表单要按链路配置拆小模块。

任务创建页模块：

1. 基础主题：关键词、目标账号、模式。
2. 选题来源：手动主题 / 热点候选 / 历史文章复用。
3. 账号定位：定位、读者、匹配标签、规避话题。
4. 内容模板：文章类型、长度、语气、结构。
5. 研究策略：是否联网、资料来源偏好、引用要求。
6. 图片策略：封面、文内图数量、风格、品牌色、标题安全区。
7. 审核策略：严格度、自动改写、人工复核、高风险拦截。
8. 发布策略：是否入草稿箱、是否人工确认、目标账号。

任务详情页模块：

1. 任务状态轨道。
2. 节点时间线。
3. 配置快照。
4. 选题决策。
5. 研究证据包。
6. 提纲。
7. 正文草稿。
8. 图片资产。
9. 质量报告。
10. 发布决策与草稿箱结果。

### 8.5 审核中心

目标：把人工兜底从“任务详情里的提示”升级成独立工作流。

模块拆分：

1. 待审核列表。
2. 审核详情。
3. 风险项定位。
4. 原文与建议改写对比。
5. 图片审核。
6. 操作区：通过、退回改写、手动修改、禁止发布。

审核结果：

- `approved`
- `rejected`
- `revision_requested`
- `blocked`

### 8.6 文章库

目标：管理最终成稿。

模块拆分：

1. 文章列表。
2. 状态筛选：已生成、待审核、可发布、已入草稿、发布失败。
3. 文章预览。
4. 封面和文内图预览。
5. 质量报告摘要。
6. 批量推送。
7. 复用为新任务。

### 8.7 发布中心

目标：集中处理公众号草稿箱和多账号发布。

模块拆分：

1. 待入草稿文章。
2. 目标账号选择。
3. 主题样式选择。
4. 推送结果。
5. 失败重试。
6. 草稿箱记录。

### 8.8 自动化排期

目标：从“定时执行任务”升级为“自动内容生产规则”。

模块拆分：

1. 规则列表。
2. 热点分类与平台配置。
3. 执行频率。
4. 每次最大生成篇数。
5. 目标账号。
6. 审核与发布策略。
7. 最近运行结果。

### 8.9 配置中心

建议拆成 Tab：

1. 模型配置。
2. 发布账号。
3. 账号定位预设。
4. 文章模板。
5. 图片风格。
6. 审核规则。
7. 公众号样式。

现有 `StyleConfig`、`ModelConfig`、`AccountConfig` 可以迁入统一配置中心，但路由可先保持兼容。

### 8.10 系统账号

目标：系统账号模块必须保留，独立负责后台登录账号、角色和启停状态，不合并进配置中心。

模块拆分：

1. 登录账号列表。
2. 新增账号。
3. 编辑显示名称、角色、启用状态。
4. 重置密码。
5. 最近登录时间。
6. 操作审计记录。

保留现有模块：

- `api/routers/users.py`
- `api/routers/auth.py`
- `api/auth.py`
- `frontend/src/pages/UserManage.tsx`
- `frontend/src/pages/Login.tsx`
- `frontend/src/store/authStore.ts`

后续增强：

- 角色权限拆分为 `admin`、`operator`、`reviewer`。
- 审核中心操作需要记录审核人。
- 发布中心的手动推送需要记录操作人。
- 用户禁用后清理本地 token 或让下一次请求失效。

---

## 9. 前端视觉与交互要求

### 9.1 视觉方向

后台系统应采用克制、密集、可扫描的工作台风格：

- 信息密度高，但分组清晰。
- 减少营销式大 Hero。
- 页面首屏直接展示可操作内容。
- 卡片只用于重复实体，如任务、选题、文章、规则。
- 关键状态用颜色和标签表达，避免大段解释文字。

### 9.2 结合 Figma 的落地项

开发前需要从 Figma 补齐：

1. 导航样式：侧边栏宽度、图标、选中态。
2. 页面布局：顶部栏、内容区、筛选区、表格区。
3. 字号和行高。
4. 色板：主色、状态色、背景、边框。
5. 按钮、表单、Tab、Tag、Modal 的组件状态。
6. 移动端或窄屏适配规则。

### 9.3 组件拆分

建议新增组件目录：

```text
frontend/src/components/pipeline/
  WorkflowTimeline.tsx
  NodeStatusBadge.tsx
  QualityReportPanel.tsx
  ConfigSnapshotPanel.tsx
  EvidencePackPanel.tsx

frontend/src/components/topics/
  TopicScoreCard.tsx
  TopicCandidateTable.tsx
  HotspotSourceSelector.tsx

frontend/src/components/articles/
  ArticlePreview.tsx
  VisualAssetGallery.tsx
  PublishDecisionCard.tsx

frontend/src/components/reviews/
  ReviewQueueTable.tsx
  RiskIssueList.tsx
  RevisionComparePanel.tsx
```

---

## 10. 实施阶段拆分

### Phase 1：清理旧链路，稳定新主链路

目标：后端只保留一条主 workflow。

任务：

1. 确认旧节点未被主图引用。
2. 删除旧链路节点和对应测试。
3. 保留 `search_web/fetch_extract`，作为 research 工具。
4. 将 `generate_images` 能力并入 `generate_visual_assets`。
5. 更新 `README`、`walkthrough`、旧文档引用。

验收：

- `pytest` 通过。
- 新任务能完整走到 `final_article`。
- 旧任务详情不崩溃。

### Phase 2：选题中心与热点候选池

目标：热点不再只是任务内部状态，而是可管理资产。

任务：

1. 新增 `topics` 数据模型。
2. 新增 `topics` API。
3. 热点抓取结果写入候选池。
4. 前端新增选题中心。
5. 支持从选题一键创建任务。

验收：

- 可抓取、筛选、忽略、转任务。
- 选题详情能看到分数来源。

### Phase 3：任务详情重构为链路视图

目标：让用户看得懂每一步在做什么。

任务：

1. 重构 `TaskDetail.tsx`。
2. 增加节点时间线。
3. 增加证据包、提纲、图片、质量报告独立面板。
4. WebSocket 进度映射到节点状态。

验收：

- 运行中任务能实时更新。
- 完成任务能完整回看链路。

### Phase 4：审核中心

目标：人工审核成为独立业务模块。

任务：

1. 新增 `reviews` API。
2. `quality_gate` 输出待审核记录。
3. 前端新增审核中心。
4. 支持通过、退回、阻断。
5. 审核通过后允许推送草稿箱。

验收：

- 强制人工复核任务不会自动推送。
- 人工通过后可继续发布。

### Phase 5：配置中心预设化

目标：减少每次创建任务的重复输入。

任务：

1. 账号定位预设。
2. 内容模板预设。
3. 审核策略预设。
4. 图片风格预设。
5. 发布策略预设。

验收：

- 创建任务可选择预设。
- 预设变更不影响已运行任务的 `config_snapshot`。

### Phase 6：发布中心与多账号发布

目标：把文章库和发布动作解耦。

任务：

1. 新增发布中心页面。
2. 统一显示草稿箱推送记录。
3. 支持失败重试。
4. 支持批量推送不同账号。

验收：

- 能看到每篇文章每个账号的推送结果。
- 失败原因可追踪。

---

## 11. 验收清单

### 11.1 后端

- 主 workflow 只有一条正式链路。
- 旧链路节点不再被导入。
- `config_snapshot` 在任务生命周期内不漂移。
- `final_article` 是文章库和发布模块的唯一优先来源。
- 质量门禁能正确分流：通过、改写、人工复核、阻断。
- 自动热点和手动主题都能进入同一条后续链路。

### 11.2 前端

- 工作台能看到任务、审核、发布和热点概览。
- 选题中心能管理候选选题。
- 任务详情能按节点展示链路产物。
- 审核中心能处理人工兜底。
- 文章库只管理成稿。
- 发布中心只处理草稿箱和推送记录。
- 页面样式与 Figma 原型保持导航、间距、颜色、表格、表单和状态组件一致。

### 11.3 测试

需要保留和新增：

- workflow 主链路测试。
- 手动任务到成稿测试。
- 自动热点到选题测试。
- 质量门禁分支测试。
- 人工审核 API 测试。
- 选题中心 API 测试。
- 前端页面 smoke test。
- 任务详情 WebSocket 更新测试。

---

## 12. 最终目标状态

最终系统应变成：

```text
热点/手动主题
  -> 候选选题
  -> 多 Agent 内容生产
  -> 证据驱动写作
  -> 图片协同生成
  -> 质量门禁
  -> 人工审核兜底
  -> 成稿入库
  -> 公众号草稿箱
```

后台页面应变成：

```text
工作台看状态
选题中心定方向
创作任务跑链路
审核中心控风险
文章库管成稿
发布中心管草稿箱
排期台跑自动化
配置中心管策略
```

这个拆分能让系统从“一个文章生成工具”升级为“可运营的内容生产后台”。
