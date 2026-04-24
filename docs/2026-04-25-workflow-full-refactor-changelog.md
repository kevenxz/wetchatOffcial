# 2026-04-25 Workflow 全链路重构变更文档

## 背景

本次变更基于 `docs/xitong.md` 中的系统设计，对现有内容生产 workflow 做一次全链路重构。目标不是新增单点能力，而是把手动任务、自动热点、文章生成、图片生成、质量审核、人工复核和公众号草稿箱发布统一到同一套状态机与配置模型中。

关联方案文档：

- `docs/2026-04-24-workflow-full-refactor-plan.md`

关联提交：

- `7298259 重构内容生产工作流全链路`

## 核心变化

### 1. 统一 workflow 配置快照

新增 `workflow/config.py`，在 workflow 启动时生成 `config_snapshot`。后续节点读取快照，不再各自解析前端原始配置，避免配置在流程中漂移。

快照包含：

- `mode`: `manual` 或 `auto_hotspot`
- `generation`: 原有文章生成配置
- `hotspot`: 热点抓取配置
- `account_profile`: 账号定位、目标读者、匹配标签、规避话题
- `content_template`: 模板、文章长度、语气、结构偏好
- `review_policy`: 审核严格度、自动改写、人工复核、最大改写轮次
- `image_policy`: 自动出图、封面图、文内图数量、图片风格、品牌色
- `publish_policy`: 是否自动进入公众号草稿箱、是否需要人工确认

### 2. 扩展共享状态模型

`workflow/state.py` 新增关键字段：

- `mode`
- `config_snapshot`
- `selected_topic`
- `final_article`
- `revision_count`

这些字段被纳入 `workflow/graph.py` 的结果回传，API 和前端可以直接查看本次任务的配置、选题、最终成稿与审核状态。

### 3. 重构主链路流转

主链路调整为：

```text
capture_hot_topics
  -> intake_task_brief
  -> planner_agent
  -> analyze_hotspot_opportunities
  -> plan_research
  -> run_research
  -> build_evidence_pack
  -> resolve_article_type
  -> plan_article_angle
  -> compose_draft
  -> review_article_draft
  -> plan_visual_assets
  -> generate_visual_assets
  -> review_visual_assets
  -> quality_gate
  -> targeted_revision | assemble_article
  -> push_to_draft | ui_feedback
```

关键变化：

- 热点任务和手动任务共用后续文章生产链路。
- 热点分析节点输出 `selected_topic`，写作和检索围绕该选题继续执行。
- 质量门禁不再只决定是否推送，也会决定自动改写、人工复核或继续发布。
- 新增 `assemble_article` 节点，统一合并文章、图片资产、质量报告和发布决策。

### 4. 新增成稿组装节点

新增 `workflow/skills/assemble_article.py`。

该节点负责：

- 将 `generated_article` 与 `visual_state.assets` 合并为 `final_article`。
- 自动补齐 `cover_image`、`illustrations`、`visual_assets`。
- 写入 `selected_topic`、`selected_hotspot`、`quality_report`。
- 根据审核策略、发布策略和质量结果生成 `publish_decision`。
- 设置 `human_review_required`，阻止高风险内容自动进入草稿箱。

### 5. 审核与自动改写策略

`workflow/skills/quality_gate.py` 支持从 `config_snapshot.review_policy` 读取策略：

- `strictness`: 影响 Planner 生成的质量阈值。
- `auto_rewrite`: 控制是否允许自动改写。
- `max_revision_rounds`: 控制最大自动改写轮次。
- `require_human_review`: 强制人工复核。
- `block_high_risk`: 存在阻断原因时要求人工复核。

`workflow/skills/targeted_revision.py` 会递增 `revision_count`，避免无限改写。

### 6. 选题、写作、图片节点适配

以下节点开始读取 `selected_topic` 或 `config_snapshot`：

- `intake_task_brief`: 将配置快照写入任务简报。
- `planner_agent`: 根据账号定位、模板、审核策略和图片策略规划。
- `analyze_hotspot_opportunities`: 从热点候选生成可写选题。
- `plan_research`: 基于选题生成检索计划。
- `plan_article_angle`: 将选题、账号定位和模板传入角度规划。
- `compose_draft`: 写作时使用选题、账号定位和内容模板。
- `plan_visual_assets`: 按图片策略生成封面和文内图 brief。
- `push_to_draft`: 优先使用 `final_article` 推送草稿。

### 7. API 与任务同步

`api/models.py` 扩展 `GenerationConfig`，新增：

- `AccountProfileConfig`
- `ContentTemplateConfig`
- `ReviewPolicyConfig`
- `WorkflowImagePolicyConfig`
- `PublishPolicyConfig`

`TaskResponse` 新增：

- `mode`
- `config_snapshot`
- `selected_topic`
- `final_article`

`api/workflow_sync.py` 同步新增字段，确保任务详情页、WebSocket 回调和持久化状态一致。

`api/routers/tasks.py` 与 `api/scheduler.py` 改为传递完整 `generation_config.model_dump()`，避免嵌套策略字段被旧的归一化逻辑提前丢弃。

### 8. 前端配置与详情展示

`frontend/src/api/index.ts` 增加与后端一致的 TypeScript 类型和默认值。

`frontend/src/pages/TaskCreate.tsx` 增加“流程策略”配置区：

- 账号定位
- 账号匹配标签
- 内容模板
- 文章长度
- 审核严格度
- 必须人工复核
- 自动出图
- 文内配图数量
- 图片风格
- 自动入公众号草稿箱

`frontend/src/pages/TaskDetail.tsx` 调整为优先展示 `final_article`，并新增：

- 配置快照
- 选题决策

## 兼容性说明

- 旧任务没有 `config_snapshot` 时，workflow 启动时会按默认值补齐。
- 原有 `generation_config` 的 `audience_roles/article_strategy/style_hint` 仍保留。
- `generated_article` 仍会同步存在，但发布和详情展示优先使用 `final_article`。
- `skip_auto_push=true` 会写入发布策略，阻止自动进入公众号草稿箱。
- 热点抓取为空时不会再构造虚假候选，流程回退到原始关键词。

## 验证结果

已在 worktree `G:\PycharmProjects\wechatProject\wechatProject\.worktrees\workflow-full-refactor` 验证：

```text
python -m compileall api workflow tests
pytest -q
npm run build
npm run test -- --run
```

结果：

- 后端测试：`122 passed`
- 前端测试：`44 passed, 1 skipped`
- 前端构建：通过

前端测试输出中仍存在项目既有的 React Router future flag、AntD `destroyOnClose`、jsdom `getComputedStyle` 警告，不影响测试结果。

## 后续建议

- 将 `publish_decision` 在前端做成明确的人工复核/可发布状态卡，而不是仅展示 JSON。
- 为 `config_snapshot` 增加版本号，例如 `snapshot_version: 1`，便于后续迁移。
- 将账号定位、模板、审核策略从任务表单抽象为可复用预设，减少每次手动输入。
- 增加端到端任务流测试，覆盖自动热点到草稿箱的完整路径。
