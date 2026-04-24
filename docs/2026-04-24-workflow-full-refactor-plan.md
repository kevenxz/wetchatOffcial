# 2026-04-24 Workflow 全链路重构方案

## 目标

按照 `docs/xitong.md`，将系统重构为 **Workflow/Harness 主导 + 专职 Agent 节点协作 + 统一共享状态 + 人工兜底** 的内容生产流水线。

目标能力：

- 手动主题和自动热点使用同一条主链路。
- 前端配置一次任务策略，后端生成不可变的 `config_snapshot`。
- 热点模块只输出候选选题池和最终选题，不直接跳过筛选写文章。
- Planner、Writer、Reviewer、Image Agent、Publisher 通过共享状态协作。
- 质量门禁决定自动修订、人工复核或进入草稿箱。
- 调度任务由 scheduler 统一处理账号、主题样式和多账号推送。

## 目标链路

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

## 共享状态设计

核心字段：

- `mode`: `manual | auto_hotspot`
- `config_snapshot`: 本次任务的配置快照，包含生成、热点、账号定位、模板、审核、图片、发布策略。
- `task_brief`: 标准任务简报。
- `hotspot_candidates`: 热点候选池。
- `selected_hotspot`: 抓取层选中的热点。
- `selected_topic`: 选题决策层输出的可写选题。
- `planning_state`: Planner 输出，包含文章类型、检索计划、图片计划、审核阈值。
- `research_state`: 搜索、提取、证据包和资料缺口。
- `writing_state`: 草稿、文章审核和修订建议。
- `visual_state`: 图片 brief、图片资产、图片审核。
- `quality_state`: 质量报告、门禁结果、发布决策。
- `generated_article`: 写作/图片阶段的文章对象。
- `final_article`: 成稿组装后的最终文章包。
- `human_review_required`: 是否需要人工复核。
- `revision_count`: 自动修订轮次。

## 配置快照

`GenerationConfig` 扩展为以下可选块：

- `account_profile`
  - `positioning`
  - `target_readers`
  - `fit_tags`
  - `avoid_topics`

- `content_template`
  - `template_id`
  - `name`
  - `preferred_framework`
  - `article_length`
  - `tone`

- `review_policy`
  - `strictness`
  - `auto_rewrite`
  - `require_human_review`
  - `block_high_risk`
  - `max_revision_rounds`

- `image_policy`
  - `enabled`
  - `cover_enabled`
  - `inline_enabled`
  - `inline_count`
  - `style`
  - `brand_colors`
  - `title_safe_area`

- `publish_policy`
  - `auto_publish_to_draft`
  - `require_manual_confirmation`

运行开始时通过 `workflow/config.py` 归一化为 `config_snapshot`，后续节点只读快照，避免配置在流程中漂移。

## 节点职责

- `capture_hot_topics`
  - 读取热点配置。
  - 关闭热点时透传手动主题。
  - 开启热点时抓取、打分、去重、选择热点。

- `intake_task_brief`
  - 生成标准任务简报。
  - 合并主题、热点、账号定位、模板、审核、图片、发布配置。

- `planner_agent`
  - 选择文章类型。
  - 生成检索角度、图片角色、质量阈值。
  - 根据审核严格度调整阈值。
  - 根据图片策略决定是否生成封面和文内图。

- `analyze_hotspot_opportunities`
  - 消费真实热点候选。
  - 输出 `selected_topic`。
  - 热点启用但无候选时不制造假热点。

- `plan_research/run_research/build_evidence_pack`
  - 围绕 `selected_topic` 生成检索计划。
  - 聚合搜索、网页提取和证据包。

- `plan_article_angle/compose_draft`
  - 按证据密度和模板策略生成文章蓝图。
  - 写作时注入账号定位和内容模板。

- `review_article_draft/review_visual_assets`
  - 输出结构化审核结果和修订建议。

- `quality_gate`
  - 按审核策略决定 `pass/revise_writing/revise_visuals/human_review`。
  - 超过最大修订轮次后转人工复核。

- `targeted_revision`
  - 只生成局部修订 brief。
  - 增加 `revision_count`。

- `assemble_article`
  - 合并正文、图片、热点、质量报告和发布决策。
  - 输出 `final_article`。

- `push_to_draft`
  - 优先推送 `final_article`。
  - 调度任务由 scheduler 统一推送。

## 前端调整

- 手动任务创建页新增“流程策略”：
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

- 详情页展示：
  - 配置快照
  - 选题决策
  - 最终成稿
  - 质量报告
  - 人工复核状态

## 兼容策略

- 不迁移 JSON 数据结构，新增字段全部可选。
- 旧任务没有 `config_snapshot` 时，运行时按默认值补齐。
- `GenerationConfig` 保留原有字段，新增配置块不破坏旧请求。
- 调度任务原有 `hotspot_capture` 保持兼容。

## 验收标准

- 手动任务关闭热点时仍能完整生成文章。
- 手动任务开启热点时先抓取热点，再进入选题和写作。
- 定时任务开启热点时由 workflow 生成内容，由 scheduler 推送草稿箱。
- `TaskResponse` 能看到 `config_snapshot/selected_topic/final_article/quality_report`。
- 质量不通过时可自动修订；超过修订轮次或强制人工复核时不自动推送。
- 后端 pytest、前端测试和前端 build 通过。
