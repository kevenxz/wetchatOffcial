# 爆文目标驱动的 Agent 架构（v2）

## 1. 目标函数

系统不再以“成功生成并推送文章”为最高目标。新的北极星目标是：在不牺牲事实边界的前提下，提高文章获得合格点击、完整阅读、收藏与有效转发的概率。

爆文不是一个可事先保证的结果，因此系统只优化可控的领先指标，并保留发布后的真实数据作为后续学习信号：

| 维度 | 权重 | 回答的问题 |
| --- | ---: | --- |
| 标题点击力 | 18% | 标题是否有真实信息增量、明确冲突或收益？ |
| 首屏留存 | 18% | 前 120 字是否快速兑现标题并建立阅读张力？ |
| 观点新颖度 | 15% | 是否提供非显然判断，而非新闻复述？ |
| 读者共鸣 | 14% | 是否与目标读者的损失、机会或选择直接相关？ |
| 分享动机 | 15% | 读者是否有明确对象和理由转发？ |
| 证据可信度 | 12% | 核心判断是否有高可信、多源证据支撑？ |
| 阅读流畅度 | 8% | 移动端结构、段落与转场是否顺畅？ |

默认传播质量线为 78 分，可在任务 review policy 中配置为 60–95。

## 2. 分层架构

```text
API / WebSocket / Scheduler
          │
          ▼
Application Orchestrator (LangGraph)
  ├─ 运行状态、重试、检查点、人工闸门
  ├─ 节点输入输出追踪
  └─ 质量仲裁与定向返工路由
          │
          ▼
Domain Agents
  ├─ Topic Agent          选题优先级
  ├─ Research Agent       检索计划与证据包
  ├─ Virality Strategist  读者张力、传播承诺、差异角度
  ├─ Outline Agent        标题假设与证据映射
  ├─ Writer Agent         按合同写作
  ├─ Editorial Reviewer   事实、结构与表达审查
  ├─ Virality Critic      独立传播潜力反思
  └─ Visual Agent         封面与正文配图
          │
          ▼
Infrastructure Adapters
  ├─ LLM / Image Model
  ├─ Search / Fetch / RAG
  ├─ WeChat API
  └─ Task / Run / Editorial Memory Store
```

节点之间只交换结构化合同，不依赖另一个 Agent 的内部推理。`viral_state.strategy` 是创作目标合同，`viral_state.review` 是独立评审合同，`quality_state` 只负责仲裁。

## 3. Agentic Design Patterns 映射

| 设计模式 | 项目中的实现 |
| --- | --- |
| Prompt Chaining | 选题 → 研究 → 传播策略 → 大纲 → 写作 → 双重评审 → 发布 |
| Routing | 文章类型路由、质量门禁、写作/视觉定向返工 |
| Planning | Planner 产出研究合同、质量阈值和资源策略 |
| Tool Use | 搜索、抓取、图片生成、微信公众号草稿 API |
| Reflection | Editorial Reviewer 与 Virality Critic 独立于 Writer |
| Multi-Agent Collaboration | Agent 通过共享结构化状态协作，职责与目标分离 |
| Goal Monitoring | 七维传播分、文章分、视觉分和证据缺口共同驱动闸门 |
| Human in the Loop | 超过返工预算、证据缺口或风险阻断时进入人工复核 |
| Exception Recovery | 节点级追踪、失败终止、断点重试与确定性降级策略 |
| Learning & Adaptation | 下一阶段接入发布后数据，形成账号级 editorial memory |

## 4. 新工作流

```text
热点捕获 → 任务简报 → 总体规划 → 选题评估
    → 研究规划 → 多轮检索 → 证据包 → 类型路由
    → 传播策略 → 文章大纲 → 写作成稿
    → 编辑审核 → 传播评审
    → 图片规划 → 图片生成 → 图片审核
    → 质量门禁 ─┬─ 通过 → 组装 → 草稿箱/人工确认
                ├─ 写作弱 → 定向返工 → 写作成稿
                ├─ 视觉弱 → 定向返工 → 图片生成
                └─ 超预算/高风险 → 人工复核
```

## 5. 迁移路线

本次落地的是第一阶段基础闭环：传播策略合同、独立传播评审、质量门禁接入、定向返工和编辑部评分 UI。

后续阶段按以下边界推进：

1. 将超长 `plan_article_angle.py` 拆成纯领域服务、Prompt adapter 与 fallback policy，消除重复定义。
2. 用数据库替代 JSON 文件存储，引入正式 checkpoint、outbox 和幂等发布键。
3. 接入公众号发布后的阅读、分享、收藏与关注数据，建立账号级内容记忆与离线评估集。
4. 增加标题多候选锦标赛、反方评审和账号风格 RAG；未经真实数据验证，不自动修改线上权重。
5. 将任务详情页从原始状态转储逐步收敛为“决策、证据、成稿、发布”四个工作区。

## 6. 约束

- “爆文分”是传播潜力估计，不是流量承诺。
- 可信度是硬约束；点击力不得通过夸大、恐惧或伪造确定性换取。
- Writer 不给自己打分；Critic 不重写全文；Quality Gate 不承担创作。
- 文章结构不是合同：蓝图中的章节只是候选叙事节点，Writer 可以合并、重排、改名或舍弃；只有事实、禁写结论和证据边界是硬约束。
- 所有自动返工都有轮次上限，失败与高风险状态必须可见、可追溯、可人工接管。
