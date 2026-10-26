# 文章生成链路提速 与 推送/发布链路优化

更新日期：2026-09-24
状态：Phase A–H 全部已实现并通过测试（后端 263 passed，前端见各阶段说明）。

---

## 1. 背景与目标

系统原本已具备「热点捕获 → 研究 → 写作 → 双评审 → 配图 → 草稿箱」的完整链路，但存在两个实际问题：

1. **单篇任务耗时 4.5–11 分钟**，远超需求文档中「≤3 分钟」的目标。
2. **推送/发布链路不完整**：工作流推送节点读取全局环境变量凭据、与多账号架构冲突；只能入草稿箱，无法发布；封面之外的多张插图串行上传；access_token 仅存在进程内存中。

本轮优化目标：

- 单篇任务耗时降到 **1.5 分钟量级**（含缓存命中可进 1 分钟内），且不降低事实边界与传播质量线。
- 推送链路支持**草稿箱 + 直接发布双模式**，按任务绑定账号推送，全链路可追溯。
- 补齐存储生产化、工作流健壮性、调度生产化、前端页面、数据反馈与运维能力。

部署口径：单机 2C2G，PostgreSQL + Redis（两者均可选，未配置时自动降级）。部署细节见 [单机部署与运维指南](2026-09-24-deployment-and-operations-2c2g.md)。

---

## 2. 优化前的耗时画像

逐节点审查结论（LLM 往返按顺序串行）：

| # | 位置 | 问题 | 量级 |
|---|---|---|---|
| 1 | `workflow/nodes/run_research.py` | 每个 query **依次** 执行 search + fetch | 80–160s |
| 2 | `workflow/tools/image_generation.py` | `for brief in briefs` **逐张** 生图 | 20–120s |
| 3 | `workflow/agents/writer.py` | 草稿违规时**第二次全量 LLM 生成**（4000 tokens） | 60–120s（命中时） |
| 4 | `workflow/agents/writer.py` | 返工路径 `previous_draft={}`、`draft_violations=[]` **硬编码空值** → 模型看不到上一稿，等于重写 | 90–150s（命中时） |
| 5 | `workflow/graph.py` | `review_article_draft → review_viral_potential` 串行（两者只依赖草稿，互不依赖） | 20–40s |
| 6 | `workflow/graph.py` | 出图分支串行排在评审之后（同样只依赖草稿） | 20–100s |
| 7 | `workflow/agents/planner.py` | LLM 研究合同；但规则引擎已能确定性产出完整契约 | 15–30s |
| 8 | `workflow/agents/outline.py` | 传播策略与文章蓝图串行 | 20–40s |
| 9 | 全部 `ChatOpenAI(...)` | **未设 timeout / max_retries** → SDK 默认 600s + 2 次重试 | 长尾可挂 20 分钟 |
| 10 | 全部 LLM 节点 | 统一使用强模型，评审/策略类也一样 | 30–60s |
| 11 | 评审节点 | `max_tokens` 1400–1600，实际输出远小于上限 | 10–30s |

LLM 往返共 **6 次串行**（违规/返工时 7–8 次）。

---

## 3. Phase A：生成链路提速

### 3.1 新增基础设施

**`workflow/runtime_settings.py`**（新增）
集中式调优参数，全部由环境变量驱动，便于 2C2G 单机按需降级；并提供按事件循环缓存的 `get_semaphore()`（并发信号量），保证并发任务共享预算、测试的独立事件循环互不干扰。

**`workflow/model_factory.py`**（新增）
- `resolve_text_config(stage)`：按阶段路由强/快模型。强模型用于 `plan_article_angle`、`compose_draft`；快模型用于 `planner_agent`、`design_viral_strategy`、`review_article_draft`、`review_viral_potential`。
- 快模型未配置（api_key 为空或非字符串）时**自动回退**主模型，老配置无需改动。
- `build_chat_model()`：统一注入 `timeout` 与 `max_retries`，消除 SDK 600s 长尾。
- `llm_slot()`：按 `LLM_CONCURRENCY` 限流的异步上下文管理器。
- `model_context()`：统一结构化日志上下文，附带 `model_tier` 与 `stage`，密钥经掩码处理。

**`workflow/utils/draft_quality.py`**（新增）
把草稿质量规则与「机械可修」判定从 `writer.py` 抽出，供写作与独立修复节点共用：
- `draft_quality_violations()`：原有的长度/段落/小标题/重复段落/编辑语言检查。
- `classify_violations()`：区分**机械可修**（小标题含 URL 或来源标题、小标题过多、重复段落、编辑语言残留）与**内容级**（正文过短、段落不足）。
- `normalize_draft_content()`：确定性修复上述机械问题，返回修复项列表。
- `safe_heading()`：标题合法性判定（长度、URL、截断）。

### 3.2 并行化

**研究查询并发**（`workflow/nodes/run_research.py`）
- 同一轮内所有 query 的「search → fetch」改为 `asyncio.gather` 并发执行，由 `RESEARCH_CONCURRENCY`（默认 4）限流。
- **轮次语义保持不变**：第 1 轮全部结束后才做充分性评估，再决定是否进入第 2 轮。
- 单个 query 失败仍只追加 `research_gaps` 不中断；`_merge_results` 去重与 `search_runs` 结构不变。
- 收益：80–160s → 25–45s。

**生图并发**（`workflow/tools/image_generation.py`）
- briefs 改为并发 gather + `IMAGE_CONCURRENCY`（默认 2）信号量。
- 用 `gather` 保证**返回顺序与 brief 顺序一致**，插图编号 `[插图N]` 稳定。
- 保留「单张失败 → placeholder 兜底」语义，单张失败不影响其他图。
- 收益：20–120s → 12–60s。

**评审并发 + 结构短路**（`workflow/nodes/parallel_review.py`，新增）
- 文章评审与传播评审并发执行。
- **短路**：若文章评审判定硬性结构失败（`planning_language` / `source_heading` / `fragmented_structure`），**取消**在途的传播评审调用 —— 草稿必须重写，此时的传播分没有意义。
- **修复并发写冲突**：`review_viral_potential_node` 原先同时写 `viral_state` 与 `writing_state["viral_review"]`，与并发的文章评审写同一个 `writing_state` 键会冲突。现已删除该冗余写入（消费方 `quality_gate`、`targeted_revision` 均已优先读 `viral_state.review`）。
- 收益：成功路径省 1 次 LLM 往返（20–40s）；失败路径额外省下一次在途调用。

**传播策略与蓝图并行**（`workflow/agents/outline.py` + `workflow/nodes/merge_outline_strategy.py`，新增）
- 拆出 `outline_planner_base_node`：只产出蓝图与 outline_result，不合并传播策略。
- 新增确定性节点 `merge_outline_strategy`：承接原 `outline_planner_node` 中的合并逻辑（标题假设、核心承诺、selected_skill）。
- 图结构改为 `resolve_article_type` 并发分派到 `design_viral_strategy` 与 `outline_planner`，二者汇入 `merge_outline_strategy`。
- 收益：省 1 次 LLM 往返（20–40s）。

### 3.3 减少 LLM 往返与输出量

**planner 默认走规则**（`workflow/agents/planner.py`）
- 新增 `PLANNER_MODE`：`rules`（默认，完全不调 LLM）/ `auto`（仅当规则引擎把主题归类为 `other`、或搜索深度升级为 `strict` 时才调 LLM）/ `llm`（原行为）。
- 依据：`build_fallback_search_contract()` 已能确定性产出 `category`、`search_depth`、`query_plan`、`must_have_evidence` 与阈值，planner 其余输出本就完全确定性。
- 收益：省 1 次 LLM（15–30s）。

**模型分级**
- `api/models.py` 的 `ModelConfig` 新增 `text_fast`；`api/store.py` 从 `OPENAI_FAST_MODEL` 读取默认值。
- 前端「模型配置」页新增「快速模型（可选）」区块，留空即回退主模型。
- 收益：30–60s。

**`max_tokens` 收紧**
- `review_article_draft` 1400 → 600；`review_viral_potential` 1400 → 700；`design_viral_strategy` 1600 → 700；`planner` 新增上限 900。
- `plan_article_angle` 保持 1800、`compose_draft` 保持 4000（强模型、长输出）。
- 收益：10–30s。

> ⚠️ **后续修正（见第 16 节）**：上述收紧假设的是**非推理模型**。当主模型是推理模型时，
> 推理 token 计入 `completion_tokens`，这些上限会被推理过程耗尽，导致结构化 JSON 被截断、
> 每个阶段退回确定性模板（表现为「所有文章结构都一模一样」）。
> 现已改为按阶段可配置（`LLM_MAX_TOKENS_*`）并把结构化阶段默认路由到非推理模型。

### 3.4 抑制二次生成与返工

**确定性修复优先**（`workflow/agents/writer.py` + 新增 `workflow/nodes/normalize_draft.py`）
- 原先任何违规都会触发**第二次 4000-token 全量生成**。现在改为：先做确定性修复 → 复检 → **仅当仍有内容级违规**（正文过短、段落不足）才调 LLM 修复。
- 新增独立节点 `normalize_draft`（位于 `compose_draft` 之后、并发分派之前），兜住返工稿与降级稿残留的机械问题。
- `writing_state.draft_generation_mode` 新增 `model_revision`；`writing_state.draft_normalization` 记录已修复项，便于观测。
- 收益：多数任务省掉第二次全量生成（60–120s），并顺带降低返工率。

**返工定向化**
- 修复 `previous_draft` / `draft_violations` 硬编码空值：返工时传入当前草稿与返工指引，模型据此做定向修改而非重写。
- 返工调用 `max_tokens` 由 4000 降为 2500。
- 收益：返工 90–150s → 30–60s。

### 3.5 搜索缓存

**`workflow/utils/redis_client.py`**（新增）
惰性单例 Redis 客户端：未配置 `REDIS_URL`、连接失败或 ping 失败时返回 `None` 并进入 60s 冷却，全链路静默降级，绝不因 Redis 故障增加请求延迟。

**`workflow/utils/search_cache.py`**（新增）
- key = `search:v1:sha1(provider|query|limit)`（query 大小写与空白归一化）。
- `workflow/tools/search_web.py` 各 provider 调用改为经 `_call_provider_cached()`：命中直接返回，未命中则请求并写回。
- 收益：定时热点任务重复查询时 research 阶段再降 60–80%。

### 3.6 图结构（优化后）

```text
capture_hot_topics → intake_task_brief → planner_agent → analyze_hotspot_opportunities
  → plan_research → run_research（查询级并发）→ build_evidence_pack → resolve_article_type
      ├─→ design_viral_strategy ─┐          ← 两条分支深度均为 1
      └─→ outline_planner ───────┴─→ merge_outline_strategy
  → compose_draft → normalize_draft → plan_visual_assets
      ├─→ parallel_review（文章评审 ∥ 传播评审，含硬性失败短路）─┐   ← 深度 1
      └─→ image_agent（生图 + 图片审核）───────────────────────┴─→ quality_gate
                                              ├─ 通过 → assemble_article → push_to_draft
                                              └─ 返工 → targeted_revision → 写作/出图
```

两处 fan-out 都以「路径函数返回**多个目标节点**」实现（LangGraph 的 `add_conditional_edges` 支持返回列表）。

**fan-in 是真正的 barrier 的前提是两条分支深度相同**，这一点极其关键，详见第 15 节：`quality_gate` 有两条入边，只有当两条入边在**同一步**触发时才会等待双方；若一条分支更长，join 节点会在长分支尚未到达时就先行执行（拿到不完整的 `visual_review`），随后长分支到达时再执行一次，导致重复的返工/推送。因此 `plan_visual_assets`（确定性、几乎零耗时）被放在主干上，而把生图与图片审核合并进 `image_agent`，使两条分支都恰好只有一步。

---

## 4. Phase B：推送 / 发布链路优化

### 4.1 推送节点账号化（`workflow/tools/wechat_draft.py`）

- 新增 `publish_targets` 状态：由 API 层在创建任务时按绑定的账号写入（`CreateTaskRequest.account_ids`）。
- 推送节点优先按绑定账号逐个推送（凭据来自 account store），并按账号主题渲染 HTML。
- 全局 `WECHAT_APP_ID`/`WECHAT_APP_SECRET` **仅作降级**，且结果显式标记：
  - `draft_info.source = "env_fallback"`（环境变量降级）
  - `draft_info.mock = true`、`source = "mock"`（无任何凭据）
  - 操作者不会再把自己的 mock 结果误认为已推送。
- 单个账号失败不影响其他账号；全部失败才判定节点失败。

### 4.2 共享 access_token 缓存（`workflow/utils/wechat_token.py`，新增）

- token 缓存写入 Redis（`wechat:token:{app_id}`，TTL = `expires_in - 300`），进程重启后仍可复用，避免触发微信 token 日限额。
- Redis 不可用时回退进程内存缓存。
- 提供 `invalidate_access_token()`：微信返回 token 失效码（40001/40014/42001/42002）时清空缓存并重试。
- draft / publish / （后续 datacube）共用同一份缓存。

### 4.3 图片上传并发化（`workflow/utils/wechat_draft_service.py`）

- 封面仍按候选顺序串行尝试（必须命中第一个可用封面）。
- 文内插图改为 `asyncio.gather` 并发上传（并发度 3），**顺序保持**，与正文 `[插图N]` 占位一一对应。

### 4.4 草稿箱 + 直接发布双模式（`workflow/utils/wechat_publish.py`，新增）

- `submit_publish()`：调用 `freepublish/submit` 返回 `publish_id`。
- `poll_publish_status()`：轮询 `freepublish/get` 至终态；区分「成功 / 终态失败 / 仍在发布中（超时）」。
- `publish_failure_reason()`：把微信状态码翻译成运营可读原因（原创校验失败、平台审核不通过等）。
- `publish_policy` 扩展：`auto_publish`（默认 **false**）、`publish_retry_limit`、`publish_poll_interval_seconds`、`publish_poll_max_attempts`。
- 流程：`draft/add` 拿到 `media_id` → 若 `auto_publish` 则 submit → 轮询 → 落发布状态。
- **发布失败不影响草稿**：草稿已创建成功，`publish_status` 记为 `publish_failed` 并保留 `media_id`，运营可手动发布，无需重复建草稿。
- `publish_status` 取值：`draft_only` / `publishing` / `published` / `publish_failed`。

> ⚠️ 上线前需按微信开放平台当前文档核实：`freepublish` 对未认证账号是否可用、每日发布次数上限、`publish_id` 终态语义。当前实现遇到不支持的情况会回退为 `publish_failed` 并保留草稿，不会丢稿。

### 4.5 推送记录可追溯（`api/models.py`）

`PushRecord` 新增：`publish_status`、`publish_id`、`theme_name`、`attempt`。
工作流推送节点产出的记录由 `api/workflow_sync.py::_sync_push_records()` 按 `push_id` **去重后**合并进任务，断点续跑不会重复累加。

### 4.6 手动推送与定时推送同样支持发布

- `POST /api/articles/{id}/push`、`POST /api/articles/batch-push` 新增 `auto_publish` 参数。
- 定时任务推送读取该计划 `generation_config.publish_policy.auto_publish`，并统一写入带发布状态的推送记录。

### 4.7 主题解析统一（`api/store.py`）

新增 `resolve_theme_style(theme_name, strict=False)`，统一「全局风格 / 预设主题 / 自定义主题」的解析顺序，工作流推送节点与主题渲染使用同一份逻辑，避免预览与实际推送主题不一致。

---

## 5. 配置项

`.env.example` 新增：

| 变量 | 默认 | 说明 |
|---|---|---|
| `OPENAI_FAST_MODEL` / `OPENAI_FAST_API_KEY` / `OPENAI_FAST_API_BASE` | 空 | 快模型；留空则全部阶段用主模型 |
| `RESEARCH_CONCURRENCY` | 4 | 每任务并发查询数 |
| `IMAGE_CONCURRENCY` | 2 | 每任务并发生图数（内存吃紧降为 1） |
| `LLM_CONCURRENCY` | 3 | 进程级并发 LLM 上限 |
| `LLM_TIMEOUT_SECONDS` | 90 | 单次 LLM 超时 |
| `LLM_MAX_RETRIES` | 1 | LLM 重试次数 |
| `PLANNER_MODE` | `rules` | `rules` / `auto` / `llm` |
| `SEARCH_CACHE_ENABLED` | true | 搜索缓存开关 |
| `SEARCH_CACHE_TTL_SECONDS` | 21600 | 搜索缓存 TTL |
| `REDIS_URL` | 空 | 未配置则 token 与搜索缓存全部降级 |

发布相关配置位于任务的 `generation_config.publish_policy`（前端「直接发布到公众号」开关），而非环境变量 —— 发布是不可撤回操作，必须逐任务显式开启。

---

## 6. 测试

新增 8 个测试文件（后端）：

| 文件 | 覆盖 |
|---|---|
| `tests/test_model_factory.py` | 分级路由、快模型回退、timeout/retry 注入、密钥掩码 |
| `tests/test_draft_normalizer.py` | 机械修复各项、内容级违规保留、未知规则不静默丢弃 |
| `tests/test_run_research_parallel.py` | 查询并发（并发计数断言）、轮次语义、单查询失败容错 |
| `tests/test_image_parallel.py` | 生图并发、顺序稳定、单张失败兜底、关闭生图不调 provider |
| `tests/test_parallel_review.py` | 评审并发、硬性失败取消在途调用、传播评审失败不拖垮分支 |
| `tests/test_revision_targeted.py` | 返工传 `previous_draft`、token 预算切换、机械缺陷不触发二次生成、内容级违规仍升级 |
| `tests/test_planner_rules_mode.py` | `rules` 不调 LLM 且契约完整、`auto` 高敏升级、非法值回落、缓存 key/TTL/降级 |
| `tests/test_wechat_token_cache.py` | 内存命中、过期刷新、Redis 命中、写穿、故障降级、失效清理 |
| `tests/test_wechat_publish.py` | submit 成功/失败/缺 publish_id、轮询成功/终态失败/超时、失败保留草稿、默认不发布 |
| `tests/test_push_targets.py` | 账号绑定优先、发布开关透传、禁用账号跳过、mock/env 显式标记、部分失败隔离、全失败判定 |

同步更新：`test_compose_draft.py`、`test_review_article_draft.py`、`test_plan_article_angle.py`、`test_outline_planner.py`、`test_virality_agent.py`（patch 目标迁移到 `workflow.model_factory`；移除对 `writing_state["viral_review"]` 的断言）。

前端：`ModelConfig` 类型新增 `text_fast`，`PublishPolicyConfig`、`PushRecord`、`CreateTaskRequest` 同步扩展；「模型配置」页新增快速模型区块；「新建任务」新增「直接发布到公众号」开关。

**当前状态：后端 264 passed；前端 `tsc` / `lint` / `build` 全通过，`npm test` 64 passed / 1 skipped。**（Phase C–H 落地后的数据，见第 9–14 节。）

---

## 7. 预期收益

| 阶段 | 单篇耗时 |
|---|---|
| 优化前 | 4.5–11 min |
| 并行化（研究 + 生图 + 评审 + 分支） | 2.5–6 min |
| 再叠加 LLM 往返削减与模型分级 | 1.5–3.5 min |
| 再叠加返工抑制与超时收敛 | 1.2–2.5 min |
| 缓存命中时 | 0.8–2 min |

---

## 8. 回滚方式

所有优化项均可独立退回，无需改代码：

| 想退回 | 操作 |
|---|---|
| 恢复 LLM 版规划 | `PLANNER_MODE=llm` |
| 关闭并发（回到串行等价行为） | `RESEARCH_CONCURRENCY=1`、`IMAGE_CONCURRENCY=1` |
| 关闭搜索缓存 | `SEARCH_CACHE_ENABLED=false` |
| 关闭 Redis（token 回进程内存） | 清空 `REDIS_URL` |
| 恢复强模型跑全部阶段 | 清空 `OPENAI_FAST_MODEL` |
| 取消自动发布 | 任务 `publish_policy.auto_publish=false`（默认即 false） |
| 退回 JSON 文件存储 | 清空 `DATABASE_URL` |
| 关闭失败告警 | 清空 `ALERT_WEBHOOK` |
| 关闭工作流限流 | `WORKFLOW_MAX_CONCURRENCY` 调大 |

---

## 9. Phase C：存储生产化（PostgreSQL）

**设计**：每个实体一行「类型化标识列 + JSON payload」。

- 标识列（`id` / `created_at` / `updated_at` / `status` 等）用于索引与查询，`payload` 列保存完整的 Pydantic 模型 dump —— 富嵌套文档只有一个真相来源，同时获得真正的表、索引与查询能力。
- `api/db.py`：SQLAlchemy 2.0 声明式表定义（`tasks`、`topics`、`reviews`、`workflow_run_steps`、`accounts`、`users`、`schedules`、`article_stats`）、引擎管理、`init_db()`、`database_health()`。
- `api/persistence.py`：JSON 与数据库双后端。`persist_kind()` 会与上次落库快照做 diff，**只写真正变化的行** —— 一次任务进度事件只更新一行，而不是整表。
- `api/store.py`：保持全部原有函数签名作为兼容层，内部改为经由 persistence 读写；**路由层零改动**。
- `bootstrap_storage()`：配置了数据库时创建缺失表 → 把旧 `data/*.json` 导入空库 → 重命名为 `*.imported` 备份 → 从数据库加载。未配置数据库时维持原有 JSON 行为。

**关于异步引擎的偏离说明**：原计划使用 SQLAlchemy **异步**引擎。实现时开发环境为 Python 3.9，异步扩展所需的 `greenlet` 在缺少 MSVC 的 Windows 上无法编译，因此改为**同步引擎**。项目随后已迁移到 **Python 3.11**，异步引擎现已在技术上可行，但同步实现保留了下来：`store.py` 与所有路由本来就是同步 API，单机数据量小，写入路径不经过异步驱动的额外往返，反而更简单。若并发规模上升可再评估切换。

**索引**：`tasks(status)`、`tasks(created_at)`、`tasks(keywords)`、`topics(status)`、`reviews(status/target_id)`、`workflow_run_steps(task_id/run_id/created_at)`、`schedules(enabled/next_run_at)`、`article_stats(task_id unique/published_at)`。

**测试**：`tests/test_store_postgres.py`（16 项）—— 使用 SQLite 验证同一套模型：往返持久化、未变更行不重写、变更行更新、删除行移除、全部 8 类实体的列映射、JSON 一次性导入与备份、导入跳过非空容器、健康检查。

**测试隔离（顺带修复的一处隐患）**：`api.store` 的 `data/` 路径是相对工作目录解析的，因此测试既会覆盖开发者本地的 `data/*.json`，`bootstrap_storage()` 的用例还会把这些文件重命名为 `*.imported`。现在 `tests/conftest.py` 提供 autouse 夹具，把 `DATA_DIR`、全部路径常量与 `_KIND_REGISTRY` 重定向到每个用例自己的 tmp 目录，并在结束后精确还原。测试运行不再改动本地运行态数据。

---

## 10. Phase D：工作流健壮性

**断点续跑**：为每个节点包了一层守卫（`workflow/graph.py::_guard_node`）。
- 运行中把已成功完成的节点名累积进 `completed_nodes`，并随最终结果持久化到任务上（`TaskResponse.completed_nodes`）。
- 重试时 `retry_task` 把 `completed_nodes` 作为 `resume_state` 传入，已完成的节点直接返回空更新，**只重跑失败节点及其下游**，不再全量重跑。

**任务取消**：
- `api/task_control.py` 维护取消登记表与运行中 asyncio 任务映射。
- `POST /api/tasks/{id}/cancel` 记录取消、通过 Redis 发布（多进程时也能收敛）、并直接 `cancel()` 本地 asyncio 任务。
- 节点守卫在边界处检测取消，返回 `cancelled` 而不是 `failed`；所有条件路由都新增 `cancelled → ui_feedback` 的映射，因此不会在返工环里打转。

**并发闸门**：
- `WORKFLOW_MAX_CONCURRENCY`（默认 2）限制同时执行的工作流数量。
- 等待槽位的任务状态会置为 `queued`（排队中）并广播，而不是无限期停留在 `pending`。

**三个入口统一**：任务创建、重试、热点选题转任务现在都走同一个 `start_workflow_task()`，因此都受闸门、取消与发布目标绑定约束（此前热点转任务有自己的一份启动代码，绕过了这些机制）。

**测试**：`tests/test_task_cancel.py`（9 项）、`tests/test_checkpoint_resume.py`（4 项）。

---

## 11. Phase E：调度生产化

- `ScheduleMode` 新增 `cron`；`ScheduleConfig` 新增 `cron_expression` 与 `timezone`（默认 `Asia/Shanghai`）以及 `missed_runs`。
- 使用 APScheduler 的 `CronTrigger` 解析标准 5 段式表达式，按计划自带时区求值后统一换算为 UTC 存储。
- **严格未来语义**：计算出的下一次触发时间一定晚于当前时间。否则当 `next_run_at` 恰好等于当前时刻时，每个 tick 都会重新选中同一触发点并导致计划连续触发。
- **错过补偿**：`reconcile_on_startup()` 在启动时校正状态。一次性计划若已过期会重新武装为立即执行；循环计划只记录错过次数（`missed_runs`）并滚动到下一个真实时间点，**不会补跑一批**（避免开机即打满并发）。
- 校验顺序：先校验时区再校验 cron 表达式 —— cron 求值依赖时区，否则非法时区会报出令人困惑的 cron 解析错误。

**测试**：`tests/test_scheduler_cron.py`（14 项）。

---

## 12. Phase G：数据反馈闭环

**数据来源分级**：

1. **自动**：`POST /api/stats/sync` 调用微信 `datacube/getarticletotal`，按发布时间窗口拉取，再**按标题匹配**回任务。
2. **手动兜底**：`PUT /api/stats/{task_id}` 由运营录入。

**接口**：

| 接口 | 说明 |
|---|---|
| `GET /api/stats/overview` | 累计文章 / 发布 / 草稿、总阅读 / 分享 / 收藏 / 点赞 |
| `GET /api/stats/articles?range=7\|30` | 按日趋势（发布量 + 阅读量）与阅读量倒序的 Top 文章 |
| `GET /api/stats/{task_id}` | 单篇指标 |
| `PUT /api/stats/{task_id}` | 手动录入（可创建或更新） |
| `POST /api/stats/sync` | 同步微信数据，可指定单个账号 |

「已发布」的判定来自推送记录中 `publish_status == "published"` 的条目，因此统计口径与实际投递结果一致。

**测试**：`tests/test_stats_router.py`（13 项，含健康检查与告警）。

---

## 13. Phase H：运维能力

- **健康检查** `GET /api/health`：返回 `status` / `database` / `redis` / `scheduler` / `version`。数据库异常时整体为 `degraded`。
- **日志轮转**：`logs/app.log` 改为 `RotatingFileHandler`（默认 10MB × 5，可用 `LOG_MAX_BYTES` / `LOG_BACKUP_COUNT` 调整）。单机部署若不轮转，日志最终会写满磁盘并拖垮服务。uvicorn 自身的 logger 也接入同一处理器。
- **可选结构化日志**：`LOG_FORMAT=json` 输出 JSON。
- **失败告警**：`api/alerts.py`，由 `error_handler` 节点调用。支持企业微信等 JSON webhook，默认关闭；**每任务最多 3 条**以避免告警风暴；投递失败只记日志，绝不影响任务收尾。
- **部署文档**：[单机部署与运维指南（2C2G）](2026-09-24-deployment-and-operations-2c2g.md) —— 依赖、配置、内存预算、swap、备份与恢复、故障处理表。

---

## 14. 其他能力补齐

- **全局搜索** `GET /api/search?q=`：一次调用返回任务 / 文章 / 热点三类结果，供前端顶栏搜索使用。
- **文章在线编辑** `PUT /api/articles/{task_id}/content`：标题 / 摘要 / 正文 / 封面 / 插图。保存后**按当前主题重新渲染 HTML**，并把结果同时写回 `final_article` 与 `generated_article`，保证列表预览、主题渲染与后续推送内容一致。
- **任务状态扩展**：新增 `queued` 与 `cancelled`。
- **发布账号绑定落库**：`TaskResponse.publish_account_ids`，使重试与断点续跑仍能推送到同一批账号。

---

## 15. 并发编排的两处关键缺陷（已修复）

这两处缺陷在首次真正「走完整图」时才暴露：节点级单元测试各自通过，因为它们在隔离环境下直接调用节点，既不经过状态合并，也不经过 join 判定。修复后新增 `tests/test_graph_pipeline.py`，用桩节点完整走一遍图来锁死这两点。

### 15.1 并发分支写同一状态键 → 图直接崩溃

LangGraph 拒绝在同一步内对同一个 state key 写入多次：

```
InvalidUpdateError: At key 'status': Can receive only one value per step.
Use an Annotated key to handle multiple values.
```

而两处 fan-out 的分支都会返回 `status` / `current_skill` / `progress`：

- 规划分支：`design_viral_strategy_node` 与 `outline_planner_base_node`
- 稿件分支：`parallel_review_node` 与 `image_agent_node`（原 `plan_visual_assets_node`）

也就是说，**每一个真实任务都会在 `resolve_article_type` 之后立刻崩溃**。这类问题在只测单个节点时完全不可见。

**修复**：在 `workflow/state.py` 为共用簿记键声明 reducer：

| 键 | reducer | 语义 |
|---|---|---|
| `status` | `merge_status` | 终态优先：`failed` / `cancelled` 排名高于 `running`，避免失败被健康分支掩盖 |
| `progress` | `merge_progress` | 取双方最大值，进度条只前进不后退 |
| `current_skill` | `merge_current_skill` | 后写者胜（并发下本就没有唯一答案），紧随其后的 join 节点会立刻覆盖为确定值 |
| `error` | `merge_error` | 保留已有错误信息，不被空值擦除 |

`status` 选择「终态优先」而不是简单的「后写者胜」是刻意的：否则一个分支失败、另一个分支成功时，最终状态可能是 `running`，失败会被静默吞掉。

### 15.2 分支深度不等 → join 提前触发并重复执行尾部

即使解决了状态合并，第二处 fan-out 仍然是错的。修复前的实际执行顺序（桩节点实测）：

```text
14. parallel_review
15. plan_visual_assets
16. image_agent
17. quality_gate          ← 在 review_visual_assets 之前就执行了
18. assemble_article
19. review_visual_assets
20. push_to_draft
21. quality_gate          ← 再次执行
22. assemble_article
23. ui_feedback
24. push_to_draft         ← 草稿被推送两次
25. ui_feedback
```

原因是两条分支深度不同（`parallel_review` 深度 1，视觉分支深度 3）。LangGraph 的 join 只在**同一步触发的入边**之间等待，因此 `parallel_review` 结束时 `quality_gate` 立即执行，拿到空的 `visual_review`，据此做出错误的质量判定并开始推送；待视觉分支到达后又执行一次。

后果是**重复推送草稿**与**基于不完整状态的质量判定**，两者都会直接影响生产。

**修复**：把 `plan_visual_assets`（确定性、几乎零耗时）移到主干上，并将生图与图片审核合并进 `image_agent`，使两条分支都恰好一步深。修复后的实测顺序：

```text
14. plan_visual_assets
15. image_agent          ┐ 并发
16. parallel_review      ┘
17. quality_gate         ← 仅一次，且在两侧都完成后
18. assemble_article
19. push_to_draft
20. ui_feedback
```

图中每个节点都恰好执行一次，无重复。代价是 `plan_visual_assets` / `image_agent` / `review_visual_assets` 三个阶段在步骤追踪中合并为两个节点名；图片审核的结论仍完整写入 `visual_state.visual_review`，前端步骤轨道已同步调整。

### 15.3 回归防护

`tests/test_graph_pipeline.py` 新增 3 项测试：

1. 完整管线用桩节点走通，断言两处 fan-out 的四条分支都执行、两个 join 各执行一次、最终到达 `ui_feedback`；
2. 一条 fan-out 分支失败时整体必须落到 `error_handler` 且不得继续（验证 `merge_status` 的终态优先语义）；
3. 管线中途取消时必须以 `cancelled` 收尾且**不得推送草稿**。

`tests/test_checkpoint_resume.py` 另有一项测试专门断言规划 fan-out 的两条分支都执行，防止未来 LangGraph 版本不再支持「路径函数返回列表」这种 fan-out 写法。

---

## 16. 结构化输出可用性、来源质量与结构去模板化

### 16.1 为什么「优化后文章结构全都一样」

第 3.3 节把若干阶段的 `max_tokens` 收紧到 600–900，前提是**非推理模型**。实际部署的
`text` 层是推理模型 `deepseek/deepseek-v4-pro-0813`，而 `text_fast` 未配置。日志显示每个阶段都恰好用满上限：

```
plan_article_angle_fallback    completion_tokens=1800 (==上限)  "length limit was reached"
compose_draft_fallback         completion_tokens=4000 (==上限)
review_article_draft_fallback  completion_tokens=600  (==上限)
```

推理 token 计入 `completion_tokens`，模型把预算全部用于推理，没有输出可解析的 JSON。
由于流水线中**每个**阶段都使用 `with_structured_output`，结果是**全链路退回确定性模板**：

- `_build_source_driven_sections` 对每篇文章输出四个写死的标题
  （`先确认发生了什么` / `变化为什么会在此时出现` / `把变化放进真实场景` / `仍需验证的关键变量`）；
- `_build_fallback_draft` 输出固定文本表。

落库任务 `1132364a` 验证了该推断：`blueprint.framework` 取自技能的静态 `framework`、
`draft_generation_mode == "fallback"`、`blueprint.sections` 只有那组固定标题中的两个。

**教训**：降级只记 warning 时，一条「成功生成」的模板文章和一个真实生成结果在表面上无法区分。

### 16.2 修复

| 方向 | 措施 |
|---|---|
| 路由 | `text_fast` 语义改为**结构化输出模型**；所有结构化阶段默认走该层，支持 `LLM_STRUCTURED_TIER` / `LLM_STRONG_STAGES` 覆盖，未配置时回退主模型 |
| 预算 | 按阶段可配置（`LLM_MAX_TOKENS_*`），默认值按非推理模型留足 JSON 余量 |
| 截断 | 新增 `invoke_structured()`：分类 `truncated`/`other`、记录 `llm_structured_truncated`、按 `LLM_TRUNCATION_RETRY_FACTOR` 放大预算重试一次、否则抛 `StructuredOutputError` |
| 可见性 | 新增 `GET /api/config/model/effective`；任务详情页顶部告警条；模型配置页「结构化模型」字段与警告 |
| 来源 | 新增 `workflow/utils/source_filter.py` 四道关卡（质量/相关性/近重复/域名上限），接入 `run_research` 与 `build_evidence_pack`，掉因可审计；来源不足时继续生成但强制人工复核 |
| 结构 | 标题改由素材自身生成（共享工具 `workflow/utils/headings.py`）；蓝图 prompt 明确禁止固定占位标题并要求「两个故事不得共享同一组标题」 |
| 热点 | 新增 `fetch_hotspot_source` 节点：先解析榜单跳转链接、抓取热点原文、由其派生检索词并前插，蓝图以原文为主料 |

### 16.3 附带修复的真实缺陷

- `plan_research` 中 `int(item.get("priority") or 99)` 把合法的 `priority=0` 当作缺失值，
  使原文派生检索词被排到末尾；改为 falsy-safe 的 `_priority_of()`。
- `plan_article_angle.py` 中 `_build_fallback_blueprint` 被定义两次（后者覆盖前者），
  `_build_legacy_fallback_blueprint` 与 `_section_from_material` 已无引用；合计删除约 250 行死代码。
- 素材上下文由 12×900 字降为 6×400 字（热点原文单独放宽到 3000 字），
  直接把 `prompt_tokens` 从约 10.8k–13.4k 压下来，减少截断概率。

### 16.4 验证

后端 315 passed（新增 42 项），其中 `tests/test_blueprint_structure_varies.py`
直接用「两组不同素材必须产出不同标题集合」锁死本次回归；`tests/test_structured_truncation.py`
覆盖截断分类、重试与降级原因。前端 `tsc`/`lint`/`build` 通过，66 passed / 1 skipped。

> 注意区分：**相同素材**仍应产出相同结构（结构由证据决定，不由主题名决定）；
> 修复的是「**不同素材**也曾产出相同结构」。

---

## 17. 已知待处理项

1. **`freepublish` 权限与次数限制**需按微信最新文档核实后再开启自动发布。当前实现对不支持的情况回退为 `publish_failed` 并保留草稿，不会丢稿。
2. **邮件告警**仅预留 `ALERT_EMAIL` 配置位，尚未实现 SMTP 通道。
3. **Alembic 迁移**：当前建表由 `init_db()` 的 `create_all` 完成（幂等、适合全新部署）。若后续需要在线变更表结构，应补 Alembic 迁移脚本。
4. **生成图片不自动清理**：`artifacts/generated_images/` 会持续增长，建议定期归档或后续加清理策略。
5. **LLM 供应商并发限制**：`LLM_CONCURRENCY` 默认 3 是保守值。若供应商限额更高且 2C2G 内存允许，可调高以进一步缩短多任务同时运行的排队时间。

> 主题一致性问题已修复：`assemble_article_node` 现在按任务的 `article_theme` 渲染 `html_content`，与推送阶段使用同一份主题样式；运营在「内容管理」页保存编辑时也会按当前主题重新渲染。
