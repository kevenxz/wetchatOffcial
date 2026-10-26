# 热点获取：提炼 TrendRadar 核心逻辑并内建定时拉取

日期：2026-10-22
状态：已实现（后端 436 → 499 项测试通过；前端 tsc/lint/20 测试文件全绿）
关联：`demand.md` §25、`docs/2026-10-21-logging-overhaul.md`

---

## 1. 问题与结论

> 能否使用 mcp 方式然后每日定时拉取数据，我可以把 github 上的项目重新跑起来

**MCP 与 GitHub Actions 互斥**，这是结论，不是网络问题：

| 证据（来自 `sansan0/TrendRadar/.github/workflows/crawler.yml`） | 含义 |
|---|---|
| `permissions: contents: read` | 只有读权限，**永远无法把数据 commit 回仓库** |
| 整个 workflow 无 commit/push 步骤 | 抓取结果不进仓库 |
| `timeout-minutes: 15` | 每轮最多 15 分钟即销毁 |
| 无监听端口 | **云端不存在 MCP 端点**；`trendradar-mcp:3333` 只存在于 Docker 形态 |
| 持久化靠 `S3_*` secrets | 要读得配 R2/OSS/COS 密钥 |

补充核实：你 fork 里那 7 个 `output/news/*.db`（2025-12-21~27）**是模板自带的示例数据**——
其 git SHA 与上游 `sansan0/TrendRadar` 完全相同，且 fork 的 `pushed_at`（2026-03-24）早于
它最后一次 Actions 运行（2026-08-09）。fork 的 `crawler.yml` 状态为 **`disabled_inactivity`**
（GitHub 对 60 天无活动仓库的自动禁用），与它自带的「7 天试用期」是两套不同机制。

因此按你的决定走**「提炼核心逻辑并嵌入本项目」**。

---

## 2. TrendRadar 的核心逻辑（源码实证）

`trendradar/crawler/fetcher.py`（约 200 行）——它并不爬各站 HTML，而是调用一个公开接口：

```
GET https://newsnow.busiyi.world/api/s?id=<platform_id>&latest
→ {"status":"success"|"cache","items":[{"title","url","mobileUrl","extra"},…]}
```

**实测：它的 16 个平台 id 全部可用（16/16，0 失败）**：

```
toutiao(30) baidu(30) wallstreetcn-hot(10) thepaper(20) bilibili-hot-search(30)
cls-hot(13) ifeng(12) tieba(30) weibo(30) douyin(30) zhihu(20) ithome(30)
jin10(28) fastbull(30) mktnews(30) xueqiu(30)
```

移植的 **6 条行为**（都是它踩过坑换来的）：

| # | 行为 | 为什么 |
|---|---|---|
| 1 | 校验 `status ∈ {success, cache}` | 上游返回缓存态；不校验会把异常响应当数据 |
| 2 | 重试 + **抖动退避** | 我们原用 TopHub 重试了 **429 次** |
| 3 | **非字符串标题直接跳过** | 它的 CHANGELOG 记录过 `'float' object has no attribute 'lower'` 崩溃 |
| 4 | 同平台标题去重并收集全部 rank | 判断"同一条反复上榜" |
| 5 | **域名安全校验**（HTTPS + hostname 后缀匹配） | 上游是第三方，注入 URL 会流进我们的抓取链路 |
| 6 | 请求间隔 + 抖动 | 16 平台并发时的礼貌与限流规避 |

> 第 3 条在实现时被我自己的测试抓到一次**漏移植**：`_clean_text(1.5)` 会得到 `"1.5"`，
> 于是浮点标题变成了"热点标题"。改为要求 `isinstance(title, str)` 后才与它一致。

---

## 3. GPL-3.0 处理

TrendRadar 是 **GPL-3.0**，而本仓库**当前没有 LICENSE 文件**。
所以：**不复制源码**（那会让整个仓库被迫 GPL-3.0 并需附对应源码），只移植**行为/方法**
（方法不受版权保护），并在 `newsnow_catalog.py` 与 `hotspot_providers.py` 的 docstring 中署名
newsnow（API 提供方）与 TrendRadar（平台目录与校验行为的来源）。

---

## 4. 改动

### 4.1 新来源 `newsnow`

| 文件 | 内容 |
|---|---|
| `api/models.py` | `HotspotSource` 增加 `newsnow` |
| `workflow/utils/newsnow_catalog.py`（新） | 16 个平台预设 + **每平台期望域名规则** |
| `workflow/utils/hotspot_providers.py` | `NewsNowHotspotProvider`（含上述 6 条行为）；`_platform_source()` 把**无 scheme 无斜杠的裸标识**识别为 newsnow；目录并入内置预设 |
| `frontend/src/api/index.ts` | `HotspotSource` 增加 `'newsnow'` |
| `frontend/src/pages/TaskCreate.tsx` | **修复真实缺陷**：原 `buildHotspotConfig` 丢弃 `source`/`provider_id` 且硬编码 `source:'tophub'`；现按平台保留并按多数推导顶层来源 |

### 4.2 定时拉取 + 快照缓存（`api/hotspot_snapshot.py`，新）

- `refresh_hotspot_snapshot()`：并发拉取全部配置平台 → 统一打分 → **原子落盘** `data/hotspot_snapshot.json`
- 复用上一轮加固过的 `persistence.write_json_file`（唯一临时名 + 每路径锁 + 退避重试 + fsync）
- `is_fresh()` / `due_for_refresh()` / `candidates_for()` / `split_covered_platforms()`
- 拿锁串行化，避免"定时刷新"与"手动刷新"重复打上游
- **写盘失败不丢数据**：保留内存快照并记 warning

### 4.3 接入调度器

挂到既有 `SchedulerEngine._tick()`（20 秒轮询循环）里，而非另起定时器。
刷新内部按 `HOTSPOT_REFRESH_INTERVAL_MINUTES` 自限速，且**吞掉自身异常**，不会阻塞或影响定时任务执行。

### 4.4 任务创建优先读快照

`capture_hot_topics_node`：
- 快照新鲜且覆盖请求平台 → **完全不打上游**
- **部分覆盖 → 只实时抓未覆盖的平台**（避免"快照只覆盖一半"导致候选池静默变小）
- 快照过期/缺失 → 走原有实时抓取（**行为不退化**）
- 快照候选仍要过任务自己的 `categories`/`exclude_keywords`/`min_selection_score`（快照是无过滤打分的）
- 新增日志字段 `snapshot_used` / `live_platform_count`

### 4.5 查询接口

- `GET /api/hotspots/snapshot`：可用性、新鲜度、覆盖平台、失败平台、候选数
- `POST /api/hotspots/snapshot/refresh`：强制刷新；上游异常返回 502

---

## 5. 实测验证

| 验证项 | 结果 |
|---|---|
| 16 平台可用性 | **16/16**（仅 `mktnews` 偶发返回 0 条） |
| 全量刷新 | **215 条原始 → 205 条候选，2.8 秒** |
| 快照落盘 | `data/hotspot_snapshot.json`，192 KB |
| 快照被任务复用 | **0 次上游调用**仍产出候选、选中热点、改写 keywords |
| 部分覆盖 | 只对未覆盖平台发起 **1 次**调用 |
| 快照是否新鲜/到期 | 新鲜时不重复刷新（`captured_at` 不变） |
| 域名校验 | 放行 `s.weibo.com`/`www.zhihu.com`；拦截 `weibo.com@evil.com` 等 4 种伪装 |

真实选中的热点（当日）：`西藏那曲巴青县发生7.0级地震`、`国乒女团2比3日本女团`、
`习近平出席纪念中国工农红军长征胜利90周年大会`。

---

## 6. 测试

新增 3 个文件（**+63 项**，后端 436 → **499 passed**）：

| 文件 | 项数 | 覆盖 |
|---|---|---|
| `tests/test_hotspot_newsnow.py` | 28 | 平台目录 16 项；注册表分派；裸标识识别；状态校验；重试恢复；**非字符串标题跳过**；标题去重 + `all_ranks`；`top_n` 截断；`extra.hover` → `extra_text`；**4 种域名伪装全部拦截**；HTTP 失败不抛 |
| `tests/test_hotspot_snapshot.py` | 24 | 新鲜/过期/到期判定；`1440` 每日周期；平台覆盖与**部分覆盖切分**；坏时间戳降级；并发刷新只打一次上游；单平台失败隔离；**上游全挂仍产出合法空快照**；重启后仍可读；文件损坏降级；**写盘失败保留内存快照**；调度钩子永不抛 |
| `tests/test_hotspot_snapshot_integration.py` | 11 | 快照新鲜 → **断言上游零调用**；过期 → 实时抓；部分覆盖 → 只抓未覆盖；任务过滤器仍生效；`/snapshot` 与 `/snapshot/refresh`；上游异常 → 502；`/platforms` 含 16 个 newsnow 且未挤掉 tophub |

---

## 7. 配置新增

| 键 | 默认 | 说明 |
|---|---|---|
| `NEWSNOW_API_BASE` | `https://newsnow.busiyi.world/api` | 可切自建 newsnow 实例 |
| `HOTSPOT_REFRESH_INTERVAL_MINUTES` | `60` | **设 1440 即为你要的「每日一次」** |
| `HOTSPOT_SNAPSHOT_MAX_AGE_MINUTES` | `180` | 超过则任务创建时实时抓 |
| `HOTSPOT_REFRESH_SOURCE` | `newsnow` | 定时刷新来源 |
| `HOTSPOT_REFRESH_PLATFORMS` | 空 = 全部 16 个 | 可缩小刷新范围 |
| `HOTSPOT_REFRESH_TOP_N` | `15` | 每平台条数上限 |

> **关于周期我按建议设了 60 分钟而非每日**（计划中已说明并获准）：热点衰减很快，
> 20 小时前的热点拿来做今天的文章会明显掉队；TrendRadar 自己也是每小时抓。
> 成本仅 16 次 GET。**若要每日，改成 1440 即可，无需改代码。**

---

## 8. 验收

```powershell
# 1) 单测
.\.venv\Scripts\python.exe -m pytest tests/test_hotspot_newsnow.py tests/test_hotspot_snapshot.py tests/test_hotspot_snapshot_integration.py -q

# 2) 真实刷新（写入 data/hotspot_snapshot.json）
#    预期 16 平台、~205 候选、数秒内完成
# 3) 接口
curl http://127.0.0.1:8001/api/hotspots/snapshot
curl -X POST http://127.0.0.1:8001/api/hotspots/snapshot/refresh
curl http://127.0.0.1:8001/api/hotspots/platforms   # 应含 16 个 newsnow
```

---

## 9. 已知限制与下一步（含实测证据）

### 9.1 打分并列：跨平台频次信号缺失（**最值得先做**）

实测本次快照：205 条候选、60 个不同分值，但**最高分 71.2 有 8 条并列**，其中 3 条是
**同一个故事**：

```
71.2  今日头条   西藏那曲巴青县发生7.0级地震
71.2  百度热搜   西藏那曲市7.0级地震
71.2  微博热搜   西藏7级地震
```

原因：newsnow **不提供热度值**，所以 `hot_value` 恒为 `None`；在 `rank` 与
`platform_weight` 相同时，`rank_hotspots` 无从区分。而 `pick_best_hotspot` 取
`candidates[0]`，排序键为 `(selection_score, -rank)`，同分时等价于**平台目录顺序**——
即当前选中结果"确定但无意义"。

**这正是 TrendRadar 用 `advanced.weight`（rank 0.6 / frequency 0.3 / hotness 0.1）解决的问题。**
我们已有现成数据：快照里一条标题出现在几个平台 = 跨平台频次。加一个频次项即可显著改善，
但计划中我明确承诺**本轮不动 `rank_hotspots` 权重**（先换源再调参，避免同时改两件事无法归因），
故留作下一步。

### 9.2 其他

1. `mktnews` 偶发返回 0 条（已正确计为 failed 并记日志，不影响其他 15 个平台）。
2. 平台 id 与 TrendRadar 版本可能漂移；id 已写入我们自己的目录并注明来源，上游新增不影响运行。
3. 未实现 Phase 3（MCP 适配器）：若将来本机跑起 `trendradar-mcp`，可加一个 adapter 复用同一套
   定时/缓存/降级骨架；其独有价值是 `rank_history` 的**排名时间线**（我们的快照对比也能近似实现）。
4. `data/hotspot_snapshot.json` 属运行期状态，已随 `data/` 由 .gitignore 覆盖。
