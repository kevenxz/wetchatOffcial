# LangGraph 文章蓝图与可信搜索改造说明

## 1. 改造目标

这次改造解决两个核心问题：

1. 文章生成 prompt 过于生硬，结构、风格、搜索重点都挤在 `generate_article` 一个节点里。
2. 搜索阶段只拿 URL 列表，无法优先官网、官方文档和高可信媒体，也没有免费的 DuckDuckGo 兜底。

改造后的目标是：

- 用户默认只输入主题文本，风格由系统自动推断
- 保留可选 `style_hint`，作为额外风格约束
- 先生成文章蓝图，再按蓝图去搜索，再按蓝图和证据写文章
- 搜索优先官网/官方文档/权威媒体，并增加 DuckDuckGo 免费兜底
- LangGraph 全链路保留中间状态，方便调试、展示和后续扩展

## 2. 新的 LangGraph 流程

原流程：

`initialize -> search_web -> fetch_extract -> plan_article_strategy -> generate_article -> generate_images`

现流程：

`initialize -> interpret_user_intent -> infer_style_profile -> build_article_blueprint -> plan_search_queries -> search_web -> rank_sources -> fetch_extract -> generate_article -> generate_images`

职责拆分如下：

- `interpret_user_intent`
  - 解析主题、主角色、文章目标、解析后的文章策略
- `infer_style_profile`
  - 自动生成风格画像
  - 如果用户提供 `style_hint`，会和自动画像合并
- `build_article_blueprint`
  - 生成结构化文章蓝图
  - 同时回填兼容旧接口的 `article_plan`
- `plan_search_queries`
  - 根据蓝图生成搜索词和搜索意图
- `search_web`
  - 多引擎搜索，返回结构化搜索结果，而不是纯 URL
- `rank_sources`
  - 按可信度、相关度和搜索意图排序，保留来源多样性
- `fetch_extract`
  - 只抓取排序后的高分来源
- `generate_article`
  - 只负责按“意图 + 风格 + 蓝图 + 证据”写文章

## 3. 新增状态字段

`WorkflowState` 新增：

- `user_intent`
- `style_profile`
- `article_blueprint`
- `search_queries`
- `search_results` 从 `list[str]` 升级为 `list[dict]`

保留：

- `generation_config`
- `article_plan`
- `generated_article`

其中：

- `generation_config`
  - `audience_roles`
  - `article_strategy`
  - `style_hint`
- `article_plan`
  - 继续保留给前端和历史任务展示，兼容旧逻辑
  - 内容由 `article_blueprint` 派生，不再是唯一规划来源

## 4. 风格推断与蓝图生成

### 4.1 风格推断

系统现在内置 4 类风格原型：

- `finance_rational`
- `tech_deep_explainer`
- `product_review`
- `trend_commentary`

系统会根据：

- 主题文本
- 目标角色
- 文章策略
- 用户可选 `style_hint`

自动生成 `style_profile`，包括：

- 语气
- 标题写法
- 开头写法
- 段落节奏
- 证据风格
- 术语解释规则
- 禁用写法
- 面向正文节点的简化 `style_prompt`

### 4.2 蓝图生成

`build_article_blueprint` 会先生成结构化文章蓝图，而不是直接写正文。

蓝图包含：

- `title_strategy`
- `opening_goal`
- `reader_takeaway`
- `search_focuses`
- `search_query_hints`
- `ending_style`
- `planned_illustrations`
- `section_outline[]`

每个 `section_outline` 都包含：

- `heading`
- `goal`
- `evidence_needed`

## 5. 搜索策略升级

### 5.1 搜索来源

搜索链路现在支持：

- SerpApi Google
- Bing Web Search
- DuckDuckGo HTML 搜索

其中 DuckDuckGo 作为免费兜底，不依赖额外 API Key。

### 5.2 搜索结果结构化

`search_web` 不再只返回 URL，而是返回：

- `url`
- `title`
- `snippet`
- `domain`
- `provider`
- `query`
- `query_intent`
- `source_type`
- `authority_score`
- `relevance_score`
- `freshness_score`
- `official_bonus`
- `final_score`

### 5.3 来源排序

新增 `rank_sources` 节点，按以下维度排序：

- 来源可信度
- 与当前搜索意图的匹配度
- 与主题的相关度
- 官网/官方文档加分
- 同域名去重与多样性控制

来源类型识别包括：

- `official`
- `documentation`
- `github`
- `research`
- `media`
- `institution`
- `community`
- `aggregator`

## 6. 文章生成节点重构

`generate_article` 现在的输入为：

- `keywords`
- `user_intent`
- `generation_config`
- `style_profile`
- `article_blueprint`
- `article_plan`
- `extracted_contents`

正文 prompt 的职责被收敛为：

- 严格按照蓝图章节写作
- 严格基于抓取证据写作
- 按风格画像控制语气、标题和段落节奏
- 保留 `[插图1]...[插图3]`
- 对证据不足或来源分歧进行显式说明

同时保留：

- 结构化输出
- 非结构化 Markdown 回退解析
- 标题长度/章节完整性/插图标记/正文长度校验

## 7. API 与前端变化

### 7.1 `generation_config`

新增字段：

- `style_hint: string`

适用范围：

- 创建任务
- 编辑定时任务
- 定时任务执行
- 历史任务持久化

### 7.2 TaskResponse 新增

- `user_intent`
- `style_profile`
- `article_blueprint`

### 7.3 前端表单

新增可选输入：

- 任务创建页：`style_hint`
- 定时任务页：`style_hint`

如果不填写，系统自动推断风格；填写后作为偏好约束参与风格生成。

## 8. 关键代码落点

- `workflow/article_generation.py`
- `workflow/state.py`
- `workflow/graph.py`
- `workflow/skills/interpret_user_intent.py`
- `workflow/skills/infer_style_profile.py`
- `workflow/skills/build_article_blueprint.py`
- `workflow/skills/plan_search_queries.py`
- `workflow/skills/search_web.py`
- `workflow/skills/rank_sources.py`
- `workflow/skills/fetch_extract.py`
- `workflow/skills/generate_article.py`
- `api/models.py`
- `api/routers/tasks.py`
- `api/scheduler.py`
- `frontend/src/api/index.ts`
- `frontend/src/pages/TaskCreate.tsx`
- `frontend/src/pages/ScheduleManage.tsx`
- `frontend/src/pages/TaskDetail.tsx`

## 9. 验证结果

- 后端测试：`32 passed`
- 前端构建：`npm run build` 通过
- 兼容性：
  - 保留 `article_plan`
  - `fetch_extract` 仍兼容旧的 `search_results: list[str]`
  - 无搜索 API Key 时仍可使用 DuckDuckGo 兜底

## 10. 后续建议

- 增加 `organize_evidence` 节点，把证据按蓝图章节聚合后再写正文
- 把来源白名单、权威域名和排序权重抽成可配置项
- 在前端详情页展示 `style_profile` 和 `article_blueprint` 的核心字段，便于排查和复盘
