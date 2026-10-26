# 单机部署与运维指南（2C2G）

更新日期：2026-09-24
适用版本：`0.2.0`
运行环境：**Python 3.11**（`requirements.txt` 中的依赖已在该版本下验证）

本文档面向「少量用户、单台服务器自部署、2 核 2G 内存」的部署形态，说明依赖、配置、启动、内存预算、备份与故障处理。

---

## 1. 架构与运行形态

```
单台服务器 2 vCPU / 2 GB
  ├─ PostgreSQL 15+      业务数据（可选：不配置则用 data/*.json）
  ├─ Redis 7             access_token 缓存 + 搜索结果缓存（可选）
  └─ FastAPI（单进程 uvicorn，1 worker）
       ├─ APScheduler 触发器（cron / interval / once）
       ├─ LangGraph 工作流（进程内，受 WORKFLOW_MAX_CONCURRENCY 限流）
       └─ 内置调度循环（每 20 秒 tick 一次）
```

**为什么固定单进程 1 worker**：WebSocket 广播与任务运行态都在进程内存中；多 worker 会让同一任务的进度只推送到部分连接，也会重复触发定时任务。当前规模下单进程足够。

---

## 2. 依赖安装

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

`requirements.txt` 中的运行依赖：

| 依赖 | 用途 | 是否必需 |
|---|---|---|
| `fastapi` / `uvicorn` | Web 服务 | 必需 |
| `langgraph` / `langchain-openai` | 工作流与 LLM | 必需 |
| `httpx` / `trafilatura` / `beautifulsoup4` | 搜索、抓取、解析 | 必需 |
| `structlog` | 结构化日志 | 必需 |
| `sqlalchemy` / `psycopg2-binary` / `greenlet` | PostgreSQL 存储层 | 配置 `DATABASE_URL` 时必需 |
| `apscheduler` | cron 表达式解析 | 使用 cron 定时任务时必需 |
| `redis` | token 与搜索缓存 | 配置 `REDIS_URL` 时必需 |

> **关于运行环境**：本项目已统一到 **Python 3.11**，全部依赖（含 `greenlet`、`psycopg2-binary`）都有 3.11 的预编译 wheel，正常 `pip install` 即可，无需编译器。若在裸 Windows 上安装 `sqlalchemy` 或 `psycopg2` 时遇到需要 MSVC 的报错，改用预编译轮子即可：
> ```powershell
> pip install --only-binary=:all: greenlet sqlalchemy psycopg2-binary
> ```

> **存储层为何使用同步引擎**：SQLAlchemy 的异步扩展需要 `greenlet`，在早期开发环境（Python 3.9 + 无 MSVC）下无法编译，因此存储层采用同步引擎。这是一个**有意的设计选择**而非临时方案：`api/store.py` 与全部路由本来就是同步 API，单机数据量小，写入路径不经过异步驱动的额外往返反而更简单。迁移到 3.11 后异步引擎已可用，若后续并发规模上升，可再评估切换。

---

## 3. 配置

复制 `.env.example` 为 `.env`，按下表填写。所有配置都有安全默认值，**未配置的可选组件会自动降级而不是报错**。

### 3.1 必需配置

```ini
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
```

### 3.2 强烈建议配置

```ini
# 数据库：不配置则使用 data/*.json
DATABASE_URL=postgresql://wechat:password@127.0.0.1:5432/wechat

# 缓存：不配置则 token 存进程内存、搜索不缓存
REDIS_URL=redis://127.0.0.1:6379/0

# 定时任务时区
SCHEDULER_TIMEZONE=Asia/Shanghai
```

### 3.3 性能与资源

| 变量 | 默认 | 说明 |
|---|---|---|
| `WORKFLOW_MAX_CONCURRENCY` | 2 | 同时执行的工作流数量；超出排队 |
| `RESEARCH_CONCURRENCY` | 4 | 每任务并发检索数 |
| `IMAGE_CONCURRENCY` | 2 | 每任务并发生图数；内存吃紧降为 1 |
| `LLM_CONCURRENCY` | 3 | 进程级并发 LLM 上限 |
| `LLM_TIMEOUT_SECONDS` | 90 | 单次 LLM 超时 |
| `LLM_MAX_RETRIES` | 1 | LLM 重试次数 |
| `PLANNER_MODE` | `rules` | `rules` 不调 LLM / `auto` 仅模糊主题调用 / `llm` 总是调用 |
| `OPENAI_FAST_MODEL` | 空 | 快模型；留空则全部阶段用主模型 |

### 3.4 日志与告警

| 变量 | 默认 | 说明 |
|---|---|---|
| `LOG_MAX_BYTES` | 10485760 | 单个日志文件上限（10MB） |
| `LOG_BACKUP_COUNT` | 5 | 保留的轮转文件数 |
| `LOG_FORMAT` | 空 | 留空为可读文本，`json` 为结构化 JSON |
| `ALERT_WEBHOOK` | 空 | 失败告警 webhook（企业微信机器人等），留空关闭 |

---

## 4. 内存预算

目标常驻 ≤ 1.6 GB，为系统留出余量：

| 组件 | 预估占用 |
|---|---|
| OS + 基础服务 | ~250 MB |
| PostgreSQL | ~200 MB |
| Redis | ~40 MB |
| Python 应用（langchain/langgraph 导入较重） | ~600–800 MB |
| 峰值余量（2 个并发工作流 + 图片处理） | ~300 MB |

### PostgreSQL 调参（单机建议）

```ini
shared_buffers = 128MB
max_connections = 50
work_mem = 4MB
maintenance_work_mem = 32MB
```

应用侧连接池固定为 `pool_size=5, max_overflow=5`。

### Redis 调参

```ini
maxmemory 128mb
maxmemory-policy allkeys-lru
```

### 必须配置 swap

2 GB 内存在并发生图时可能出现瞬时峰值，请配置 2 GB swap 作为兜底：

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### 内存超预算时的降级顺序

1. `WORKFLOW_MAX_CONCURRENCY=1`
2. `IMAGE_CONCURRENCY=1`
3. PostgreSQL `shared_buffers` 降至 64MB
4. 关闭 Redis（清空 `REDIS_URL`）

---

## 5. 启动与停止

```powershell
# 启动（单进程，1 worker）
.\.venv\Scripts\python.exe -m uvicorn api.main:app --host 0.0.0.0 --port 8001

# 或直接运行入口脚本
.\.venv\Scripts\python.exe main.py
```

启动时会自动执行：

1. `bootstrap_storage()` —— 准备存储。配置了 `DATABASE_URL` 时创建缺失的表；若库为空且存在旧 `data/*.json`，自动导入并重命名为 `*.imported` 备份；随后从数据库加载。
2. `ensure_default_admin_user()` —— 确保存在默认管理员。
3. `reconcile_on_startup()` —— 校正定时计划：一次性计划若已过期会重新武装为立即执行；循环计划记录错过的次数并滚动到下一个真实时间点，不会补跑一批。
4. 启动调度循环。

前端构建：

```powershell
cd frontend
npm install
npm run build      # 产物在 frontend/dist
```

---

## 6. 健康检查

```bash
curl http://127.0.0.1:8001/api/health
```

```json
{
  "status": "ok",
  "database": "ok",
  "redis": "ok",
  "scheduler": "running",
  "version": "0.2.0"
}
```

字段含义：

| 字段 | 取值 | 说明 |
|---|---|---|
| `database` | `ok` / `disabled` / `error:<类型>` | `disabled` 表示未配置 `DATABASE_URL`（使用 JSON 存储） |
| `redis` | `ok` / `disabled` / `error:<类型>` | `disabled` 表示未配置或未启用 |
| `scheduler` | `running` / `stopped` | 调度循环状态 |
| `status` | `ok` / `degraded` | 数据库出错时为 `degraded` |

建议将 `/api/health` 接入外部监控（HTTP 200 判定）。

---

## 7. 备份与迁移

### JSON 存储

直接备份 `data/` 目录。注意 `data/*.imported` 是导入数据库后的历史备份，可以归档。

### PostgreSQL 存储

```bash
pg_dump -U wechat -d wechat -Fc -f wechat_$(date +%F).dump
```

恢复：

```bash
pg_restore -U wechat -d wechat --clean wechat_2026-09-24.dump
```

### JSON → PostgreSQL 迁移

1. 停止服务。
2. 备份 `data/` 目录。
3. 在 `.env` 中配置 `DATABASE_URL`。
4. 启动服务，观察日志中的 `legacy_import_done` 与 `storage_ready`。
5. 确认 `data/tasks.json` 等已重命名为 `*.imported`，且接口返回数据正常。

> 若某个实体类型在数据库与内存中都不为空，导入会被跳过（避免覆盖）；需要重新导入时请清空对应表。

---

## 8. 故障处理

| 现象 | 排查方向 |
|---|---|
| 任务长期停在「排队中」 | `WORKFLOW_MAX_CONCURRENCY` 已满。查看日志 `workflow_start` 是否有未结束的 run；必要时重启服务。 |
| 任务状态为 `cancelled` | 操作者通过 `POST /api/tasks/{id}/cancel` 取消。重试会清除取消标记。 |
| 定时计划没有触发 | 检查 `reconcile_on_startup` 日志中的 `schedule_missed_runs`；确认计划 `status=running` 且 `enabled=true`；cron 表达式需为标准 5 段式。 |
| 日志出现 `cron_parse_failed` | cron 表达式或时区不合法，接口会返回 400 并给出中文提示。 |
| 日志出现 `redis_unavailable` | Redis 不可达，已自动降级（token 存内存、搜索不缓存），60 秒后重试。 |
| 日志出现 `wechat_api_mock` | 任务未绑定发布账号且未配置 `WECHAT_APP_ID/SECRET`，返回的是**模拟**草稿。请配置账号或绑定发布目标。 |
| 日志出现 `alert_delivery_failed` | 告警 webhook 不可达；不影响任务本身。 |
| 草稿推送失败提示 `thumb_media_id` | 封面图上传失败。检查封面 URL 可访问、格式为 jpg/png/gif。 |
| 发布状态一直是 `publishing` | 微信侧仍在处理，或轮询次数用尽。可稍后核对公众号后台，草稿已保留。 |
| 磁盘占用增长 | 检查 `logs/`（已按 10MB × 5 轮转）与 `artifacts/generated_images/`（生成图片不会自动清理，建议定期归档）。 |
| **生成的文章结构千篇一律 / 正文像模板** | 最常见原因：结构化阶段落在了**推理模型**上，推理 token 耗尽输出预算导致 JSON 被截断，各阶段退回固定模板。检查：① `GET /api/config/model/effective` 的 `fast_tier_configured` 是否为 `true`、`warning` 是否为空；② 日志是否出现 `llm_structured_truncated`、`plan_article_angle_fallback`、`compose_draft_fallback`。处理：在「模型配置」页为**结构化模型**填写一个非推理模型（如 `deepseek-chat` / `qwen-plus` / `gpt-4o-mini`），或临时设 `LLM_STRUCTURED_TIER=strong` 并调大 `LLM_MAX_TOKENS_*`。 |
| 任务详情页出现「本次生成已降级」 | 说明蓝图或正文来自确定性模板，或来源不足。查看告警条中的具体原因与 `planning_state.blueprint_degraded_reason`、`writing_state.draft_degraded_reason`。 |
| 日志出现 `llm_structured_truncated` | 结构化输出被 token 上限截断，已按 `LLM_TRUNCATION_RETRY_FACTOR`（默认 2）放大预算重试一次。频繁出现说明上限偏小或模型是推理模型。 |
| 日志出现 `source_filter_applied` 且 `insufficient=true` | 过滤后可用来源不足（< `SOURCE_MIN_SURVIVORS`）。任务会继续生成但强制人工复核。若长期偏少，可放宽 `SOURCE_MIN_RELEVANCE` 或 `SOURCE_MIN_CHARS`。 |
| 日志出现 `hotspot_source_unavailable` | 热点原文未能抓取（跳转链接无法解析、原文被过滤或抓取失败），流程继续，结构主要依据搜索结果。可检查 `HOTSPOT_SOURCE_ENABLED` 与目标站点是否可访问。 |

---

## 9. 定时计划模式

| 模式 | 必需字段 | 说明 |
|---|---|---|
| `once` | `run_at` | 指定时间执行一次，执行后自动停止 |
| `interval` | `interval_minutes` | 每 N 分钟执行一次 |
| `cron` | `cron_expression` + `timezone` | 标准 5 段式表达式，如 `0 8 * * 1-5`（工作日 08:00） |

cron 表达式按 `timezone` 字段解释（默认 `Asia/Shanghai`），内部统一换算为 UTC 存储。计算出的下一次触发时间**严格晚于当前时间**，因此不会出现同一时刻反复触发。

---

## 10. 相关文档

- [文章生成链路提速与推送/发布链路优化](2026-09-24-article-chain-latency-and-publish-optimization.md)
- [工作流优化实施说明](2026-04-24-workflow-optimization-implementation.md)
- [爆文目标驱动的 Agent 架构](2026-07-18-viral-agent-architecture.md)
