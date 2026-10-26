# 项目开发规范

## 项目概述

基于 LangGraph 的微信公众号文章自动发布系统。用户输入关键词，系统自动搜索网页内容、调用 LLM 生成图文文章，并通过微信公众号 API 推送至草稿箱，配套 Web UI 提供可视化操作界面。

## 技术栈

### 后端

| 类别 | 选型 |
|------|------|
| 语言 | Python 3.11+ |
| 工作流引擎 | LangGraph 0.2+ |
| LLM 框架 | LangChain 0.3+ |
| Web 框架 | FastAPI 0.110+ |
| 异步 HTTP | httpx |
| 网页解析 | trafilatura（主）、BeautifulSoup4（备） |
| 环境配置 | python-dotenv |
| 日志 | structlog |
| 测试 | pytest + pytest-asyncio |
| 依赖管理 | pip + requirements.txt（锁定版本） |

### 前端

| 类别 | 选型 |
|------|------|
| 框架 | React 18 + TypeScript |
| UI 组件库 | Ant Design 5.x |
| 状态管理 | Zustand |
| 路由 | React Router v6 |
| 构建工具 | Vite 5.x |
| HTTP 客户端 | Axios |
| 实时通信 | 原生 WebSocket |

## 目录结构

```
wechatProject/
├── api/                        # FastAPI 后端
│   ├── main.py                 # 应用入口
│   ├── routers/                # 路由（tasks.py, ws.py）
│   └── models.py               # Pydantic 数据模型
├── workflow/                   # LangGraph 工作流
│   ├── graph.py                # StateGraph 定义
│   ├── state.py                # WorkflowState 定义
│   └── skills/                 # 各 Skill 节点实现
├── frontend/                   # React 前端
│   ├── src/
│   │   ├── pages/              # 页面组件
│   │   ├── components/         # 通用组件
│   │   ├── store/              # Zustand 状态
│   │   └── api/                # API 请求封装
│   ├── package.json
│   └── vite.config.ts
├── tests/                      # pytest 测试
├── logs/                       # 日志（不提交 git）
├── main.py                     # 命令行入口
├── requirements.txt            # Python 依赖（锁定版本）
├── .env.example                # 环境变量示例
├── .gitignore
└── CLAUDE.md                   # 本文件
```

## 后端代码规范

### Python 风格

- Python 版本：**3.11+**，严格遵循 PEP 8
- 缩进：4 个空格
- 命名：类名 `PascalCase`，函数/变量 `snake_case`，常量 `UPPER_SNAKE_CASE`
- 每行不超过 120 个字符
- 文件编码：`UTF-8`
- 所有公共模块、类、函数必须有 docstring

### 类型注解

- 所有函数参数和返回值必须有类型注解
- 使用 `from __future__ import annotations` 支持延迟注解
- 优先使用内置类型（`list[str]` 而非 `List[str]`，Python 3.11+ 支持）

### 异步规范

- FastAPI 路由和 LangGraph 节点优先使用 `async def`
- 使用 `httpx.AsyncClient` 进行异步 HTTP 请求
- 避免在异步上下文中使用同步阻塞调用

### 导入顺序

1. 标准库
2. 第三方库
3. 本项目模块

各组之间空一行，使用 `isort` 或手动保持排序。

## 前端代码规范

### TypeScript 风格

- 严格模式：`tsconfig.json` 中启用 `"strict": true`
- 组件命名：`PascalCase`（如 `TaskDetail.tsx`）
- 函数/变量：`camelCase`
- 常量：`UPPER_SNAKE_CASE`
- 禁止使用 `any`，必须明确声明类型

### 组件规范

- 统一使用函数式组件 + React Hooks
- 每个组件单独文件，放在对应的 `pages/` 或 `components/` 目录
- 页面级组件放 `pages/`，复用组件放 `components/`

### UI 风格规范

**设计方向：明亮极简瑞士风（International Typographic Style）**

- **唯一真源**：`frontend/src/styles/tokens.css`。组件**只允许**使用其中的语义层令牌
  （`--surface-*`、`--text-*`、`--border-*`、`--accent*`、`--status-*`），不得写死色值、圆角或阴影。
  深色主题只覆盖语义层，不复制调色板。
- **主色调**：`#0F766E`（青绿）。注意：此前文档写的是 `#1677FF`，与实现（`#0f766e`）长期不一致，
  现已统一为青绿，因为红/琥珀/绿已被状态语义占用，再加一个红色会产生歧义。
- **圆角**：面块 `--radius-none`（0），控件 `--radius-hair`（2px）。禁止大圆角。
- **阴影**：默认不使用。层级用 `--border-hairline` 发丝线表达；仅浮层（Modal/Dropdown/Popover）
  使用 `--elevation-overlay` / `--elevation-popover`。
- **字体**：拉丁与中文均使用系统字体栈（`--font-sans`）。**不要引入中文网络字体**——
  中文子集动辄数 MB，部署目标是 2C2G 单机。要引入授权拉丁紧体时，放入 `public/fonts/`
  并前置到 `--font-sans`，同时补 `@font-face`。
- **字阶与字距**：严格使用 `--type-*` 与 `--tracking-*`。大标题用 `--tracking-tight`，
  等宽小标签用 `--tracking-wider` + 大写。数字一律 `font-variant-numeric: tabular-nums`。
- **间距**：统一使用 `--space-*`（4px 基数，8px 节奏）。不要用魔法数字。
- **动效**：只动画 `transform` 与 `opacity`，统一使用 `--dur-*` 与 `--ease-*`；
  所有动效必须尊重 `prefers-reduced-motion`（`global.css` 已提供全局兜底，
  自建 hook 见 `src/motion/`）。
- **布局**：门面页 `/` 为公开页；控制台为左侧导航 + 右侧内容区，页面骨架使用
  `components/layout/` 的 `PageHeader` / `Panel` / `Toolbar` / `StatGrid` / `EmptyState` / `KeyValueList`。
- **禁止内联样式对象**（`style={{ ... }}`）：样式统一写在 CSS Modules 中。
  **唯一例外**是真正的动态值（进度、图表几何），必须写成 CSS 自定义属性
  （`style={{ '--progress': pct }}`），以便主题仍能作用于它。
  该规则由 `src/styles/__tests__/noInlineStyle.test.ts` 强制，旧令牌由
  `noLegacyTokens.test.ts` 强制，两者都使用「只减不增」的待迁移清单。
- **antd**：保留 antd 提供表单/表格/弹窗的可用性，但主题必须由令牌生成
  （`src/theme.ts` 从 `styles/tokens.ts` 派生）；`styles/__tests__/tokenParity.test.ts`
  会校验 TS 与 CSS 两侧的令牌一致，防止再次漂移。
- **品牌标记**：统一使用 `components/brand/BrandMark`，favicon 为 `public/favicon.svg`。

## 依赖管理

### 后端

- 所有依赖写入 `requirements.txt`，锁定版本号：`package==x.y.z`
- 安装：`pip install -r requirements.txt`
- 新增依赖后及时更新：`pip freeze > requirements.txt`

### 前端

- 使用 `npm` 管理，锁定 `package-lock.json`
- 安装：`npm install`
- 新增依赖后提交 `package.json` 和 `package-lock.json`

## Git 规范

### 分支策略

- `main`：稳定主分支，只接受 PR 合并
- `master`：当前开发分支
- 功能分支：`feature/功能描述`
- 修复分支：`fix/问题描述`

### Commit 消息格式

```
<type>: <简短描述>

[可选详细说明]
```

type 类型：
- `feat`：新功能
- `fix`：Bug 修复
- `refactor`：重构
- `docs`：文档更新
- `chore`：构建/工具/配置变更

示例：`feat: 添加 search_web skill 节点`

### .gitignore 必须排除

- `.venv/`
- `__pycache__/`、`*.pyc`
- `.env`
- `logs/`
- `frontend/node_modules/`
- `frontend/dist/`

## 安全规范

- API 密钥（微信、搜索引擎、LLM）禁止硬编码，统一放 `.env` 文件
- `.env` 不得提交 git，仅提交 `.env.example`（值留空）
- Web UI 接口需 Token 鉴权
- 用户输入需过滤恶意内容

## 测试规范

- 测试文件放 `tests/`，命名：`test_<模块名>.py`
- 使用 `pytest` + `pytest-asyncio`
- 每个 Skill 节点必须有对应单元测试
- Mock 外部 API 调用（搜索引擎、LLM、微信 API）

## 日志规范

**统一使用 `structlog`**（`structlog.get_logger(__name__)`）。不要用 stdlib `logging`：
stdlib 记录经 structlog formatter 渲染后会**丢失时间戳、级别与 logger 名**，
产生无法过滤、无法解析的行。唯一的例外是配置模块本身（`api/logging_config.py`）。

### 格式与级别

- **文件写 JSON**（`logs/app.log`，每行一个 JSON 对象），**控制台写可读文本**；
  `LOG_FORMAT` 可显式覆盖为 `json` 或 `text`。
- 级别由 `LOG_LEVEL` 控制（默认 `INFO`）。排查问题时改环境变量，不要改代码。
- 第三方库（`httpx`/`httpcore`/`openai`/`langchain*`/`trafilatura` 等）
  固定不低于 `WARNING`：httpx 会为每个请求写一行 INFO。

### 字段约定

- 每行自动携带 `event`、`level`、`logger`、`timestamp`（无需手写）。
- 业务字段至少包含：`task_id`、`skill`、`status`、`duration_ms`。
- **用结构化字段，不要字符串拼接**，也不要用 `%s` 占位
  （structlog 不做 %-插值，会原样打印 `%s`）：
  `logger.info("fetch_failed", url=url, error=str(exc))`。

### 异常必须带堆栈

`except` 块中的日志调用**必须**附带 traceback，否则 `error=boom` 无法定位：

```python
except Exception as exc:
    # 容忍/降级路径：保持原级别，补 exc_info=True
    logger.warning("fetch_failed", url=url, error=str(exc), exc_info=True)
    ...
except Exception as exc:
    # 真正的失败：用 logger.exception（ERROR + traceback）
    logger.exception("workflow_failed", task_id=task_id, error=str(exc))
```

### 关联 ID

- HTTP 请求自动带 `request_id`（`RequestContextMiddleware` 绑定，并回写 `X-Request-ID` 响应头）。
- 工作流运行自动带 `task_id` + `run_id`（`run_workflow` 绑定，`finally` 解绑）。
- 因此**不要手动在消息里拼 `task_id`**，它已经在字段里。

### 敏感信息

- 任何密钥必须掩码：用 `workflow.model_logging.mask_secret`。
- 两个去向都会递归掩码 `api_key`/`secret`/`password`/`token` 键。

### 模型 payload 单独落盘

完整 prompt/响应**不写 `app.log`**（曾占其体积 57%，单行最长 3 万字符），
而是写 `logs/model.log`（JSON Lines）。主日志只留元数据：
`payload_chars`、`payload_sha256`、`payload_truncated`。
统一走 `workflow.model_logging.log_model_request/log_model_response`，
不要自己拼 `logger.info("model_request", request=...)`。

### 高并发事件的级别

- 每次 flush / 每次连接一类的高频事件用 `DEBUG`
  （如 `persistence_flushed`、`ws_connected`）。
- 每个节点一对的进度事件（`skill_start`/`skill_done`）保留 `INFO`——那是日志的叙事主线。

### 测试

测试**不得写入仓库 `logs/`**：`api/main.py` 在导入时配置日志，
`tests/conftest.py` 的 `isolate_logging` autouse fixture 会把文件日志重定向到 `tmp_path`。
新增测试若自行配置日志，同样必须传入 `log_dir_override`。

## 图片来源规范

配图有两种来源，**真实照片优先**：`workflow/utils/source_images.py` 从"文章已引用的来源页面"
采集真实照片（`provider: "source"`），不足的部分才由图像模型生成。

`fetch_extract` 早就在收集 `extracted_contents[].images`，但长期**无人消费**；
插图位只由模型填充。新增消费方时不要重新发明排布逻辑——把照片转成资产后交给既有的
章节排序与 `[插图N]` 插入机制即可。

### 图片来源必须遵守的规则

1. **必须可留痕**：无标题且无域名的图片**直接丢弃**。无法记录出处就满足不了版权策略。
2. **只要有来源照片被使用，就必须强制人工审核**（`assemble_article._build_publish_decision`）。
   这是**追加**原因，不得替换或放宽运维方自己的 `review_policy`。
3. **用真实像素校验，不要信任标签属性**：`<img width= height=>` 通常缺失，
   这正是过去放行 logo/图标/广告条/追踪像素的直接原因。检查真实尺寸、宽高比、亮度方差、动态帧。
4. **WeChat 只接受 jpeg/png/gif**（`ARTICLE_ALLOWED_IMG_TYPES`）。来源图里 webp 很常见，
   **必须转码**——旧校验接受了 `.webp`，会在上传阶段才失败。
5. **下载要带 `Referer`**，否则很多 CDN 直接 403，表现为"一张图都采不到"。
6. **资产引用要指向已下载的本地文件**。指向远端地址会让上传阶段二次下载，
   而该路径**不带 Referer**，很可能 403——这类问题本地预览正常，**只在推送时暴露**。
7. **封面裁切只做提示不判定**：系统没有视觉模型，无法判断主体是否被裁掉。
   丢弃比例超阈值时给出提示，由人工确认。

### 降级路径不得是全局常量

`build_fallback_spec` 曾只接收 `role`，于是所有文章拿到同一张写死的图
（实测两篇无关文章逐字节相同）。**降级也要带上文章上下文**（topic/section/claim），
保证"至少与主题相关、且不同文章不同图"。降级状态必须照旧上报并触发人工审核。

## 长文本显示规范

**任何来自接口/LLM 的动态文本，渲染为标题或段落时必须用 `components/layout/TruncatedText`**：

```tsx
<TruncatedText as="h2" lines={1}>{task.title}</TruncatedText>
<TruncatedText as="p" lines={3}>{summary}</TruncatedText>
```

理由（这是实际发生过的缺陷）：把完整标题与最长 200 字的摘要直接放进 `<h2>`/`<p>`，
卡片高度就会随内容无限增长并撑坏周围栅格。栅格列即使写对了
（`minmax(0, 1fr)` + `min-width: 0`）也不管用——**必须截断文本元素自身**。

`TruncatedText` 已处理一个容易漏掉的坑：**`min-width: 0`**。
flex/grid 子项默认 `min-width: auto`，会拒绝收缩到内容宽度以下，
于是即使写了 `text-overflow: ellipsis` 也永远不出现省略号。
它还加了 `overflow-wrap: anywhere`（长 URL / 长 ID 不溢出），
并把完整值放进原生 `title` 提示，所以截断不丢信息。

- 静态字面量（`<p>确认后会将文章渲染为 HTML…</p>`）不受此限：长度在评审时确定。
- 该规则由 `components/layout/__tests__/textOverflow.test.ts` 强制：
  `pages/` 与 `components/` 内不得出现裸的 `<h1-h3>{动态值}` / `<p>{动态值}`。

## 热点排序规范

跨平台覆盖是**独立于 rank 的排序信号**：同一故事在多个平台上榜，说明它是真热点，
而不只是某个榜单的头部条目。`rank_hotspots` 输出 `frequency_score`、
`cross_platform_count`、`source_platforms` 供审计。

改相似度阈值时务必记住**两个阈值用途不同、不可合并**：

| 常量 | 用途 | 误判代价 |
|---|---|---|
| `DUPLICATE_SIMILARITY`（0.90） | 决定哪些**行存活** | 删掉真实不同的故事，**不可恢复** |
| `CROSS_PLATFORM_SIMILARITY`（0.65） | 只决定**覆盖广度** | 多给**有上限**的分，绝不删行 |

覆盖分组必须**可传递**（并查集连通分量）：真实跨平台标题常构成链
（A≈B、B≈C，但 A≁C），星形逐一比对会把同一个故事算成 2/3/2 而不是 3/3/3。

## 热点获取规范

### 平台必须显式配置，不能留空

**空平台列表不是"用默认值"，而是"自动发现全部内置平台"**
（`capture_hot_topics_node` 会调 `discover_hotspot_platforms()`），
结果是 26 个平台里混入 8 个 TopHub + 2 个 RSS 被**实时抓取**——那条不可靠的路径。

前端新建任务默认提交 **16 个 newsnow 平台**（选择器从 `/api/hotspots/platforms` 读目录，
提交时按 `path` 回目录取完整条目，**不要在前端硬编码 `source`/`provider_id`**）。

### 来源与调度

- 热点来源通过 `HotspotSource` 枚举分派：`tophub`（爬 HTML）、`newsnow`（结构化 JSON）、
  `rss_or_feed`、`ranking_page`。**新增来源只需加枚举值 + 一个 `HotspotProvider` 子类 + 注册表分支。**
  `HotspotCaptureConfig.source` **只用于日志**，分派始终按平台的 `_platform_source()`。
- **默认来源是 `newsnow`**：它是 TrendRadar 自己调用的多平台接口，一次 GET 拿一个平台的结构化榜单，
  覆盖 16 个平台。原先爬 TopHub HTML 的实测代价是 429 次重试、176 次 `hotspot_source_unavailable`。
- 热点**不再在任务创建时同步抓取**：后台定时刷新写入快照，任务优先读快照。
  改变周期只需设 `HOTSPOT_REFRESH_INTERVAL_MINUTES`（`1440` = 每日），**不要改代码**。

### provider 必须做到的事

1. 校验上游 `status`（newsnow 的 `cache` 是合法状态，表示上游返回了近期缓存）。
2. **标题必须是字符串**：上游返回过数字与 null，字符串化会产出 `"1.5"` 这种"标题"。
3. 单平台失败**只丢弃该平台**，不得中断其余平台（用 `asyncio.gather(return_exceptions=True)`）。
4. 重试带**抖动**；16 个平台并发时固定间隔会让它们同步打上游。
5. 候选字段遵循既有形状：`title`/`url`/`rank`/`platform_weight`/`category`/`extra_text`/`source`。

### 第三方链接安全

上游返回的 URL 会进入我们的抓取链路，因此必须校验：
**全程 HTTPS**，且 **hostname 必须等于或后缀匹配该平台的期望域名**。
用 `urlsplit().hostname` 比对，**不要比对原始字符串** —— `https://baidu.com@evil.com/` 的
userinfo 段看起来就像可信域名。期望域名表在 `workflow/utils/newsnow_catalog.py`。
未通过校验的条目**丢弃并记 `warning`**，不要静默保留。

### GPL 边界（重要）

TrendRadar（`sansan0/TrendRadar`）是 **GPL-3.0**，本仓库**没有 LICENSE 文件**。
- ✅ 可以：调用其上游 API、按其平台目录配置来源、**移植行为/方法**（方法不受版权保护）。
- ❌ 不可以：把它的源码复制进本仓库 —— 那会要求整个项目 GPL-3.0 并附对应源码。
- 移植行为时**必须在 docstring 中署名**来源（见 `hotspot_providers.py` / `newsnow_catalog.py`）。

## 运行方式

```bash
# 激活虚拟环境
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Linux/macOS

# 安装后端依赖
pip install -r requirements.txt

# 启动后端服务
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# 安装并启动前端（开发模式）
cd frontend
npm install
npm run dev

# 命令行模式
python main.py --keywords "人工智能 最新进展"
```
