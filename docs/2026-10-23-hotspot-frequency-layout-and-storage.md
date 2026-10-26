# 热点排序补强、长文本撑破页面修复、存储现状核查

日期：2026-10-23
状态：已实现（后端 499 → 521 项测试通过；前端 144 → 156 项通过）
关联：`demand.md` §26、`docs/2026-10-22-hotspot-newsnow-and-scheduled-refresh.md` §9.1

---

## 1. 三个需求的对应结果

| 需求 | 结果 |
|---|---|
| 「加上去」——补上跨平台频次信号 | ✅ 已实现，实测最高分并列从 8 条降到 3 条（且那 3 条是同一个故事） |
| 页面适配：长文本应省略号，现在把页面撑坏 | ✅ 已修复 5 个页面/组件 + 加了回归守卫 |
| 目前的数据库 pgsql 是否有使用 | ❌ **没有使用**；并顺带查到 JSON 存储存在真实的写放大问题（见 §4） |

---

## 2. 跨平台频次信号

### 2.1 问题（上一轮已记录的证据）

`newsnow` 不提供热度值 → `hot_value` 恒为 `None`。只有 `rank` 与 `platform_weight` 时，
真实快照里**最高分 71.2 有 8 条并列**，其中 3 条是同一个故事：

```
71.2  今日头条   西藏那曲巴青县发生7.0级地震
71.2  百度热搜   西藏那曲市7.0级地震
71.2  微博热搜   西藏7级地震
```

`pick_best_hotspot` 取 `candidates[0]`，同分时等价于**平台目录顺序** —— 确定但无意义。

### 2.2 实现

在 `hotspot_ranker.py` 增加覆盖广度项：

| 组件 | 上限 | 说明 |
|---|---|---|
| `frequency_score` | 12.0 | 每多一个平台 +6，封顶 12（即 3 个平台即满） |

候选上新增三个可审计字段：`frequency_score`、`cross_platform_count`、`source_platforms`。

**两个相似度阈值刻意不同**（这是本次最关键的设计决定）：

| 常量 | 值 | 用途 | 误判代价 |
|---|---|---|---|
| `DUPLICATE_SIMILARITY` | 0.90（未变） | 决定哪些**行存活** | 删掉一条真实不同的故事，**不可恢复** |
| `CROSS_PLATFORM_SIMILARITY` | 0.65 | 只决定**看起来被多少平台报道** | 多给一个**有上限**的分，绝不删行 |

真实跨平台标题几乎不会逐字相同，所以宽松阈值是必需的：三条地震标题两两相似度约 0.76，
严格阈值会把它们当成三条无关新闻。

### 2.3 自己的测试抓到的实现 bug：分组必须可传递

第一版按"每个标题与其他标题逐一比对"（星形）计算覆盖，实测得到 `[2, 3, 2]` 而不是 `[3, 3, 3]`。
原因：三条标题构成**链**而非星形 ——

```
A 西藏那曲巴青县发生7.0级地震  ──0.78──  B 西藏那曲市7.0级地震  ──0.63──  C 西藏7级地震
A ←──────────────── 0.53 ────────────────→ C        （A 与 C 互不相似）
```

B 是**桥**，而 A 与 C 从不匹配。已改为**并查集连通分量**（可传递分组），
并加了长度预筛（短/长比 < 0.45 直接跳过）把复杂度控制在实用范围。

另外补了一条规则：**标题短于 4 字必须完全相同**——
"召回" 与 "汽车召回" 的相似度是 0.67，会被误判为同一故事。

### 2.4 实测（同一份真实快照，205 条候选）

| 指标 | 修改前 | 修改后 |
|---|---|---|
| 最高分并列 | **8** 条（3 条同一故事） | 3 条（**全部是同一故事，故无害**） |
| 不同分值数 | 60 | **70** |
| 跨平台故事得分 | 71.2（与单平台并列） | **83.2**（比单平台高 12 分） |
| 最大覆盖平台数 | — | **4** |
| 20 条候选耗时 | — | **425 ms** |

`西藏那曲…地震` 现在占据前 4 名（4 个平台），随后是 `国乒女团` 故事（weibo + bilibili 正确合并为同一故事，x3）。

并列不再影响结果：剩下并列的 3 条**本来就是同一个故事**，选中任何一条都是正确答案。

---

## 3. 长文本撑破页面

### 3.1 根因

`ArticleManage` 把完整标题与**最长 200 字**的摘要直接渲染进 `<h2>` / `<p>`。
栅格列本身是对的（`minmax(0, 1fr)` + `min-width: 0`），但**文本元素自己没有截断**，
于是卡片高度随内容无限增长，把周围栅格撑坏。

同样的写法还出现在 4 处：`TopicCenter`、`TaskDetail`、`ViralityScorecard`、`StatusRail`。
其中 **`ViralityScorecard` 风险最高**——它渲染的是 LLM 生成的 `core_promise` / `audience_tension`，
天然就是成段文字。

### 3.2 实现：设计系统级原语，而不是逐页打补丁

新增 `components/layout/TruncatedText.tsx` + `layout.module.css` 的 `.truncated` / `.clamp1..4`：

```tsx
<TruncatedText as="h2" lines={1}>{title}</TruncatedText>
<TruncatedText as="p" lines={2}>{summary}</TruncatedText>
```

三个要点：

1. **`min-width: 0`** —— 这是"设了 `text-overflow` 却不出现省略号"的常见原因：
   flex/grid 子项默认 `min-width: auto`，拒绝收缩到内容宽度以下，省略号永远不生效。
   原语把它一并处理，调用方不必知道这个坑。
2. **`overflow-wrap: anywhere`** —— 长 URL / 长 ID 这类无空格串不能溢出容器。
3. **完整值保留在原生 `title` 提示**里，而不是再套一个 Tooltip 组件 ——
   不增加每行的 DOM 节点，也不引入布局副作用。

个例修复：`TopicCenter` 标题 2 行、摘要 3 行；`TaskDetail` 标题 2 行；
`ViralityScorecard` 2/3 行；`StatusRail` 2/2 行。

### 3.3 顺带清理

`ArticleManage` 原有两处内联样式：
- `Empty style={{ padding: 72 }}` → 改用设计系统的 `EmptyState` + `.emptyPad`
- `TextArea style={{ resize: 'none' }}` → `.textAreaFixed`

因此该文件**已从 `noInlineStyle` 待迁移清单移除**（守卫的"清单不得含失效条目"检查主动报错提醒了我，这正是棘轮设计的目的）。

### 3.4 回归守卫

新增 `components/layout/__tests__/textOverflow.test.ts`，规则：
**`pages/` 与 `components/` 内不得出现裸的 `<h1-h3>{动态值}` 或 `<p>{动态值}`。**

- 静态字面量（`<p>确认后会将当前文章渲染为微信样式 HTML…</p>`）不受限 ——
  长度在评审时就确定，不会随接口数据变化。
- 允许清单只放了 `WorkbenchShell`（渲染导航元数据 `contextTitle`/`contextDescription`，
  在导航表里写死一次，不随数据变化），并且**有一条测试专门验证该条目仍然成立**，
  避免允许清单腐烂成"永远豁免"。

---

## 4. PostgreSQL 现状核查（结论：未使用）

### 4.1 事实

| 检查项 | 结果 |
|---|---|
| `.env` 中 `DATABASE_URL` | **未设置** |
| `api/db.database_health()` | `disabled` |
| SQLAlchemy / psycopg2 是否安装 | **都装了**（sqlalchemy 2.1.3、psycopg2-binary 2.9.13） |
| 是否存在 `.db` / `.sqlite` 文件 | **没有** |
| 数据实际位置 | 全部在 `data/*.json` |

也就是说：**代码支持、驱动已装、但从未启用**。当前所有读写都走 JSON 文件后端。
`api/persistence.py` 的双后端设计是有意为之（`DATABASE_URL` 一设即切），并非遗留代码。

### 4.2 顺带查到的真实问题：JSON 后端的写放大

启用与否不只是"要不要上数据库"，实测发现 JSON 后端已有明显代价：

```
data/workflow_run_steps.json
  磁盘大小 : 32.9 MB
  记录数   : 101
  JSON 内容: 16.5 MB   ← indent=2 让磁盘占用约为内容的 2 倍
  单条平均 : 167 KB（最大 508 KB，最小的仅 7 KB）
```

单条记录存储了**三份几乎相同的工作流状态快照**：

```
input_state  157 KB
output       169 KB
state_after  182 KB
```

（状态里含 `extracted_contents` 全文与 `generated_article`，因此随文章长度增长。）

而 `write_json_file` 是**整文件重写**，于是：

> **每个节点步骤都要重写整个 32.9 MB 文件**；一个 20 节点的任务产生约 **660 MB** 磁盘写入。

这同时解释了上一轮日志里反复出现的
`[WinError 5] data\workflow_run_steps.tmp -> workflow_run_steps.json`：
写窗口太长（33 MB），Windows 上与并发写者/杀软抢占目标文件的概率随之升高。

### 4.3 建议（两个独立的问题，别混为一谈）

1. **启用 Postgres 解决的是"整文件重写"**：按行 upsert，一次步骤只写一行。
   前提是目标机器有 Postgres 实例（本机未安装/未配置）。步骤轨迹与任务本身都是高写入频率数据，
   换库收益最直接。
2. **但换库不解决"三份快照"**：`input_state` / `output` / `state_after` 内容高度重叠，
   即使进了数据库，三列各存一份仍然是 3 倍存储与 3 倍写入。
   这是**独立的**优化项（例如只存 `state_after` + 输出差异，或对 `payload` 做截断/白名单）。

另：`indent=2` 对运行期状态没有人类可读性收益，改成紧凑 JSON 可直接减半。

> 本次**未改动**存储层——换库属于部署决策，且需要你确认目标环境是否有 Postgres。
> 上述数据供你决定。

---

## 5. 测试

| 文件 | 项数 | 覆盖 |
|---|---|---|
| `tests/test_hotspot_frequency.py`（新） | 22 | 两个阈值刻意不同；**真实跨平台标题被正确分组**；**链式传递分组**；短标题不做比例匹配；同平台重复只算一次；不误合并无关故事；频次分封顶；覆盖在过滤前计算；并列时覆盖更广者胜；**打乱输入顺序结果不变**；去重仍然严格 |
| `frontend/src/components/layout/__tests__/TruncatedText.test.tsx`（新） | 8 | 默认 1 行截断；指定行数；完整值保留在 `title` 提示；可覆盖提示；保留标题语义（`role=heading`）；非字符串子节点不加提示；调用方类名共存 |
| `frontend/src/components/layout/__tests__/textOverflow.test.ts`（新） | 4 | **全仓无裸动态标题/段落**；允许清单仍然有效（防腐烂）；5 个长文本面确实走了 `TruncatedText` |

后端 **499 → 521 passed**；前端 **144 → 156 passed**（22 个测试文件）。

---

## 6. 已知限制

1. **频次分组是启发式的**：`CROSS_PLATFORM_SIMILARITY=0.65` 与 `MIN_LOOSE_TITLE_LENGTH=4`
   是经验值。误判代价被刻意限制为"最多 +12 分"，不会删行；`source_platforms` 字段可用于人工复核。
2. **`O(n²)` 分组**：205 条候选 425 ms。若候选规模上到数千条需要改用倒排索引/SimHash 分桶。
3. **`TruncatedText` 用原生 `title` 提示**，不是 antd Tooltip：移动端长按不显示，且无样式控制。
   这是用"零 DOM 开销"换来的取舍。
4. **允许清单里的 `WorkbenchShell`** 若将来改为渲染动态文本，守卫不会自动发现——需人工同步。
5. 存储层未改动，见 §4.3。
