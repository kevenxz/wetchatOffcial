# 全项目日志优化

日期：2026-10-21
状态：已实现（后端 393 → 436 项测试通过）
关联：`demand.md` §24、`CLAUDE.md` 日志规范

---

## 1. 问题

> 优化整个项目的日志

审计对象：`logs/app.log`（5.1 MB / 13,678 行）+ `logs/app.log.1`（12.9 MB / 50,761 行）。

---

## 2. 诊断（全部实测，非推测）

### 2.1 正确性

**A1 测试正在写入生产日志** —— 最严重的一条。

`setup_logging()` 在 `api/main.py:43` **模块导入时**执行。任何 `from api.main import app`
的测试（所有 `TestClient(app)` 用例）都会装上生产的轮转文件 handler。

实测证据：跑一次 `tests/test_images_router.py` → 生产日志**增长 743 字节 / 8 行**，
`task-images-test` 出现 70 次、`task-no-visuals` 出现 14 次。
全量统计：**6,501 / 13,701 行（47%）来自 34 个测试 task_id**。

**A2 全仓库没有任何一处记录堆栈**：`exc_info` 使用次数 **0**。
321 条 error 行**全部没有 traceback**，`workflow_error error=boom` 无法定位。

**A3 密钥掩码正常**：2,525 处 `api_key_masked` 全部已掩码，**0 泄漏**（已加防回归测试）。

### 2.2 信噪比

| 项 | 实测 | 占比 |
|---|---|---|
| 模型 payload | 3.0 MB / 5.1 MB，单行最长 **30,309 字符** | **57% 体积** |
| httpx `HTTP Request:` | 2,208 行 | **16% 行数** |
| `skill_start`+`skill_done` | ~1,600 行 | 12%（**降噪依据存疑，见 §3.8**） |
| `persistence_flushed` | 750 行（每次 flush 一条 `affected=1`） | 5% |
| `ws_connected`+`ws_disconnected` | ~640 行 | 5% |

`MODEL_LOG_MAX_CHARS=12000` 是**逐字符串字段**截断，嵌套 dict 有 N 个字段就可远超上限。

`httpx` 有效级别实测为 **INFO**，全项目没有任何地方设置其级别。

### 2.3 可运维性

- **无关联 ID**：`merge_contextvars` 已配置，但全项目**无人调用 `bind_contextvars`**。
- **无级别开关**：文件与控制台硬编码 `INFO`，全仓库无 DEBUG 用法。
- **默认非 JSON**，但 `CLAUDE.md` 写明"使用 structlog 输出 JSON 格式结构化日志"——文档与实现不一致。
- **无查询入口**：`logs/` 无接口或界面。

### 2.4 一致性

`api/auth.py`、`api/store.py` 用 stdlib `logging`。实测这是**真实渲染缺陷**，不只是风格：

```
store_load_skipped kind=tasks error=boom        ← stdlib：无时间戳、无级别、无 logger 名
2026-10-21T14:42:27Z [warning] json_read_failed [probe.structlog] error=kaboom   ← structlog
```

`api/auth.py` 还有一处 `%s` 占位（`logger.warning("...username=%s", username)`）——
改用 structlog 后会原样打印 `%s`。

### 2.5 顺带发现：原子写失败（已一并修复）

生产日志中 27 次：

```
workflow_step_trace_create_failed error=[WinError 5] 拒绝访问。:
  'data\workflow_run_steps.tmp' -> 'data\workflow_run_steps.json'
```

根因是 `write_json_file` 的两个缺陷：

1. 临时文件名 `path.with_suffix(".tmp")` —— **所有并发写者共用同一个名字**；
2. `Path.replace` 只调用一次、无重试。Windows 上它映射到 `MoveFileEx`，
   目标被任何句柄占用即 Access Denied，而失败被降级成 warning 静默吞掉。

---

## 3. 改动

### 3.1 测试日志隔离（A1）

- `setup_logging()` 改为**幂等可重入**：只管理自己装的 handler（打标记），
  重复调用不会叠加文件 handler。
- 新增 `LOG_DIR`，`setup_logging(log_dir_override=...)` 让测试重定向文件日志。
- `tests/conftest.py` 新增 autouse fixture `isolate_logging`，把文件日志指向 `tmp_path`。
- 被污染的 `app.log.1` 已归档到 `logs/archive/`（不删除，用户可自行处理）。

**验证**：跑一次测试模块，仓库 `logs/app.log` 增长 **0 字节**。

### 3.2 不再破坏宿主的 handler（实现过程中自查发现）

最初用 `logging.basicConfig(force=True, handlers=[...])` 安装 handler。
`force=True` 会**移除所有已存在的 root handler**，包括 pytest 自己的日志捕获 handler。
已改为显式 `root.addHandler(...)`，并加测试
`test_setup_logging_leaves_foreign_root_handlers_alone` 守护。

### 3.3 异常必带堆栈（A2）

`workflow/` 内所有 except 块中的日志调用补上 `exc_info=True`
（容忍/降级类保持原级别；纯错误改用 `logger.exception`）。
`workflow/graph.py` 的 `workflow_error`/`workflow_failed` 原本已用 `logger.exception`。

**验证**：`/api/logs` 返回的错误行已带 `ValueError: boom` traceback。

### 3.4 模型 payload 分离（B1）

| 去向 | 内容 |
|---|---|
| `logs/app.log` | 元数据：`payload_chars`、`payload_sha256`、`payload_truncated`、`model`、`model_tier` |
| `logs/model.log` | 完整 payload，**JSON Lines**，每行一个独立 JSON 对象 |

- `MODEL_LOG_MAX_CHARS` 语义修正为**整份 payload**上限（不再是逐字段）。
- `_scrub_secrets()` 递归掩码任何 `api_key`/`secret`/`password`/`token` 键，两个去向都生效。
- `MODEL_LOG_PAYLOADS=false` 可整体关闭。
- `model.log` 的 handler 用裸 `%(message)s` formatter，**不依赖 structlog 处理器链**——
  这样改控制台格式永远不会破坏已记录的 payload。

### 3.5 第三方库静音（B2）

`httpx`、`httpcore`、`urllib3`、`openai`、`langchain*`、`trafilatura` 等固定
`max(level, WARNING)`。health 检查的 uvicorn access 行由 `_HealthCheckFilter` 过滤。

### 3.6 关联 ID（C1）

新增 `api/request_context.py`：

- `RequestContextMiddleware` 为每个请求绑定 `request_id`（接受并透传上游 `X-Request-ID`，
  截断到 64 字符），并**回写 `X-Request-ID` 响应头**，便于用户上报。
- 中间件在异常时先 `logger.exception("request_failed", ...)` 再抛出，
  因此失败请求也能按 id 追溯。
- `run_workflow()` 绑定 `task_id` + `run_id`（`run_id` 区分同一任务的重试），
  并在 `finally` 中解绑，覆盖 `CancelledError` 的提前 return 路径。
- 请求作用域只解绑 `request_id`，不影响后台任务自己绑定 `task_id`。

### 3.7 级别与格式（C2/C3）

- 新增 `LOG_LEVEL`（默认 INFO）。
- **文件默认 JSON、控制台默认可读文本**；`LOG_FORMAT` 可显式覆盖为 `json` 或 `text`。
  既满足 `CLAUDE.md` 的 JSON 约定，又保留人读的终端体验。
- `cache_logger_on_first_use` 改为 **False**：之前的 `True` 会让重配置（测试或改级别）
  **静默失效**。

### 3.8 降噪（B3/B4/B5）—— 含一处经核实的计划修正

降为 **DEBUG**（无诊断价值，失败路径仍按各自级别记录）：

| 事件 | 原 INFO 量 | 为什么是噪声 |
|---|---|---|
| `persistence_flushed` | 750 行 | 每次 flush 一条，几乎全是 `affected=1` |
| `ws_connected` + `ws_disconnected` | ~640 行 | 一次页面刷新即一对，无诊断价值 |

**计划中原本还要把 `skill_start`/`skill_done` 降为 DEBUG，执行时核实后改为不降。**

原因：计划里的依据是"二者合计约 1,600 行（12%）"。落实时逐个检查发射点后发现，
`search_web_node` 与 `fetch_and_extract_node` 都是**每次节点调用发一次**
（带 `query_count` / `url_count`），**不是**每查询/每 URL 一次：

```python
# workflow/tools/search_web.py:384
logger.info("skill_start", task_id=task_id, skill="search_web", status="running",
            query_count=len(search_queries))   # 一次调用一行
```

它们的高计数（306 / 288）反映的是**该日志窗口内的任务执行次数**，
而那个窗口**47% 的行来自测试**（即 A1 已修的缺陷）。

也就是说：**降噪依据本身是测试污染的产物**。修掉 A1 之后，
`skill_start`/`skill_done` 是每个任务约 10–15 对，正是 `app.log` 的叙事主线，
把它们降到 DEBUG 会让日志失去可读性。因此**保留 INFO**，并在此记录这一偏离。

（`persistence_flushed` 与 `ws_*` 不属此列：前者每次 flush 一条、后者每次连接一对，
与任务数无关，是真正的重复噪声。）

### 3.9 统一 structlog（D1）

`api/auth.py`、`api/store.py` 改用 `structlog.get_logger(__name__)`，字段化改写；
`api/store.py` 的 `store_load_skipped` 顺带补上 `exc_info=True`。
`%s` 占位改为结构化字段。现在 stdlib `logging` 只存在于 `logging_config.py`（配置模块本身）。

### 3.10 日志查询接口（C4）

新增 `api/routers/logs.py`（**只做后端，不加界面**，按选择）：

```
GET /api/logs?file=app|model&level=&task_id=&request_id=&q=&limit=&offset=
GET /api/logs/files
```

安全约束：`file` 是**白名单键**（调用方永远不提供路径）；从**文件尾部**反向读取并限制扫描字节数
（不在 2C2G 上把 10 MB 读进内存）；输出**再过一遍脱敏**（历史行可能含明文）；
沿用既有 Token 鉴权。

### 3.11 修复原子写（E）

`api/persistence.py::write_json_file`：

1. **每个路径一把锁**（`_path_lock`）——进程内写者排队，而不是互相抢占。
   这是关键修复：压测显示仅靠重试，6 个并发写者会耗尽重试并**丢失写入**。
2. 临时文件名唯一化：`{name}.{pid}.{uuid8}.tmp`。
3. `Path.replace` 带退避重试（0.05/0.15/0.4 s，共 4 次尝试）。
4. `flush()` + `os.fsync()`，替换前确保已落盘。
5. 失败时清理临时文件并以 `logger.error(..., exc_info=...)` **抛出**，不再静默降级。

---

## 4. 实测验证

| 验证项 | 结果 |
|---|---|
| 跑测试对生产日志的增量 | **0 字节**（此前 743 字节/模块） |
| 主日志是否含 prompt 正文 | **否**；含 `payload_chars`/`payload_sha256` |
| `logs/model.log` 是否是完整 payload | **是**，JSON Lines，密钥已掩码 |
| 主日志是否含 `HTTP Request:` | **否**（此前 2,208 行） |
| 主日志每行是否可 `json.loads` | **是**（含 `event`/`level`/`logger`/`timestamp`） |
| 异常是否带 traceback | **是** |
| `request_id` 是否出现在日志与响应头 | **是** |
| 重复调用 `setup_logging` 是否重复行 | **否**（handler 数不变） |
| 6 线程并发写同一 JSON 是否失败 | **否**，且无 `.tmp` 残留 |
| 模拟 WinError 5 是否恢复 | **是**（第 2 次尝试成功） |

**压测复现了生产原故障**：6 个并发写者对同一文件写入时，确实复现
`[WinError 5] 拒绝访问`，与生产日志中的 27 次完全一致——确认根因判断正确。

---

## 5. 测试

新增 3 个测试文件（+40 项），后端合计 **393 → 436 passed**：

| 文件 | 覆盖 |
|---|---|
| `tests/test_logging_config.py`（20） | 幂等性；不破坏宿主 handler；`LOG_LEVEL` 生效；第三方库静音；JSON 行可解析；四要素齐全；payload 分离与整份上限；密钥脱敏；`MODEL_LOG_PAYLOADS` 开关；contextvars 绑定/不泄漏；**测试不写入仓库日志目录** |
| `tests/test_logs_router.py`（13） | 尾读倒序；行数上限；级别/task/关键字过滤；未知 file 键 400；**5 种路径穿越均被拒**；limit 上限 422；文件大小；输出再脱敏 |
| `tests/test_persistence_atomic_write.py`（7） | 正常写入；无 `.tmp` 残留；**临时名唯一**；**6 线程并发不失败不损坏**；瞬时 WinError 5 重试恢复；持续失败时抛错并清理；退避总时长 < 1s |

---

## 6. 配置新增（`.env.example`）

| 键 | 默认 | 说明 |
|---|---|---|
| `LOG_LEVEL` | `INFO` | 全局级别 |
| `LOG_DIR` | `logs` | 主日志目录 |
| `LOG_FORMAT` | 空 = 文件 JSON / 控制台文本 | 可设为 `json` 或 `text` |
| `MODEL_LOG_PAYLOADS` | `true` | 是否落盘完整 payload |
| `MODEL_LOG_MAX_BYTES` | `20971520` | payload 文件轮转上限 |
| `MODEL_LOG_BACKUP_COUNT` | `3` | payload 备份数 |
| `MODEL_LOG_MAX_CHARS` | `12000` | **整份 payload** 上限 |

`LOG_MAX_BYTES`/`LOG_BACKUP_COUNT` 保持不变。

---

## 7. 验收命令

```powershell
# 1) 测试不再污染生产日志（必须为 0）
$b = (Get-Item logs\app.log).Length
.\.venv\Scripts\python.exe -m pytest -q
(Get-Item logs\app.log).Length - $b

# 2) 主日志无 payload、无 httpx
Select-String -Path logs\app.log -Pattern 'HTTP Request:'   # 0 命中
Select-String -Path logs\app.log -Pattern '"payload"'       # 0 命中
Test-Path logs\model.log                                     # True

# 3) 异常带堆栈
Select-String -Path logs\app.log -Pattern 'Traceback'

# 4) 按任务/请求追溯
curl "http://127.0.0.1:8001/api/logs?task_id=<id>&level=warning"
```

---

## 8. 已知限制与后续

1. **运行中的服务需要重启**才能生效：新配置在导入时读取，当前进程仍持有旧的 handler。
   仓库中现存的 `app.log`（约 7 MB）仍含历史污染，会随轮转自然消失；
   `app.log.1` 已归档到 `logs/archive/`。归档文件建议确认后手动删除。
2. **`skill_start`/`skill_done` 保留在 INFO**（偏离计划，理由见 §3.8）：
   核实后确认它们每个任务只发 10–15 对，是日志的叙事主线；
   计划中的降噪依据来自测试污染，修掉 A1 后不再成立。
   若在真实生产流量下观察到此二者占比过高，再单独降级即可。
3. **JSON 行的键顺序**：`event`/`level`/`logger`/`timestamp` 出现在 kwargs 之后。
   对解析无影响（JSON 对象无序），但 `tail -f | jq` 时时间戳不在行首。
4. **`/api/logs` 无界面**（按选择）：仅后端接口。
5. **单机磁盘**：主日志 5×10 MB + payload 3×20 MB = 最多约 110 MB。
   `GET /api/logs/files` 会返回总量，便于加监控。
