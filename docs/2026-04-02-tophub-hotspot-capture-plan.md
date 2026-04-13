# 2026-04-02 TopHub 前置热点捕获实现计划

## 1. 目标

在现有文章生成工作流前增加一个“热点捕获”前置阶段，让系统可以：

1. 配置多个热点平台来源，而不是只填一组字符串话题。
2. 配置热点题材类型，例如财经、热榜、AI、社区等分类。
3. 从 `https://tophub.today/` 抓取对应分类页和平台榜单页的数据。
4. 根据榜单排名、热度值和平台权重筛选“高分热点标题”。
5. 将筛出的标题作为后续文章 agent 的 `keywords` / 上下文输入，继续走现有 LangGraph 文章生成链路。

## 2. 当前现状

结合当前代码，现状如下：

- `api/models.py` 中的 `ScheduleConfig.hot_topics` 仍然只是 `list[str]`。
- `api/scheduler.py` 执行定时任务时，只是从 `hot_topics` 中随机取一个字符串作为 `keywords`。
- `workflow/graph.py` 当前流程从 `initialize -> interpret_user_intent -> ...` 开始，没有热点采集节点。
- `frontend/src/pages/ScheduleManage.tsx` 当前也只支持配置 `hot_topics` 标签列表。

结论：

- 现有系统已经有“定时任务驱动文章生成”的入口。
- 但“热点发现、抓取、筛选、回填标题”这层还不存在。
- 这个需求可以在现有架构上增量实现，不需要推翻现有文章生成流程。

## 3. TopHub 站点结构核对

2026-04-02 已核对 `https://tophub.today/` 页面结构，当前可作为一期抓取来源使用。

确认到的可用结构：

- 首页存在分类入口，例如 `/c/finance`、`/c/ai`、`/c/news`。
- 分类页中存在平台节点卡片，例如财经分类下可见第一财经、集思录等节点。
- 节点详情页采用 `/n/{hash}` 形式，例如知乎热榜页。
- 榜单条目在 HTML 中可提取出：
  - 排名
  - 标题
  - 跳转链接
  - 附加值 `extra`
- `extra` 字段并不统一：
  - 有的榜单是数字热度
  - 有的是类目文案
  - 有的为空

重要判断：

- TopHub 页面未统一提供“可直接使用的星级评分字段”。
- 因此一期实现不应依赖“真实星级”字段，而应使用“排名 + 热度值 + 平台权重 + 分类匹配度”计算内部 `selection_score`。
- 如果前端需要展示“星级”，可以将 `selection_score` 映射为 1-5 星的展示值，但这属于系统自定义评分，不是 TopHub 原始字段。

## 4. 一期建议范围

一期只做“够用且稳定”的最小闭环：

1. 在定时任务中新增 TopHub 热点配置。
2. 支持多平台节点配置。
3. 支持题材分类配置。
4. 调度触发时先抓 TopHub，再选出 1 条最佳热点标题。
5. 用该标题驱动后续文章生成工作流。
6. 在任务结果中保留热点命中明细，便于回溯。

一期暂不做：

- 多条热点批量一次生成多篇文章。
- 历史快照能力和时光机数据回放。
- 依赖 TopHub 会员能力的数据接口。
- 完整的可视化热点分析面板。

## 5. 设计方案

### 5.1 配置模型

建议将当前松散的 `hot_topics: list[str]` 升级为结构化配置，保留向后兼容。

建议新增：

```json
{
  "hotspot_capture": {
    "enabled": true,
    "source": "tophub",
    "categories": ["finance", "ai"],
    "platforms": [
      {
        "name": "知乎热榜",
        "path": "/n/mproPpoq6O",
        "weight": 1.0,
        "enabled": true
      },
      {
        "name": "抖音热点",
        "path": "/n/xxx",
        "weight": 1.2,
        "enabled": true
      }
    ],
    "filters": {
      "top_n_per_platform": 10,
      "min_selection_score": 60,
      "exclude_keywords": [],
      "prefer_keywords": []
    },
    "fallback_topics": ["人工智能", "大模型", "财经"]
  }
}
```

建议处理方式：

- 保留 `hot_topics` 作为兼容字段，转义为 `fallback_topics`。
- 真正的热点配置放在 `ScheduleConfig` 中，而不是继续堆在纯字符串数组里。
- 手动创建任务暂时不强制支持热点捕获，优先落在定时任务链路。

### 5.2 抓取模型

新增 `TopHubHotItem` 统一结构：

```python
{
  "source": "tophub",
  "category": "finance",
  "platform_name": "知乎热榜",
  "platform_path": "/n/mproPpoq6O",
  "title": "xxx",
  "url": "https://...",
  "rank": 1,
  "extra_text": "3255",
  "hot_value": 3255.0,
  "selection_score": 88.4,
  "selection_star": 5,
  "captured_at": "2026-04-02T23:00:00+08:00"
}
```

字段策略：

- `extra_text` 原样保留，避免信息丢失。
- `hot_value` 仅在 `extra_text` 可解析为数值时填充。
- `selection_score` 由系统计算。
- `selection_star` 为系统展示值，不代表 TopHub 原始字段。

### 5.3 评分规则

建议一期采用简单可解释的打分模型：

- 基础分：按排名倒序给分，排名越高分越高。
- 热度加分：`extra_text` 可解析为数字时参与加权。
- 平台权重：不同平台可配置不同权重。
- 分类匹配加分：命中目标题材分类时加分。
- 去重惩罚：标题高度相似时只保留分数更高的一条。

建议公式：

`selection_score = rank_score + hot_value_score + platform_weight_score + category_bonus - duplicate_penalty`

### 5.4 工作流接入

建议新增节点：

`initialize -> capture_hot_topics -> interpret_user_intent -> infer_style_profile -> ...`

节点职责：

- 当任务未开启热点捕获时，直接透传原始 `keywords`。
- 当任务开启热点捕获时：
  - 先抓取 TopHub 分类页 / 节点页。
  - 汇总并评分。
  - 选出最佳热点条目。
  - 将 `keywords` 更新为命中的热点标题。
  - 将 `hotspot_context` 写入工作流状态，供后续 prompt 使用。

建议新增状态字段：

- `hotspot_capture_config`
- `hotspot_candidates`
- `selected_hotspot`
- `original_keywords`

### 5.5 后续 agent 使用方式

后续文章生成链路不需要重写，只需要在 prompt 中补充热点上下文：

- 原始输入主题是什么
- 命中的热点标题是什么
- 命中的平台和榜单是什么
- 排名和热度是什么

这样 `interpret_user_intent`、`build_article_blueprint`、`generate_article` 都可以更明确地围绕热点标题展开。

## 6. 代码落点建议

后端：

- `api/models.py`
- `api/routers/schedules.py`
- `api/scheduler.py`
- `workflow/state.py`
- `workflow/graph.py`
- `workflow/skills/capture_hot_topics.py`（新增）
- `workflow/utils/tophub_client.py`（新增）
- `workflow/utils/hotspot_ranker.py`（新增）

前端：

- `frontend/src/api/index.ts`
- `frontend/src/pages/ScheduleManage.tsx`

测试：

- `tests/test_tophub_client.py`（新增）
- `tests/test_hotspot_ranker.py`（新增）
- `tests/test_scheduler_hotspot_capture.py`（新增）
- `tests/test_workflow_hotspot_capture.py`（新增）

## 7. 实施步骤

### 阶段 1：数据模型与接口

- 扩展 `ScheduleConfig`、`CreateScheduleRequest`、`UpdateScheduleRequest`。
- 为热点配置增加结构化字段。
- 做旧字段兼容和默认值填充。

### 阶段 2：TopHub 抓取能力

- 实现分类页抓取。
- 实现节点页抓取。
- 统一解析条目结构。
- 增加请求头、超时、重试和基础反爬保护。

### 阶段 3：热点筛选与回填

- 实现评分器。
- 实现标题去重。
- 选出最佳热点标题并回填到任务执行链路。

### 阶段 4：LangGraph 前置节点

- 增加 `capture_hot_topics` 节点。
- 把 `selected_hotspot` 写入状态。
- 将命中的标题作为下游文章生成主题。

### 阶段 5：前端配置页

- 把“热门话题”表单改为“热点捕获配置”。
- 支持多平台、多分类、多条件配置。
- 展示是否启用、命中平台数量、回退主题等关键信息。

### 阶段 6：测试与验收

- 补单测和集成测试。
- 验证未启用热点捕获时原逻辑不回归。
- 验证启用后能稳定命中并生成文章任务。

## 8. 风险与约束

### 8.1 站点反爬风险

- TopHub 当前可抓取，但未来可能调整反爬策略。
- 一期需明确加入失败回退：
  - 先回退到 `fallback_topics`
  - 再回退到 `schedule.name`

### 8.2 字段不统一风险

- 不同榜单的 `extra` 语义不同。
- 一期不要把 `extra` 直接当统一热度。
- 应以“排名优先，热度加权”为主。

### 8.3 平台路径维护成本

- 平台节点路径例如 `/n/...` 可能变化。
- 一期建议先允许人工配置平台路径。
- 后续再做自动发现和平台字典维护。

## 9. 验收标准

满足以下条件即可认为一期可实现：

1. 定时任务可配置多个 TopHub 平台节点。
2. 定时任务可配置多个题材分类。
3. 调度执行时会先抓取 TopHub 数据。
4. 系统能选出 1 条高分热点标题作为文章主题。
5. 后续文章 agent 能沿用现有流程完成生成。
6. 任务详情中可看到命中的热点标题、平台、排名和评分。
7. 抓取失败时不会中断整条链路，而是能自动回退。

## 10. 文档命名建议

本次 plan 文档已采用日期命名：

- `docs/2026-04-02-tophub-hotspot-capture-plan.md`

如果该方案评审通过，后续补充 `demand.md` 时，建议新增一个带日期的章节标题：

- `## 2026-04-02 TopHub 前置热点捕获需求`

这样可以和历史需求变更区分开，便于追踪。
