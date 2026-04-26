# 2026-04-26 搜索内容驱动文章框架优化

## 背景

原 workflow 已经有 `plan_article_angle` 节点负责生成文章结构，但 fallback 路径仍会明显依赖主题模板，例如融资、出海、发布等固定结构。这样会导致一个问题：即使前面已经完成搜索和抽取，文章框架也可能没有充分利用真实搜索内容。

本次优化目标：

- 文章结构优先由搜索结果、抽取内容和证据包共同决定。
- 模板只作为兜底，不作为默认主导。
- 写作阶段必须遵循搜索内容生成的框架，避免重新退回泛化结构。

## 变更范围

### 1. `plan_article_angle`

新增搜索材料汇总逻辑：

- 从 `research_state.evidence_items` 收集搜索后生成的证据项。
- 从 `research_state.extracted_contents` 补充网页抽取正文、标题、来源信息。
- 从 `research_state.search_results` 补充搜索结果标题和摘要。
- 从 `evidence_pack` 的 `confirmed_facts/usable_data_points/usable_cases/risk_points` 补充结构化证据。

新增字段：

- `source_driven_framework`: 搜索内容驱动生成的结构信号。
- `evidence_map`: 文章章节与来源证据的映射关系。

新的规划优先级：

1. 优先用搜索材料生成章节。
2. 搜索材料不足时，用证据包补齐数据、案例和风险边界章节。
3. 搜索与证据都不足时，才退回主题模板。

### 2. 模型规划 prompt

模型调用现在额外接收：

- `search_materials`
- `evidence_pack`
- `article_type`
- `selected_topic`
- `account_profile`
- `content_template`

模型要求调整为：

- 先根据真实搜索材料决定文章框架。
- 每个主要 H2 尽量映射一个具体来源信号。
- 不允许用固定模板替代搜索内容驱动的结构。
- 始终保留风险边界或证据边界。

### 3. `compose_draft`

写作 prompt 增加约束：

- 如果蓝图里存在 `source_driven_framework` 和 `evidence_map`，正文必须遵循。
- 不允许把搜索驱动框架替换成通用模板。
- 每个主要 H2 必须基于搜索信号展开，或者明确说明证据边界。

## 数据流

```text
search_web
  -> fetch_extract
  -> run_research.evidence_items
  -> build_evidence_pack.evidence_pack
  -> plan_article_angle.search_materials
  -> source_driven_framework / evidence_map
  -> compose_draft
```

## 预期效果

- 搜索结果里的关键事实、数据、案例会直接影响文章结构。
- 同一主题在不同搜索结果下会生成不同框架。
- 文章更接近“先研究，再定结构，再写作”的编辑流程。
- 质量审核阶段更容易判断每个章节是否有证据支撑。

## 测试覆盖

新增测试覆盖：

- 无模型 fallback 时，能从 `evidence_items` 生成搜索内容驱动章节。
- 模型路径会把 `search_materials` 传入 prompt payload。
- 模型未返回 `source_driven_framework/evidence_map` 时，系统会自动补齐。

验证命令：

```text
python -m compileall workflow tests
pytest tests/test_plan_article_angle.py -q
```
