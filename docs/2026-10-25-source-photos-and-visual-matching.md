# 图片与文章内容匹配 + 复用参考文章真实照片

日期：2026-10-25
状态：已实现（后端 521 → 598 passed；前端 156 → 163 passed）
关联：`demand.md` §27、`docs/2026-10-10-image-prompt-pipeline-fix.md`

---

## 1. 需求与结论

> 这里的照片生成有问题，内容应该和文章内容匹配，而且如果参考的文章有对应的照片，可以拿来添加到生成的文章中

两个需求其实是**同一个根因链上的两端**，而且第二个需求顺带能绕过第一个需求的阻塞点。

| 需求 | 结论 |
|---|---|
| ① 图片内容要和文章匹配 | **根因是模型未配置**（`text_fast`），加上我把降级路径改成了"随文章变化" |
| ② 用参考文章的真实照片 | **数据早就抓到了，只是被丢弃**；投递链路原本就支持，属于补齐而非新建 |

---

## 2. 需求①的根因（有硬证据）

### 2.1 现象：所有文章拿到同一张"概念图"

实测 `data/tasks.json`，两篇毫不相关的文章：

```
fe61482a  被叫"史上最大"又被叫"最荒谬"，Anthropic的IPO现在只能拆开看
48d37ed3  微信亲自下场，红果劲敌"上桌"：先别把行业猜想当成事实

两者的 visual_spec.subject 逐字节完全相同：
  "A quiet workstation at night: an open laptop, a paper notebook and a cooling mug"
  section_link: "Fallback visual: no article-aware description was produced"
degraded_reason: spec_rejected:cover:no_spec_returned,contextual_illustration:no_spec_returned
```

### 2.2 失败点精确定位

`workflow/agents/visual_describer.py`：

| 位置 | 事实 |
|---|---|
| `model_config.json` | `text_fast = None`，结构化阶段回落到推理模型 `deepseek/deepseek-v4-pro-0813` |
| `logs/model.log` | `describe_visual` 的**调用确实发生了**（模型就是它）→ 不是"没配模型" |
| 第 191 行 | `chain is None` 不成立 |
| 第 218–219 行 | 调用**成功**，但 `batch.items` 为空 |
| 第 116 行 | `candidate is None` → `no_spec_returned` |
| 第 116/240 行 | `build_fallback_spec(role)` —— **只接收 role，与文章无关** |

> 所以这不是"图片生成坏了"，而是"**描述阶段没产出内容，降级到一张全局写死的图**"。

### 2.3 我的修复：降级不再是全局常量

`build_fallback_spec` 增加文章上下文，并建立**主题 → 物理场景**映射表：

```python
build_fallback_spec(role, topic=..., section=..., claim=...)
```

实测同一批主题现在得到 5 个各不相同的场景：

| 文章 | 生成的场景 |
|---|---|
| Anthropic 的 IPO | `A newspaper financial page and a pair of reading glasses on a dark trading desk` |
| 西藏那曲市7.0级地震 | `Rescue equipment laid out on the ground: rope, gloves, a folded blanket and a torch` |
| 国乒女团2比3日本女团 | `An empty stadium seating block and a folded team bench seen from the touchline` |

**诚实定位**：这是**缓解**，不是解决。它读不懂文章的论点，只能判断大致领域；
真正的"匹配"仍需要可用的结构化模型（见 §7）。降级状态照旧上报，人工审核照旧触发。

---

## 3. 需求②的现状：数据被丢弃

| | 位置 |
|---|---|
| 生产者 | `workflow/tools/fetch_extract.py:101` → `extracted_contents[].images`（每页最多 5 张） |
| 消费者 | **没有**（全仓 grep `["images"]` 只有生产者和测试） |

而投递链路**原本就支持外部图片**，不需要新管道：

- `assemble_article` 的 `illustrations` 是引用列表，`wechat_draft_service:82` 逐个交给
  `upload_article_image` → `wechat_api._download_image`（支持 http(s) 与本地文件）
- 正文插入是 `[插图N]` 占位符，由 `image_generation.py` **确定性插入**（不是写作 LLM 决定）

---

## 4. 实现

### 4.1 新增 `workflow/utils/source_images.py`

采集（零网络成本的前置过滤）：仅 HTTPS、扩展名白名单、文件名启发式排除
`logo|icon|qr|avatar|share|sprite|spacer|ad|banner|pixel|track`、URL 去重。

下载：15s 超时、浏览器 UA、**带 `Referer`**（很多 CDN 无 Referer 直接 403）。

**用 Pillow 做真实像素校验**（不再信任 `<img width= height=>` 标签属性 ——
那些属性通常缺失，正是过去漏掉 logo/小图/广告条的**直接原因**）：

| 检查 | 阈值 |
|---|---|
| 真实像素尺寸 | ≥ 600×300 |
| 宽高比 | 0.5–2.8（上限略高于封面 2.35，放行正常横图，拦掉横幅） |
| 纯色/空白 | 亮度标准差 < 8 判为空白图 |
| 动态图 | 拒绝（APNG/动态 WebP 一并拒绝） |
| **webp → jpeg 转码** | 必要：`ARTICLE_ALLOWED_IMG_TYPES = {jpeg,png,gif}` **不含 webp**，而旧提取器却接受 `.webp` —— 会在上传阶段才失败 |
| 过大图 | 下采样到宽 1600 |

（WebP 转码、真实尺寸校验、裁剪都需要图像库，故新增依赖 **Pillow**。）

### 4.2 接入 `generate_visual_assets_node`

采到的照片转成资产后**排在生成资产之前**，复用既有的章节排序与 `[插图N]` 插入逻辑
（不新写一套排布）。封面裁到微信 2.35:1 并**记录被丢弃的画面比例**。

### 4.3 来源留痕 + 强制人工审核（按选定策略）

- 每张照片带 `provider: "source"` 与
  `attribution: {source_title, source_domain, source_url, image_url}`
- **只要有照片被使用，就强制 `human_review_required = True`**，无视发布策略；
  原因是**追加**到既有 blocking 通道，不改变运维方自己的审核策略
- **无标题且无域名 → 直接丢弃**（无法留痕就不满足所选策略）
- 可见署名由 `SOURCE_IMAGE_CREDIT` 控制，**默认关闭**（对应"写入元数据与风险提示"）

### 4.4 前端

`TaskDetail` 图片画廊显示每张来源照片的出处（可点击到原文）与裁切警告，
供**必须进行人工审核**的操作者核对。

---

## 5. 自己的测试抓到的 4 个真 bug

这一轮实现里，测试先于用户发现了 4 个问题，都是"看起来对但实际错"的类型：

| # | 问题 | 证据 | 修法 |
|---|---|---|---|
| 1 | **数量上限被并发击穿** | 上限设 2，实测返回 **6**：4 个并发 worker 都在 append 前读到 `len(accepted)=0` 而放行 | 并发内保留早退（省下载），**并发后强制截断**并记 `over_cap` |
| 2 | **宽高比放行了横幅** | 2400×700（3.43:1）通过了 3.5 上限 | 上限收到 **2.8**（略高于封面 2.35，拦掉横幅） |
| 3 | **资产引用了远端 URL** | `_asset_ref` 优先取 `url`，来源资产的 `url` 是远端地址 → 上传时会**二次下载**，而 `_download_image` **不带 Referer**，很可能 403 | `url` 改为指向**已下载的本地文件**，远端地址移入 `attribution.image_url` |
| 4 | **动态图原因错报** | 我的探针构造的 GIF 使 `n_frames=1`，误报为 `low_variance` | 探针改为走真实解码路径；校验逻辑本身顺序是正确的 |

第 3 条尤其关键：它是**上线后才会暴露**的那类问题（本地预览正常，推送时才 403）。

### 5.1 顺带修掉一个上一轮的功能缺陷

上一轮的热点快照有一个调度漏洞：**刷新失败（16 个平台全挂）也会盖上新的 `captured_at`**，
于是 `due_for_refresh()` 在**整个周期内都为 False** —— 一次上游抖动会换来 60 分钟的静默。
实测 2026-10-24 19:07 就发生了 16 个平台全部失败。

现在：`attempted_at` 始终记录，无候选时按 `HOTSPOT_RETRY_INTERVAL_MINUTES`（默认 **5** 分钟）重试；
`is_fresh()` 也要求快照非空。

```
失败后立刻重试   : False   （不打的太密）
失败 6 分钟后    : True    （原为等 60 分钟）
成功后立刻       : False
成功 61 分钟后   : True
```

---

## 6. 实测验证

真实页面（从 newsnow 实时取 18 条文章 URL）→ 真实抽取 → 真实下载校验：

```
4 个页面成功抽到图片 → 9 个候选 → 4 张通过校验
rejected: {'duplicate_url': 7, 'too_small': 5}     ← logo/小图被正确拦下
 1262x726 image/png  899KB
 1000x950 image/png  490KB
 1000x831 image/png  463KB
 1000x1058 image/png 767KB
封面裁切: 1262x726 → 1262x537  ratio=2.350 (目标 2.35)  丢弃 26.0% → 超过 25% 阈值，正确提示人工确认
```

像素校验门槛（走真实解码路径）：

```
PASS   photo-like 1200x800 (PNG)     format=PNG
PASS   photo-like 1200x800 (WEBP)    format=WEBP
REJECT blank solid                   low_variance(0.0)
REJECT too small 200x150             too_small(200x150)
REJECT short banner 2000x200         too_small(2000x200)
REJECT animated gif                  animated
```

---

## 7. 需要你确认的一件事（我无法验证）

**需求①真正"匹配"的前提是把 `text_fast` 配成一个非推理模型。**

理由：结构化阶段现在回落到推理模型，返回的 `items` 是空的（§2.2）。我无法在没有你的密钥的
情况下验证换成非推理模型后是否返回非空——这一条留给你在真实任务里确认。

即使不配，本轮改动仍然有效：来源照片会填满大部分图位，且降级路径不再是全局同一张图。

---

## 8. 配置新增

| 键 | 默认 | 说明 |
|---|---|---|
| `SOURCE_IMAGE_ENABLED` | `true` | 总开关 |
| `SOURCE_IMAGE_MAX` | `3` | 每篇最多几张（封面占 1） |
| `SOURCE_IMAGE_MIN_WIDTH` / `MIN_HEIGHT` | `600` / `300` | 真实像素下限 |
| `SOURCE_IMAGE_MAX_BYTES` | `8388608` | 单张体积上限 |
| `SOURCE_IMAGE_ALLOWED_DOMAINS` | 空 | 留空不限制；收紧版权风险时使用 |
| `SOURCE_IMAGE_CREDIT` | `false` | 是否在正文显示可见署名 |
| `COVER_SOURCE_PREFERRED` | `true` | 封面是否优先用真实照片 |
| `COVER_CROP_DISCARD_WARN` | `0.25` | 裁切丢弃超过该比例即提示人工确认 |
| `HOTSPOT_RETRY_INTERVAL_MINUTES` | `5` | 热点刷新失败后的重试间隔（§5.1） |

**新增依赖**：`Pillow>=11.0.0`（需 `pip install -r requirements.txt`）。

---

## 9. 测试

| 文件 | 项数 | 覆盖 |
|---|---|---|
| `tests/test_source_images.py`（新） | 38 | HTTP/扩展名/文件名/去重过滤；**下载失败与 403 被容忍**；真实尺寸/比例/纯色/**动态图**；**webp→jpeg**；下采样；**数量上限**（曾因并发失效）；**内容重复只算一次**；**无出处即丢弃**；未引用页面被跳过；域名白名单；封面裁剪精度与丢弃比例；资产形状满足下游 |
| `tests/test_visual_fallback_matching.py`（新） | 19 | **两篇不同文章不再得到同一张图**（直接钉住原缺陷）；旧写死场景已消失；场景随主题变化；未匹配主题之间仍不同；确定性；**降级规格仍必须 `is_usable`**；不请求文字/图表；`TEXT_EXCLUSION_CLAUSE` 仍保留 |
| `tests/test_source_image_pipeline.py`（新） | 12 | 照片成为封面与插图；封面裁到 2.35:1；重裁切被标记；可关闭封面优先；**采集失败不影响生成资产**；**有照片即强制人工审核**；显式自动发布策略也无法绕过；仅生成图不触发审核 |
| `tests/test_source_image_review.py`（新） | 8 | 照片通过审核但**不计为生成图**；占位符仍被拒；重裁切与缺失出处被上报；照片不产生假的"数量不足" |
| `frontend/.../TaskDetail.provenance.test.ts`（新） | 7 | 出处提取；裁切警告；无标题回落到域名；生成图无出处；封面/插图仍被收集且去重；缺失 attribution 与缺失 article 不崩 |

后端 **521 → 598 passed**；前端 **156 → 163 passed**。

---

## 9.5 附加：让热点真正"用上"（同日追加）

排查「现在抓取热点是否有使用我给你的项目」时发现：**管道是通的，但阀门是关的**。

实测三条断点：

| 断点 | 实证 |
|---|---|
| 所有任务的热点都是关的 | 5 个有配置的任务全部 `enabled=False`、**0 个平台** |
| 后端默认 source 仍是 `tophub` | `HotspotCaptureConfig.source` 默认值 |
| **前端根本没有平台选择器** | `hotspot_platforms` 在表单里从没人写，永远是 `[]` |

第三条是关键：**打开热点开关等于没打开** —— 后端拿到空平台列表后会
`discover_hotspot_platforms()` 自动发现 26 个内置平台，其中 8 个 TopHub + 2 个 RSS
会被**实时抓取**，正是那条不可靠的路径。

按确认的决定改为：**默认开启 + 预填 16 个 newsnow 平台**。

### 改动

- `HotspotCaptureConfig.source` 默认 → `newsnow`（该字段只用于日志；
  分派始终按平台走 `_platform_source()`，所以不影响已有任务）
- `_normalize_hotspot_capture_config` 两处默认同步
- 前端：新增**热点平台选择器**，从 `/api/hotspots/platforms` 读取目录，
  默认勾选 **16 个 newsnow 平台**；提交时按 `path` 回目录取完整条目，
  保证 `source`/`provider_id` 来自后端而不是前端硬编码
- 存量 5 个任务**未改动**（按确认）

### 实测（同一任务，改前 vs 改后）

| 指标 | 改前（空平台） | 改后（16 个 newsnow） |
|---|---|---|
| 上游平台抓取次数 | 1（TopHub 实时爬） | **0** |
| 建任务耗时 | **6015 ms** | **265 ms**（23 倍） |
| 候选数 | 15 | **212 → 45** |
| 选中热点 | — | 真实热点，keywords 已改写 |

### 由此又发现两个问题

**① 已知失败的平台每次都被重抓**：`mktnews` 上游长期返回 0 条，因此它在快照里
没有候选 → 被视为"未覆盖" → **每个任务都实时重抓一次**。就是它让上表从 265 ms 变成 6015 ms。
现在快照新鲜时，把上次刷新已确认失败的平台**跳过**（`recently_failed_platforms()`），
下一个定时周期仍会重试，不会永久卡死。

**② 一次失败的刷新会抹掉好数据**：排查时上游对 16 个平台**同时返回 HTTP 500**，
而我的 `force=True` 刷新把 **210 条真实候选清空了**。
现在失败的刷新会**保留上一次的候选**，但
- 标记 `succeeded: false` → `is_fresh()` 为 False（**不会把旧数据当作当前热点使用**）
- 记录 `last_success_at` 与 `preserved_from_previous`，运维可判断数据实际有多旧
- 仍按 `HOTSPOT_RETRY_INTERVAL_MINUTES`（5 分钟）重试，恢复后立刻覆盖

另修：`candidate_count` 曾与 `candidates` 不一致（前者 0、后者 1），会误导运维判断"没有数据"。

> 注：那次 500 是**真实的瞬时故障**（也可能是我短时间内反复刷新触发的限流），
> 上游随后自行恢复（weibo 返回 30 条）。它暴露的是处理方式，不是新的 bug。

### 测试

新增 8 项（`test_hotspot_snapshot.py` 7 + `test_schedule_hotspot_models.py` 2 − 1 改写）+
前端 2 项（默认提交 newsnow 平台、目录只加载一次）。
后端 **598 → 607 passed**；前端 **163 → 165 passed**。
前端测试并补上了 `getHotspotPlatforms` 的 mock —— 之前它会**真的发网络请求**，
并因未 await 产生 `act()` 警告。

---

## 10. 已知限制

1. **没有视觉模型**：无法判断画面是否真的与正文一致、是否主体被裁掉、是否含文字。
   系统对此的说法保持诚实（`CHECK_NOTE`），裁切只做提示不做判定。
2. **主题映射是启发式的**：`_SCENE_HINTS` 是关键词表，读不懂论点；未匹配时在 4 个通用场景里
   按主题哈希取一个（保证不同文章不同图，但不保证贴切）。
3. **版权不可自动判定**：强制人工审核 + 出处留痕是当前能做的最稳妥组合；
   `SOURCE_IMAGE_ALLOWED_DOMAINS` 可进一步收紧。
4. **裁剪默认居中**：不做人脸/主体检测（无视觉模型）。
5. **`O(图片数)` 网络往返**：每篇最多试 3×上限 个候选，失败即回落，不影响任务。
6. 未改动 `data/` 中已有任务的历史图片，仅影响新任务。
