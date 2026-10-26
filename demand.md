# 基于 LangGraph 的微信公众号文章自动发布系统需求文档

版本：v2.0
更新日期：2026-10-09

---

## 1. 项目概述

本项目构建一个基于 **LangGraph** 的智能体工作流，实现微信公众号文章的自动化生成与发布。用户默认只需输入主题文本，系统会先自动推断文章风格与结构蓝图，再优先搜索官网、官方文档和高可信媒体内容，整合生成符合微信公众号风格的图文文章，并推送至公众号草稿箱，供人工审核后发布。

系统同时提供一套 **Web UI 界面**，让内容运营人员可以通过可视化页面触发任务、监控进度、预览草稿并进行人工干预。

参考产品：扣子（Coze）平台"微信公众号图文生成"工作流。

---

## 2. 用户角色

| 角色 | 职责 |
|------|------|
| 内容运营人员 | 输入关键词、触发流程、预览草稿、审核发布 |
| 系统管理员 | 维护 API 密钥、配置公众号接入、监控运行状态 |

---

## 3. 功能需求

### 3.1 核心功能

| 功能模块 | 详细描述 |
|----------|----------|
| 主题输入 | 支持输入主题文本，并可附加角色、文章策略、可选 `style_hint` 作为生成起点 |
| 风格与蓝图规划 | 在搜索前先推断 `user_intent`、`style_profile`、`article_blueprint`，确定文章结构、语气和搜索重点 |
| 网页链接搜集 | 根据蓝图规划的搜索词调用搜索引擎 API，优先获取官网、官方文档和高可信媒体链接，并使用 DuckDuckGo 作为免费兜底 |
| 内容提取与清洗 | 抓取链接页面，去除广告、导航等噪声，保留正文、标题、图片等关键信息 |
| 来源排序 | 对搜索结果进行可信度、相关度和来源多样性排序，筛掉低质量或重复来源 |
| 文章生成 | 调用 LLM，将多源内容按蓝图综合成一篇微信公众号风格文章，包含：主标题（+2个备选）、固定章节结构、局限与风险、行动建议、正文插图标注 |
| 图片处理 | 支持三种方案（详见 Skill 4），将图片上传至微信素材库并替换正文中的 `[插图]` 标记 |
| 草稿推送 | 通过微信公众号 API 将图文推送至草稿箱，返回 `media_id` |
| 结果反馈 | 向用户展示任务状态、草稿 ID 及预览链接 |
| Web UI | 可视化操作界面，支持关键词输入、任务进度监控、草稿预览与人工干预 |

### 3.2 扩展功能（可选，后续迭代）

- 定时发布：指定时间自动触发工作流
- 人工干预节点：推送前允许用户在线编辑文章
- 素材库管理：自动保存生成图片到微信素材库
- 多账号管理：支持多个微信公众号
- 多平台支持：扩展至知乎、头条号等平台

---

## 4. 非功能需求

### 4.1 性能

- 单次任务完成时间 ≤ 3 分钟（受网络与 LLM 推理速度影响）
- 支持多任务并发处理

### 4.2 可靠性

- 网络请求失败、API 限流等异常自动重试，最多 3 次
- 关键步骤（草稿推送、LLM 调用）记录结构化日志，便于追溯

### 4.3 可扩展性

- 工作流节点支持动态替换（搜索引擎、LLM 模型均可配置切换）
- StateGraph 设计预留新节点接入口

### 4.4 安全性

- 所有 API 密钥通过环境变量或加密配置文件管理，禁止硬编码
- 用户输入过滤恶意内容，防止注入攻击
- Web UI 需登录鉴权（基础 Token 认证）

---

## 5. 技术架构

### 5.1 核心技术栈

| 类别 | 技术选型 |
|------|----------|
| 语言 | Python 3.11+ |
| 工作流引擎 | LangGraph 0.2+ |
| LLM 框架 | LangChain 0.3+ |
| 大语言模型 | OpenAI GPT-4o（默认），支持切换通义千问、文心一言等 |
| 搜索引擎 | SerpApi Google（主），Bing Web Search API（备），DuckDuckGo HTML（免费兜底） |
| 网页解析 | `trafilatura`（主），`BeautifulSoup4`（备） |
| 图片生成 | DALL-E 3（可选），或从原网页提取 |
| 微信 API | 微信公众号开放平台 API（草稿、素材、Token） |
| Web UI 后端 | FastAPI 0.110+ |
| Web UI 前端 | React 18 + TypeScript + Ant Design 5.x |
| 前端构建 | Vite 5.x |
| HTTP 客户端 | `httpx`（异步），`requests`（同步工具） |
| 环境配置 | `python-dotenv` |
| 日志 | `structlog` |
| 测试 | `pytest` + `pytest-asyncio` |
| 依赖管理 | `pip` + `requirements.txt`（锁定版本） |

### 5.2 系统架构图

```
用户（Web UI）
     │
     ▼
FastAPI 后端 (api/)
     │  WebSocket 推送进度
     ▼
LangGraph 工作流 (workflow/)
     │
     ├── Skill 1: interpret_user_intent   # 解析主题、角色、文章目标
     ├── Skill 2: infer_style_profile     # 自动生成风格画像
     ├── Skill 3: build_article_blueprint # 生成结构化文章蓝图
     ├── Skill 4: plan_search_queries     # 基于蓝图规划搜索词
     ├── Skill 5: search_web              # 多搜索源检索
     ├── Skill 6: rank_sources            # 可信源排序
     ├── Skill 7: fetch_and_extract       # 网页抓取 + 内容清洗
     ├── Skill 8: generate_article        # LLM 文章生成
     ├── Skill 9: generate_images         # 图片处理
     ├── Skill 10: push_to_draft          # 微信草稿推送
     └── Skill 11: ui_feedback            # 结果通知 & 前端状态更新
```

### 5.3 LangGraph 状态定义

```python
from typing import List, Dict, Optional, Annotated
from typing_extensions import TypedDict

class WorkflowState(TypedDict):
    task_id: str                          # 任务唯一 ID
    keywords: str                         # 用户输入的关键词
    generation_config: Dict               # 文章生成配置：{audience_roles, article_strategy, style_hint}
    user_intent: Dict                     # 用户意图解析结果：{topic, primary_role, article_goal, resolved_strategy}
    style_profile: Dict                   # 风格画像：{style_archetype, tone, title_style, style_prompt}
    article_blueprint: Dict               # 文章蓝图：{section_outline, search_focuses, title_strategy}
    search_queries: List[Dict]            # 搜索规划结果：[{query, intent, priority}]
    search_results: List[Dict]            # 结构化搜索结果：{url, title, snippet, domain, source_type, final_score}
    extracted_contents: List[Dict]        # 每个 URL 提取的内容：{url, title, text, images, source_meta}
    article_plan: Dict                    # 兼容旧接口的规划结果，由 blueprint 派生
    generated_article: Dict               # 生成的文章：{title, alt_titles, content, cover_image, illustrations}
    draft_info: Optional[Dict]            # 草稿推送结果：{media_id, url, err_msg}
    retry_count: int                      # 当前重试次数
    error: Optional[str]                  # 错误信息
    status: str                           # 任务状态：pending | running | done | failed
```

### 5.4 工作流节点与转换

```
[Start]
  │
  ▼
interpret_user_intent ──失败重试──► error_handler
  │
  ▼
infer_style_profile ──失败重试──► error_handler
  │
  ▼
build_article_blueprint ──失败重试──► error_handler
  │
  ▼
plan_search_queries ──失败重试──► error_handler
  │
  ▼
search_web ──失败重试──► error_handler
  │
  ▼
rank_sources ──失败重试──► error_handler
  │
  ▼
fetch_and_extract ──失败重试──► error_handler
  │
  ▼
generate_article ──失败重试──► error_handler
  │
  ▼
generate_images ──无可用图片则跳过──►
  │
  ▼
push_to_draft ──失败重试──► error_handler
  │
  ▼
ui_feedback
  │
  ▼
[End]
```

---

## 6. 详细 Skill 说明

### Skill 1: interpret_user_intent

- **功能**：根据主题文本和生成配置，解析主角色、文章目标和实际写作策略
- **输入**：`keywords`、`generation_config`
- **输出**：更新 `user_intent`
- **职责**：
  - 规范化 `generation_config`
  - 当 `article_strategy=auto` 时自动推断实际策略
  - 生成主角色、目标角色、文章目标和核心关注问题

---

### Skill 2: infer_style_profile

- **功能**：自动生成文章风格画像
- **输入**：`user_intent`、`generation_config`
- **输出**：更新 `style_profile`
- **实现**：
  - 优先调用 LLM 生成结构化风格画像
  - 若模型不可用或结构化输出失败，则回退到内置风格原型
  - 支持保留用户补充的 `style_hint`
- **风格原型**：
  - `finance_rational`
  - `tech_deep_explainer`
  - `product_review`
  - `trend_commentary`

---

### Skill 3: build_article_blueprint

- **功能**：在搜索前生成结构化文章蓝图
- **输入**：`user_intent`、`style_profile`
- **输出**：更新 `article_blueprint`，并派生兼容旧接口的 `article_plan`
- **职责**：
  - 生成固定章节结构
  - 生成每一节的写作目标和证据需求
  - 生成标题策略、开篇目标、结尾方式和搜索重点
  - 保证包含“局限与风险”和“行动建议”

---

### Skill 4: plan_search_queries

- **功能**：根据文章蓝图规划搜索词
- **输入**：`user_intent`、`article_blueprint`
- **输出**：更新 `search_queries`
- **职责**：
  - 拆分官方事实查询、行业新闻查询、风险验证查询、市场背景查询
  - 将搜索词与搜索意图绑定，供后续排序节点使用

---

### Skill 5: search_web

- **功能**：根据结构化搜索词检索互联网内容
- **输入**：`search_queries`
- **输出**：更新 `search_results`
- **实现**：
  - 主：SerpApi Google
  - 备：Bing Web Search API
  - 免费兜底：DuckDuckGo HTML
  - 输出结构化结果，而不是纯 URL
- **结果字段**：
  - `url`
  - `title`
  - `snippet`
  - `domain`
  - `provider`
  - `query_intent`
  - `source_type`
  - `authority_score`
  - `relevance_score`
  - `final_score`
- **异常处理**：单搜索源失败允许降级；全部无结果则设置 `error`

---

### Skill 6: rank_sources

- **功能**：对搜索结果做可信度与相关度排序
- **输入**：`search_results`
- **输出**：更新排序后的 `search_results`
- **职责**：
  - 优先官网、官方文档、GitHub、论文、权威媒体和研究机构
  - 按搜索意图增加不同来源类型的权重
  - 控制同域名重复数量，保留来源多样性

---

### Skill 7: fetch_and_extract

- **功能**：并发抓取高分来源，提取正文、标题、图片
- **输入**：`search_results`
- **输出**：更新 `extracted_contents`（每项含 `url`、`title`、`text`、`images`、`source_meta`）
- **实现**：
  - 使用 `httpx` 异步并发抓取
  - 主解析：`trafilatura`；备选：`BeautifulSoup4`
  - 筛选图片：宽高 ≥ 300px、格式为 jpg/png/webp
  - 保留搜索阶段的来源元信息，供正文节点使用
- **异常处理**：单 URL 失败跳过；全部失败则报错

---

### Skill 8: generate_article

- **功能**：调用 LLM，将多源内容综合成微信公众号风格文章
- **输入**：`extracted_contents`、`generation_config`、`user_intent`、`style_profile`、`article_blueprint`、`article_plan`
- **输出**：更新 `generated_article.title`、`alt_titles`、`content`
- **实现变化**：
  - 正文节点不再负责策略决策，只按蓝图和证据写作
  - 支持结构化输出和 Markdown 回退解析双通道
  - 必须严格保留蓝图中的二级标题结构
  - 允许用户 `style_hint` 影响最终写作风格
- **Prompt 约束摘要**：

```
你是中文科技公众号总编，根据“用户意图 + 风格画像 + 文章蓝图 + 证据素材”完成文章。
要求：
- 严格依据公开资料写作，不编造事实、数据或案例
- 专业术语首次出现时采用“术语 + 中文解释 + 一句话类比”
- 必须严格保留蓝图中的所有二级标题
- 如果公开资料存在分歧，要明确说明
- 如果证据不足，要明确写出“公开资料尚不足以证明”
- 在合适段落中依次插入 [插图1]、[插图2]、[插图3]
```

- **质量校验**：
  - 主标题 / 备选标题数量与长度
  - 章节标题完整性
  - `[插图1..3]` 顺序完整性
  - 正文长度与“局限 / 行动建议”章节存在性
- **异常处理**：调用失败重试；若结构不完整则带修正反馈重新生成

---

### Skill 9: generate_images

- **功能**：为文章生成封面图与插图
- **输入**：`generated_article`、`extracted_contents`
- **输出**：更新 `generated_article.cover_image`、`illustrations`
- **实现方案**（按优先级）：
  - **方案 A**（默认）：从 `extracted_contents` 筛选高质量相关图片
  - **方案 B**：调用 LLM 生成图片描述文字
  - **方案 C**（可选，需配置）：调用 DALL-E 3 生成图片并上传图床
- **异常处理**：无可用图片时留空或使用默认占位图，不阻断流程

---

### Skill 10: push_to_draft

- **功能**：将图文内容推送至微信公众号草稿箱
- **输入**：`generated_article`（含标题、正文、封面图、插图）
- **输出**：更新 `draft_info`（`media_id`、`url`）
- **实现**：
  1. 获取 `access_token`（自动处理过期刷新，缓存有效期内复用）
  2. 将正文中的 `[插图N]` 替换为实际图片 `<img>` 标签
  3. 调用 `POST https://api.weixin.qq.com/cgi-bin/draft/add` 上传草稿
  4. 解析返回，保存 `media_id`
- **异常处理**：失败重试 3 次；`token` 失效自动刷新后重试

---

### Skill 11: ui_feedback

- **功能**：通过 WebSocket 向前端推送任务最终状态和结果
- **输入**：`draft_info`、`error`、`status`
- **输出**：前端收到任务完成通知、草稿预览链接
- **实现**：
  - 通过 FastAPI WebSocket 推送 JSON 状态消息
  - 日志记录完整任务链路（`structlog` 结构化输出）

---

### 错误处理节点: error_handler

- **功能**：统一处理工作流异常
- **实现**：
  - 记录错误到结构化日志
  - 通过 WebSocket 推送错误状态至前端
  - 支持配置邮件/企业微信告警通知

---

## 7. 前端 UI 规范

### 7.1 技术栈

| 类别 | 选型 |
|------|------|
| 框架 | React 18 + TypeScript |
| UI 组件库 | Ant Design 5.x |
| 状态管理 | Zustand |
| 路由 | React Router v6 |
| 构建工具 | Vite 5.x |
| HTTP | Axios |
| 实时通信 | 原生 WebSocket |

### 7.2 设计风格

- 主色调：`#1677FF`（Ant Design 默认蓝）
- 整体风格：简洁商务，参考 Ant Design Pro
- 布局：左侧导航 + 右侧内容区（Sider + Content）
- 响应式：支持 1280px 以上宽屏，移动端不作要求

### 7.3 页面结构

```
/                  → 重定向至 /task
/task              → 任务创建页（主题输入 + 角色/策略/可选 style_hint）
/task/:id          → 任务详情页（进度条 + 各节点状态 + 草稿预览）
/history           → 历史任务列表
/models            → 文本模型 / 图像模型配置页
/settings          → 配置管理（API Key 等，管理员可见）
```

### 7.4 核心交互

- 任务创建后，页面自动跳转至任务详情页
- 详情页通过 WebSocket 实时显示各 Skill 节点的执行状态（待执行 / 执行中 / 完成 / 失败）
- 草稿生成后展示文章预览（标题 + 正文 + 图片），提供"在微信中查看"跳转链接
- 失败节点高亮显示，并给出错误原因

---

## 8. 接口设计

### 8.1 REST API（FastAPI）

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/tasks` | 创建新任务（传入 `keywords + generation_config`，其中 `generation_config` 支持 `style_hint`） |
| POST | `/api/tasks/{task_id}/retry` | 从失败/终止节点继续执行任务 |
| GET | `/api/tasks/{task_id}` | 查询任务状态 |
| GET | `/api/tasks` | 获取历史任务列表 |
| DELETE | `/api/tasks/{task_id}` | 删除任务记录 |
| GET | `/api/config/style` | 获取当前全局样式配置 |
| PUT | `/api/config/style` | 更新当前全局样式配置 |
| GET | `/api/config/model` | 获取文本模型 / 图像模型配置 |
| PUT | `/api/config/model` | 更新文本模型 / 图像模型配置 |
| GET | `/api/config/themes` | 获取内置主题列表 |
| GET | `/api/config/themes/custom` | 获取自定义主题列表 |
| POST | `/api/config/themes/custom` | 新建自定义主题 |
| PUT | `/api/config/themes/custom/{theme_name}` | 更新自定义主题（含重命名） |
| DELETE | `/api/config/themes/custom/{theme_name}` | 删除自定义主题 |
| POST | `/api/config/themes/custom/import` | 批量导入自定义主题 |
| GET | `/api/accounts` | 获取账号配置列表 |
| POST | `/api/accounts` | 新增账号配置 |
| GET | `/api/accounts/{account_id}` | 查询单账号详情 |
| PUT | `/api/accounts/{account_id}` | 更新账号配置 |
| DELETE | `/api/accounts/{account_id}` | 删除账号配置 |
| POST | `/api/accounts/{account_id}/test` | 测试账号连接（当前支持微信） |
| GET | `/api/articles` | 获取已生成文章列表（从任务中筛选） |
| GET | `/api/articles/{task_id}` | 获取单篇文章详情 |
| PUT | `/api/articles/{task_id}/theme` | 设置文章默认推送主题 |
| POST | `/api/articles/{task_id}/push` | 单篇文章推送到多个账号 |
| POST | `/api/articles/batch-push` | 多文章批量推送到多个账号 |
| GET | `/api/schedules` | 获取定时任务列表 |
| POST | `/api/schedules` | 创建定时任务（含 `generation_config`，支持 `style_hint`） |
| PUT | `/api/schedules/{schedule_id}` | 更新定时任务（含 `generation_config`，支持 `style_hint`） |
| DELETE | `/api/schedules/{schedule_id}` | 删除定时任务 |
| POST | `/api/schedules/{schedule_id}/start` | 启动定时任务 |
| POST | `/api/schedules/{schedule_id}/stop` | 停止定时任务 |
| POST | `/api/schedules/{schedule_id}/run-now` | 立即执行一次定时任务 |

### 8.2 WebSocket

```
WS /ws/tasks/{task_id}
```

推送消息格式：
```json
{
  "task_id": "xxx",
  "status": "running",
  "current_skill": "fetch_and_extract",
  "progress": 40,
  "message": "正在提取网页内容...",
  "result": null
}
```

### 8.3 环境变量配置（`.env`）

```
# 微信公众号
WECHAT_APP_ID=xxx
WECHAT_APP_SECRET=xxx

# 搜索引擎
SERPAPI_API_KEY=xxx
GOOGLE_SEARCH_API_KEY=xxx
GOOGLE_SEARCH_ENGINE_ID=xxx
BING_SEARCH_API_KEY=xxx
# DuckDuckGo HTML 为免费兜底，无需额外 API Key

# LLM
OPENAI_API_KEY=xxx
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o

# 可选：图片生成
DALLE_ENABLED=false

# 服务
API_HOST=0.0.0.0
API_PORT=8000
```

---

## 9. 项目目录结构

```
wechatProject/
├── api/                        # FastAPI 后端
│   ├── main.py                 # FastAPI 应用入口，挂载所有路由 + 调度器生命周期
│   ├── models.py               # Pydantic 数据模型（任务/账号/文章推送/定时任务）
│   ├── store.py                # JSON 持久化存储（tasks/accounts/schedules/style/themes）
│   ├── scheduler.py            # 进程内定时调度引擎（定时触发工作流 + 多账号推送）
│   ├── ws_manager.py           # WebSocket 连接管理与广播
│   ├── logging_config.py       # 日志配置
│   ├── routers/
│   │   ├── tasks.py            # 任务 CRUD 接口
│   │   ├── ws.py               # WebSocket 接口
│   │   ├── config.py           # 样式、主题与模型配置管理接口
│   │   ├── accounts.py         # 多平台账号管理接口
│   │   ├── articles.py         # 文章管理与推送接口
│   │   └── schedules.py        # 定时任务管理接口
├── workflow/                   # LangGraph 工作流
│   ├── article_generation.py   # 文章生成配置、风格原型与兼容 article_plan 辅助函数
│   ├── graph.py                # StateGraph 定义与节点注册
│   ├── state.py                # WorkflowState 定义
│   ├── skills/
│       ├── interpret_user_intent.py # Skill 1
│       ├── infer_style_profile.py   # Skill 2
│       ├── build_article_blueprint.py # Skill 3
│       ├── plan_search_queries.py   # Skill 4
│       ├── search_web.py            # Skill 5
│       ├── rank_sources.py          # Skill 6
│       ├── fetch_extract.py         # Skill 7
│       ├── plan_article_strategy.py # 旧策略节点，暂保留兼容
│       ├── generate_article.py      # Skill 8
│       ├── generate_images.py       # Skill 9
│       ├── push_to_draft.py         # Skill 10
│       ├── ui_feedback.py           # Skill 11
│       └── error_handler.py    # 错误处理节点
│   └── utils/
│       ├── wechat_draft_service.py  # 微信草稿推送服务（token缓存/重试/素材上传）
│       ├── wechat_api.py            # 微信素材与正文图片上传
│       └── markdown_to_wechat.py    # Markdown -> 微信可用 HTML（注入主题样式）
├── frontend/                   # React 前端
│   ├── src/
│   │   ├── pages/              # 页面：创建任务/任务详情/历史/文章管理/定时任务/模型配置/系统设置/账号配置
│   │   ├── store/              # Zustand 状态（任务创建态）
│   │   ├── api/                # API 请求封装（覆盖 tasks/config/accounts/articles/schedules）
│   │   └── App.tsx
│   ├── package.json
│   └── vite.config.ts
├── tests/                      # 测试
│   ├── test_article_blueprint_flow.py
│   ├── test_search_web.py
│   ├── test_fetch_extract.py
│   ├── test_plan_article_strategy.py
│   ├── test_generate_article.py
│   ├── test_generate_images.py
│   ├── test_push_to_draft.py
│   └── test_ui_feedback.py
├── data/                       # 运行时持久化数据（JSON）
│   ├── tasks.json
│   ├── accounts.json
│   ├── schedules.json
│   ├── style_config.json
│   ├── model_config.json
│   └── custom_themes.json
├── logs/                       # 日志目录（不提交 git）
├── main.py                     # 命令行入口
├── requirements.txt            # Python 依赖（锁定版本）
├── .env.example                # 环境变量示例
├── .gitignore
└── CLAUDE.md                   # 开发规范
```

---

### 9.1 模块功能映射（当前实现）

| 模块 | 对应功能 |
|------|----------|
| `api/routers/tasks.py` | 创建任务、查询任务、删除任务、断点重试；任务状态持久化；进度广播 |
| `api/routers/ws.py` + `api/ws_manager.py` | 任务维度 WebSocket 订阅与消息广播 |
| `workflow/graph.py` | 工作流编排：initialize → capture_hot_topics → interpret_user_intent → infer_style_profile → build_article_blueprint → plan_search_queries → search_web → rank_sources → fetch_extract → generate_article → generate_images → push_to_draft/ui_feedback |
| `workflow/article_generation.py` | 统一 `generation_config` 默认值、策略枚举、风格原型与兼容 `article_plan` 辅助函数 |
| `workflow/skills/interpret_user_intent.py` | 解析主题、主角色、文章目标与实际策略 |
| `workflow/skills/infer_style_profile.py` | 自动生成风格画像，支持 `style_hint` 融合 |
| `workflow/skills/build_article_blueprint.py` | 生成结构化文章蓝图，并派生 `article_plan` |
| `workflow/skills/plan_search_queries.py` | 根据蓝图生成结构化搜索词与搜索意图 |
| `workflow/skills/capture_hot_topics.py` | 在文章链路前置执行热点抓取、评分、筛选与关键词回填，失败自动回退 |
| `workflow/skills/search_web.py` | 多搜索源检索（SerpApi/Bing/DuckDuckGo），输出结构化来源结果 |
| `workflow/skills/rank_sources.py` | 对来源做可信度、相关度和多样性排序 |
| `workflow/skills/fetch_extract.py` | 并发抓取高分来源、正文提取（trafilatura + bs4）、图片筛选 |
| `workflow/skills/plan_article_strategy.py` | 旧版策略节点，保留兼容测试与历史逻辑 |
| `workflow/skills/generate_article.py` | 按 `user_intent + style_profile + article_blueprint + extracted_contents` 生成正文，并校验章节/插图标记 |
| `workflow/skills/generate_images.py` | 根据正文 `[插图N]` 标记分配封面图与插图 |
| `workflow/skills/push_to_draft.py` + `workflow/utils/wechat_*.py` | 微信 token 获取、素材上传、Markdown 转 HTML、草稿箱推送 |
| `workflow/utils/tophub_client.py` | TopHub 分类页/榜单页抓取与解析，抽取 rank/title/url/extra/hot_value |
| `workflow/utils/hotspot_ranker.py` | 热点条目评分、过滤、去重与最佳热点选择 |
| `api/routers/config.py` + `api/store.py` | 主题、样式与模型配置：内置主题、自定义主题增删改查、导入导出、全局样式保存、文本模型/图像模型配置 |
| `api/routers/accounts.py` | 多账号配置管理（当前可测试微信连接） |
| `api/routers/articles.py` | 文章列表、文章主题绑定、单篇/批量推送、推送记录 |
| `api/routers/schedules.py` + `api/scheduler.py` | 定时任务 CRUD、启停、立即执行；支持结构化热点捕获配置并在调度执行时前置抓取与回填关键词 |
| `frontend/src/pages/*.tsx` | 可视化任务创建、流程跟踪、历史列表、主题编辑、账号管理、文章推送、定时任务管理；支持角色、策略与可选 `style_hint` 配置 |

---

## 10. 部署与运维

- **Python 版本**：3.11+
- **依赖安装**：`pip install -r requirements.txt`
- **前端构建**：`cd frontend && npm install && npm run build`
- **启动后端**：`uvicorn api.main:app --host 0.0.0.0 --port 8001`
- **命令行模式**：`python main.py --keywords "人工智能 最新进展"`
- **日志**：`structlog` 输出 JSON 格式，存储于 `logs/` 目录

---

## 11. 未来扩展

- 增加人工审核节点：推送前允许用户预览并修改
- 支持更多内容源：RSS Feed、数据库导入
- 自动发布：直接发布（需公众号权限）
- 多账号管理：支持多个微信公众号切换
- 数据统计：文章阅读量、粉丝增长等数据看板

---

## 12. demand 文档持续维护规则（新增）

为保证“项目结构与功能”始终准确，后续每次新增/调整功能时，必须同步更新 `demand.md`，规则如下：

1. 新增接口：同步更新 `8.1 REST API` 表格（方法、路径、用途、影响范围）。
2. 新增目录/文件：同步更新 `9. 项目目录结构`（包含新增文件职责）。
3. 新增业务能力：同步更新 `9.1 模块功能映射`（模块 → 功能一一对应）。
4. 变更工作流节点：同步更新 `5.2/5.4/6` 中工作流结构、节点说明与异常策略。
5. 每次更新文档后，递增版本号并更新日期（文档头部 `版本/更新日期`）。

建议在提测前增加一个检查项：`代码变更是否已同步 demand.md`，避免文档滞后。

---

## 13. 2026-04-02 TopHub 前置热点捕获需求（已实现）

### 13.1 实现范围

- 已在定时任务中引入 `hotspot_capture` 结构化配置（分类、平台、过滤条件、回退主题）。
- 已新增 TopHub 抓取能力：支持分类页平台发现与平台榜单条目解析。
- 已新增热点评分器：按排名、热度、平台权重、关键词偏好综合计算 `selection_score` 并映射星级。
- 已将热点捕获前置到 LangGraph：`initialize -> capture_hot_topics -> interpret_user_intent -> ...`。
- 已实现失败回退链路：优先 `fallback_topics`，再回退到任务原始主题（通常为 `schedule.name`）。
- 已将命中结果写入任务详情：`original_keywords`、`hotspot_candidates`、`selected_hotspot`。

### 13.2 关键接口与数据变更

- `ScheduleConfig` / `CreateScheduleRequest` / `UpdateScheduleRequest` 支持 `hotspot_capture`。
- `TaskResponse` 新增热点相关字段：
  - `original_keywords`
  - `hotspot_capture_config`
  - `hotspot_candidates`
  - `selected_hotspot`
- 前端 `ScheduleManage` 页面已升级为“热点捕获配置”，保持现有 Ant Design 视觉与交互风格。

### 13.3 新增测试

- `tests/test_tophub_client.py`
- `tests/test_hotspot_ranker.py`
- `tests/test_scheduler_hotspot_capture.py`
- `tests/test_workflow_hotspot_capture.py`

## 14. 2026-05-05 多数据源热点与 Planner 前置蓝图（已实现）

### 目标

- 热点监控从单一 TopHub 配置升级为多数据源 provider 架构。
- 定时任务可以选择具体榜单平台，例如 TopHub 节点、36氪 RSS、华尔街日报 RSS。
- Planner Agent 在搜索前携带任务、热点、可用 article skills 给 AI，由 AI 选择写作风格 skill，并生成初版文章结构蓝图。

### 关键实现

- `workflow/utils/hotspot_providers.py` 新增统一热点 provider registry：
  - `TopHubHotspotProvider`
  - `RssHotspotProvider`
  - `HtmlRankingHotspotProvider`
- `workflow/agents/hotspot.py` 改为按平台 `source` 调用 provider，合并候选后复用 `rank_hotspots` 评分和筛选。
- `api.models.HotspotPlatformConfig` 支持 `source`、`provider_id`、`category`、`parser_options`，并兼容旧 TopHub `path` 配置。
- `/api/hotspots/platforms` 返回内置多源平台目录，包含 36氪快讯和华尔街日报全球新闻。
- `workflow/agents/planner.py` 新增结构化 `PlannerOutput`，模型可输出：
  - `selected_skill`
  - `style_profile`
  - `initial_article_blueprint`
  - `search_plan`
  - `visual_plan`
- `workflow/nodes/research_plan.py` 会把 planner 初版蓝图的 `search_focuses` 转成搜索 query。
- `workflow/nodes/plan_article_angle.py` 在搜索后蓝图修正时继承 planner 初版蓝图和已选 skill。
- 前端 `ScheduleManage` 支持配置 TopHub、RSS / Feed、公开榜单页三类热点平台。

### 测试覆盖

- `tests/test_hotspot_providers.py`
- `tests/test_schedule_hotspot_models.py`
- `tests/test_planner_agent.py`
- `tests/test_workflow_hotspot_capture.py`
- `tests/test_scheduler_hotspot_capture.py`

## 15. 2026-05-05 Planner 蓝图时机修正（已实现）

- Planner Agent 不再调用 AI 生成搜索前 `initial_article_blueprint`，也不再把临时蓝图写入 `article_blueprint`。
- Planner Agent 只输出 `selected_skill`、`style_profile.content_type=wechat_public_account_article`、搜索角度、视觉策略和质量阈值。
- `workflow/nodes/research_plan.py` 不再消费蓝图 `search_focuses`；搜索 query 只来自主题、热点分类和搜索角度。
- `workflow/nodes/plan_article_angle.py` 是正式文章蓝图生成入口：AI 明确知道目标是微信公众号文章，并基于 `selected_skill + source_context + search_materials + evidence_pack` 自动生成蓝图。
- 该修正覆盖上一节中“Planner 前置蓝图”的描述；后续以本节为准。

## 16. 2026-05-05 Fallback 蓝图优化（已实现）

- `_build_fallback_blueprint` 在模型不可用或结构化输出失败时，也会按微信公众号文章语境生成蓝图。
- fallback 优先使用搜索材料生成来源驱动结构；材料不足时再结合 `selected_skill.section_guidance`、`evidence_policy`、`writing_constraints` 和证据缺口补齐章节。
- 量子科技等专项 skill 保留术语解释、工程指标、产业门槛和风险边界要求，但不再完全依赖固定模板。

## 17. 2026-05-05 文章蓝图结构限制放开（已实现）

- `plan_article_angle` 不再限制 AI 生成 4-6 个 H2，也不再截断章节数量。
- AI 可以根据 `selected_skill`、搜索内容和证据包自行决定章节数量、顺序和结构类型。
- 代码只保留空标题/空目标过滤；当证据包存在明显缺口且模型完全没有表达风险/证据边界时，才追加一个安全边界章节。
- `source_driven_framework` 和 `evidence_map` 仍用于帮助写作节点理解证据来源，但不再反向限制文章结构。

## 18. 2026-09-24 生成链路提速与推送/发布链路优化（已实现）

完整说明见 [文章生成链路提速与推送/发布链路优化](docs/2026-09-24-article-chain-latency-and-publish-optimization.md)。

### 18.1 工作流节点变更

优化后的节点顺序与分支（两处 fan-out 的分支深度均为 1，join 才是真正的 barrier）：

```text
capture_hot_topics → intake_task_brief → planner_agent → analyze_hotspot_opportunities
  → plan_research → run_research → build_evidence_pack → resolve_article_type
      ├─→ design_viral_strategy ─┐
      └─→ outline_planner ───────┴─→ merge_outline_strategy
  → compose_draft → normalize_draft → plan_visual_assets
      ├─→ parallel_review ───────────────────────────────┐
      └─→ image_agent（生图 + 图片审核）─────────────────┴─→ quality_gate
                                       ├─ 通过 → assemble_article → push_to_draft
                                       └─ 返工 → targeted_revision → 写作/出图
```

新增节点：

| 节点 | 职责 |
|------|------|
| `merge_outline_strategy` | 确定性合并并发的传播策略与文章蓝图，产出统一 `outline_result` |
| `normalize_draft` | 确定性修复草稿机械问题（小标题泄漏 URL、小标题过多、重复段落、编辑语言残留） |
| `parallel_review` | 并发执行文章评审与传播评审；硬性结构失败时取消在途传播评审 |

变更节点行为：

| 节点 | 变更 |
|------|------|
| `planner_agent` | 新增 `PLANNER_MODE`，默认 `rules` 不调用 LLM（规则引擎已能产出完整研究合同） |
| `run_research` | 同一轮内多个查询并发执行（`RESEARCH_CONCURRENCY`），轮次语义不变 |
| `outline_planner` | 拆分为 `outline_planner_base_node`（不合并传播策略），合并由 `merge_outline_strategy` 承接 |
| `compose_draft` | 机械违规改为确定性修复，仅内容级违规才二次生成；返工传入 `previous_draft` 与 `draft_violations`，token 预算 4000→2500 |
| `plan_visual_assets` | 由并发分支移入主干（确定性、几乎零耗时），用于保证两条分支深度一致 |
| `image_agent` | 合并「生图 + 图片审核」为一个节点，使该分支深度为 1；`review_visual_assets` 不再是独立图节点 |
| `review_article_draft` | `max_tokens` 1400→600；不再写 `writing_state["viral_review"]`（消除并发写冲突） |
| `review_viral_potential` | `max_tokens` 1400→700；`design_viral_strategy` 1600→700 |

并发状态合并（`workflow/state.py`）：`status` / `progress` / `current_skill` / `error` 声明了 reducer。LangGraph 不允许同一步对同一 state key 写入多次，没有 reducer 时**每个真实任务都会在 fan-out 处抛 `InvalidUpdateError`**。`status` 采用终态优先（`failed`/`cancelled` 高于 `running`），避免失败被健康分支掩盖。

### 18.2 推送与发布链路变更

- 工作流推送节点改为按任务绑定的账号（`publish_targets`）推送；全局 `WECHAT_APP_ID/SECRET` 仅作降级，结果显式标记 `source=env_fallback` 或 `mock=true`。
- 新增草稿箱 + 直接发布双模式：`publish_policy.auto_publish`（默认 false）、`publish_retry_limit`、`publish_poll_interval_seconds`、`publish_poll_max_attempts`。
- 新增 `workflow/utils/wechat_publish.py`（`freepublish/submit` + `freepublish/get` 轮询 + 失败原因翻译）；发布失败不影响已创建的草稿。
- 新增 `workflow/utils/wechat_token.py`：access_token 缓存写入 Redis，进程重启复用，失败回退进程内存。
- 文内插图上传由串行改为并发（并发度 3），顺序保持。
- `PushRecord` 新增 `publish_status`、`publish_id`、`theme_name`、`attempt`；工作流推送记录按 `push_id` 去重合并进任务。
- `POST /api/articles/{id}/push`、`POST /api/articles/batch-push` 新增 `auto_publish` 参数。
- `CreateTaskRequest` 新增 `account_ids`、`theme_name`。
- `api/store.py` 新增 `resolve_theme_style()`，统一主题解析，避免预览与推送主题不一致。

### 18.3 配置与依赖变更

- `ModelConfig` 新增 `text_fast`（快模型），用于规划与评审阶段；留空回退主模型。
- 新增模块：`workflow/runtime_settings.py`、`workflow/model_factory.py`、`workflow/utils/draft_quality.py`、`workflow/utils/redis_client.py`、`workflow/utils/search_cache.py`、`workflow/utils/wechat_token.py`、`workflow/utils/wechat_publish.py`、`workflow/nodes/parallel_review.py`、`workflow/nodes/normalize_draft.py`、`workflow/nodes/merge_outline_strategy.py`。
- `requirements.txt` 新增 `redis>=5.0.0`。
- `.env.example` 新增：`OPENAI_FAST_MODEL`、`OPENAI_FAST_API_KEY`、`OPENAI_FAST_API_BASE`、`RESEARCH_CONCURRENCY`、`IMAGE_CONCURRENCY`、`LLM_CONCURRENCY`、`LLM_TIMEOUT_SECONDS`、`LLM_MAX_RETRIES`、`PLANNER_MODE`、`SEARCH_CACHE_ENABLED`、`SEARCH_CACHE_TTL_SECONDS`、`REDIS_URL`。
- `workflow/state.py` 新增 `publish_targets`、`publish_records`、`article_theme`。
- 前端 `ModelConfig` 类型新增 `text_fast`，「模型配置」页新增快速模型区块；「新建任务」新增「直接发布到公众号」开关。

### 18.4 相关文档

- [文章生成链路提速与推送/发布链路优化](docs/2026-09-24-article-chain-latency-and-publish-optimization.md)
- [单机部署与运维指南（2C2G）](docs/2026-09-24-deployment-and-operations-2c2g.md)

## 19. 2026-09-24 存储生产化、工作流健壮性、调度、统计与运维（已实现）

### 19.1 存储生产化（PostgreSQL）

- 新增 `api/db.py`：SQLAlchemy 2.0 声明式表（`tasks`、`topics`、`reviews`、`workflow_run_steps`、`accounts`、`users`、`schedules`、`article_stats`）、引擎管理、`init_db()`、`database_health()`。
- 新增 `api/persistence.py`：JSON 与数据库双后端，按快照 diff 只写变化的行。
- `api/store.py` 改为兼容层，函数签名不变，路由层零改动；新增 `bootstrap_storage()` 负责建表、旧 JSON 一次性导入与备份。
- 存储层采用**同步引擎**：`api/store.py` 与全部路由本就是同步 API，单机数据量小，写入路径不经过异步驱动的额外往返，实现更简单（详见 19.10）。
- 未配置 `DATABASE_URL` 时维持原有 JSON 文件行为。

### 19.2 工作流健壮性

- 断点续跑：节点守卫 + `completed_nodes` 持久化；重试只重跑失败节点及其下游。
- 任务取消：新增 `POST /api/tasks/{id}/cancel`；节点边界检测取消并返回 `cancelled`；所有条件路由新增 `cancelled → ui_feedback` 映射。
- 并发闸门：`WORKFLOW_MAX_CONCURRENCY`（默认 2），等待槽位的任务状态为 `queued`。
- 任务创建、重试、热点转任务统一走 `start_workflow_task()`。
- 新增 `api/task_control.py`。

### 19.3 调度生产化

- `ScheduleMode` 新增 `cron`；`ScheduleConfig` 新增 `cron_expression`、`timezone`、`missed_runs`。
- 用 APScheduler `CronTrigger` 解析 5 段式表达式，按计划时区求值后换算 UTC。
- 下一次触发时间严格晚于当前时间，避免同一时刻反复触发。
- `reconcile_on_startup()`：一次性计划过期则立即执行；循环计划只记 `missed_runs` 并滚动，不补跑一批。

### 19.4 数据反馈闭环

- 新增 `ArticleStats` 模型与 `article_stats` 存储。
- 新增接口：`GET /api/stats/overview`、`GET /api/stats/articles`、`GET /api/stats/{task_id}`、`PUT /api/stats/{task_id}`、`POST /api/stats/sync`。
- 数据来源分级：微信 `datacube/getarticletotal` 自动同步（按标题匹配回任务）+ 手动录入兜底。
- 「已发布」判定来自推送记录的 `publish_status == "published"`。

### 19.5 其他新增接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 数据库 / Redis / 调度器健康检查 |
| GET | `/api/search` | 任务、文章、热点统一搜索 |
| PUT | `/api/articles/{task_id}/content` | 在线编辑标题/摘要/正文/封面/插图并重新渲染 |
| POST | `/api/tasks/{task_id}/cancel` | 取消待执行或运行中的任务 |
| GET | `/api/stats/overview` | 统计总览 |
| GET | `/api/stats/articles` | 按日趋势与 Top 文章 |
| GET | `/api/stats/{task_id}` | 单篇统计 |
| PUT | `/api/stats/{task_id}` | 手动录入统计 |
| POST | `/api/stats/sync` | 同步微信阅读数据 |

### 19.6 运维能力

- 日志轮转：`logs/app.log` 使用 `RotatingFileHandler`（默认 10MB × 5，可用 `LOG_MAX_BYTES`/`LOG_BACKUP_COUNT` 调整）；`LOG_FORMAT=json` 可输出 JSON。
- 失败告警：新增 `api/alerts.py`，由 `error_handler` 调用，支持企业微信 JSON webhook，默认关闭，每任务最多 3 条。
- 新增部署文档 `docs/2026-09-24-deployment-and-operations-2c2g.md`（依赖、配置、内存预算、swap、备份恢复、故障处理）。

### 19.7 数据模型变更

- `TaskStatus` 新增 `queued`、`cancelled`。
- `TaskResponse` 新增 `completed_nodes`、`publish_account_ids`。
- `ScheduleConfig` / `CreateScheduleRequest` / `UpdateScheduleRequest` 新增 `cron_expression`、`timezone`；`ScheduleConfig` 新增 `missed_runs`。
- 新增 `ArticleStats`、`UpdateArticleStatsRequest`、`StatsOverview`、`StatsTrendPoint`、`StatsTopArticle`、`StatsArticlesResponse`、`StatsSyncResponse`、`HealthResponse`、`SearchResponse`、`UpdateArticleContentRequest`。
- `PushArticleRequest` / `BatchPushRequest` 新增 `auto_publish`。

### 19.8 依赖与配置

- `requirements.txt` 新增：`sqlalchemy>=2.0.0`、`psycopg2-binary>=2.9.9`、`apscheduler>=3.10.0`、`greenlet>=3.0.0`。
- `.env.example` 新增：`WORKFLOW_MAX_CONCURRENCY`、`DATABASE_URL`、`SCHEDULER_TIMEZONE`、`LOG_MAX_BYTES`、`LOG_BACKUP_COUNT`、`LOG_FORMAT`、`ALERT_WEBHOOK`、`ALERT_EMAIL`。

### 19.9 测试

新增 `tests/test_store_postgres.py`、`tests/test_task_cancel.py`、`tests/test_checkpoint_resume.py`、`tests/test_scheduler_cron.py`、`tests/test_stats_router.py`、`tests/test_graph_pipeline.py`。后端合计 268 passed（Python 3.11）。

`tests/test_graph_pipeline.py` 用桩节点完整走一遍图，专门守护两处并发编排缺陷（详见 18.1 的状态 reducer 说明与并行分支深度要求）：完整管线不重复执行任何节点、并发分支失败必须落到 `error_handler`、中途取消不得推送草稿。

`tests/conftest.py` 新增 autouse 夹具 `isolate_local_storage`：把 `DATA_DIR`、全部 JSON 路径常量与 `_KIND_REGISTRY` 重定向到每个用例的 tmp 目录并在结束后还原。此前测试会覆盖甚至重命名开发者本地的 `data/*.json`（`bootstrap_storage()` 用例会把它们改成 `*.imported`），现已不再影响本地运行态数据。

### 19.10 前端（Phase F）

- `TaskCreate` 改为三步向导（主题与热点 / 受众与策略 / 发布与审核），研究策略与图片设置收进「高级设置」折叠区，英文标签全部中文化，新增「发布账号（可选）」多选（提交为 `account_ids`）；三个步骤保持挂载、仅切换可见性。
- `TaskDetail` 新增「发布状态」表（账号、推送状态、发布状态、publish_id、主题、尝试次数、草稿链接），原 20+ 个原始 JSON 信号卡收进默认折叠的「开发者诊断」区，新增「取消任务」「编辑文章」操作，`SKILL_STEPS` 更新为 `merge_outline_strategy` / `normalize_draft` / `plan_visual_assets` / `parallel_review` / `image_agent`。
- `ArticleManage` 新增在线编辑弹窗（标题/摘要/正文/封面/插图增删与排序），推送弹窗新增「直接发布到公众号」开关（默认关闭并提示不可撤回），新增发布状态标签与筛选。
- `ReviewCenter` 每行新增「查看任务详情」「查看文章」跳转。
- `WorkbenchShell` 顶栏搜索接入 `/api/search`（300ms 防抖，按任务/文章/热点分组），铃铛显示真实待处理数量（需人工复核 + 失败任务）。
- 新增「数据看板」`/stats` 页面（总览卡片、7/30 天趋势折线、Top 文章表、手动录入、同步微信数据）；趋势图使用内联 SVG，未引入新的 npm 依赖。
- `/schedules` 导航名称由「发布记录」改为「定时计划」。

### 19.11 运行环境

- 运行环境统一为 **Python 3.11**（原 `.venv` 为 Python 3.9，已重建并保留旧环境备份 `.venv39.backup/`）。
- 依赖全部使用 3.11 预编译 wheel，不再需要 MSVC 工具链。
- 代码在 3.9 与 3.11 下均通过全部测试；LangGraph 版本兼容 0.6.x 与 1.x（fan-out 与状态 reducer 行为均已验证）。

### 19.12 前端修复：三步向导按步骤卸载导致提交崩溃（已修复）

**现象**：在「新建任务」第三步点击「启动创作流程」时抛出
`Cannot read properties of undefined (reading 'trim')`。

**根因**：`TaskCreate` 原先按当前步骤条件渲染（`{currentStep === 0 ? renderStepOne() : null}`）。
Ant Design 的 `Form` 会在 `Form.Item` 卸载时**注销该字段**，因此在第三步提交时 `values` 中已不含第一步的 `keywords`，
随后 `values.keywords.trim()` 对 `undefined` 取属性而崩溃。同一根因还导致「上一步」返回时第一步已填内容被清空。

**修复**：

1. 三个步骤改为**全部挂载、仅切换可见性**（非当前步骤加 `display: none`），表单字段始终注册。
2. `handleSubmit` 改为 `String(values.keywords ?? '').trim()`，并在关键词为空时提示并跳回第一步，而不是抛错。
3. 新增 `onFinishFailed`：必填项校验失败时自动跳回该项所在步骤，避免错误提示藏在隐藏步骤里看不见。

**同类加固**：`TopicCenter`（`topic.tags` 可能含 null）、`ScheduleManage`（标签数组）、`ArticleManage`（在线编辑表单的 title/summary/coverImage/插图，均为非必填）的 `.trim()` 调用统一改为先强制转字符串。

**测试**：`TaskCreate.test.tsx` 新增 2 项回归测试 —— 在第三步提交仍能带上前面步骤的值；在步骤间来回切换不丢失已填内容。原先有 2 项测试断言「后续步骤字段不在文档中」，实际是在固化这个缺陷，已改为断言「已挂载但不可见」。

**验证**：前端 `tsc --noEmit` / `npm run lint` / `npm run build` 全部通过，`npm test` **66 passed / 1 skipped**；后端 268 passed。


## 20. 2026-10-09 来源过滤、热点原文优先与结构化输出可用性（已实现）

### 20.1 问题现象

用户反馈两点：

1. 自动搜索回来的文章「需要自行过滤」——低质、跑题、重复来源直接进入正文。
2. 选择热点自动生成的文章**结构完全一致**——「可以先读取对应的热点的文章，再决定对应的结构，然后生成对应的文章」。

### 20.2 根因诊断（基于运行日志与落库数据，非推测）

排查发现两个现象是**同一根因的不同表现**。日志显示每个 LLM 调用的 `completion_tokens` 都恰好等于上限：

```
plan_article_angle_fallback    completion_tokens=1800 (==上限)  "length limit was reached"
compose_draft_fallback         completion_tokens=4000 (==上限)
review_article_draft_fallback  completion_tokens=600  (==上限)
```

当时 `data/model_config.json` 的 `text` 层配置的是**推理模型** `deepseek/deepseek-v4-pro-0813`，而 `text_fast` 未配置。
推理 token 计入 `completion_tokens`，模型把全部预算花在推理上，没有输出可解析的 JSON，
`with_structured_output` 抛「无法解析」→ **每个阶段都退回确定性模板**。

真实任务 `1132364a` 的落库结果与推断完全一致：

| 字段 | 实际值 | 含义 |
|---|---|---|
| `blueprint.framework` | 取自 `general_tech_explainer` 的静态 `framework` | 走的是 `_build_fallback_blueprint` |
| `blueprint.sections` | `先确认发生了什么` / `仍需验证的关键变量` | `_build_source_driven_sections` 的固定标题 |
| `draft_generation_mode` | `fallback` | 正文也是模板 |

且 `_build_source_driven_sections` 对每篇文章都输出**四个写死的标题**；由于 LLM 全部失败，模板成了唯一实际路径。

另外两个结构性缺失：

- `build_evidence_pack` 只分组**不过滤**，只要求正文 ≥ 50 字、仅按 URL 精确去重；原有 `rank_sources` 节点已随重构删除。
- 热点的原始链接**从未被抓取**；且 TopHub 的 `url` 是跳转链接而非原文。

### 20.3 修复内容

#### 20.3.1 结构化输出可用性（根因）

- `text_fast` 语义调整为**结构化输出模型**：所有 `with_structured_output` 阶段默认走该层，
  并新增 `LLM_STRUCTURED_TIER=fast|strong`、`LLM_STRONG_STAGES` 支持按阶段覆盖；
  `text_fast` 未配置时自动回退主模型（向后兼容）。
- 新增 `invoke_structured()`：把失败归类为 `truncated` / `other`，记录专用事件 `llm_structured_truncated`，
  按 `LLM_TRUNCATION_RETRY_FACTOR`（默认 2，设为 1 关闭）放大预算重试一次；
  否则抛出 `StructuredOutputError(reason=...)`，由各阶段写入降级原因。
- 各阶段 token 上限改为可配置（`LLM_MAX_TOKENS_{PLANNER,BLUEPRINT,STRATEGY,DRAFT,DRAFT_REVISION,REVIEW}`），
  默认值按非推理模型留足 JSON 余量。
- 新增 `GET /api/config/model/effective`：返回每个阶段生效的模型层、模型名与预算，
  未配置结构化模型时返回明确警告。这类误配此前完全不可见。

#### 20.3.2 来源过滤

新增 `workflow/utils/source_filter.py`（纯确定性，不消耗 LLM），四道关卡：

| 关卡 | 规则 | 默认阈值 |
|---|---|---|
| 质量 | 正文字符数、句子数 | `SOURCE_MIN_CHARS=400`、`SOURCE_MIN_SENTENCES=3` |
| 官方豁免 | 官方/文档类来源的较短下限 | `SOURCE_OFFICIAL_MIN_CHARS=150` |
| 相关性 | 主题分词（中文 bigram + 英文词）与标题+正文前 500 字的重合率 | `SOURCE_MIN_RELEVANCE=0.12` |
| 近重复 | 正文前 600 字 shingle 的 Jaccard 相似度 | `SOURCE_NEAR_DUP_SIMILARITY=0.85` |
| 域名上限 | 单域名最多保留条数 | `SOURCE_MAX_PER_DOMAIN=2` |

- 低权威来源（community/aggregator/social/unknown）保留为线索但标记 `needs_caution`，不单独支撑核心事实。
- 接入两处：`run_research`（每轮抓取后，使充分性评估与证据包只看到合格内容）与 `build_evidence_pack`（兜底防绕过）。
- 掉因可审计：`research_state.source_filtering = {kept, dropped, reasons, insufficient, dropped_items}`。
- **来源不足时按产品选择继续生成**：置 `insufficient=True` 并强制 `human_review_required`，不中止任务。

#### 20.3.3 热点原文优先决定结构

- 新增节点 `fetch_hotspot_source`，位置 `analyze_hotspot_opportunities → fetch_hotspot_source → plan_research`：
  - 解析 TopHub 等榜单的跳转链接（取 `url`/`target`/`link`/`goto` 参数）拿到真实原文地址；
  - 复用 `_fetch_and_extract_single` 抓取并用来源过滤器校验；
  - 失败不阻断流程，记录 `hotspot_source_status = resolved | filtered_out | unavailable | disabled`。
- 从原文**确定性派生检索词**（原文标题精确检索、正文中的数字/金额/百分比信号、引号内的机构或产品名），
  在 `plan_research` 中**前插到优先级最前面**，固定模板词降级为补充。
- 蓝图以原文为主料：`_collect_search_materials` 把原文标为 `is_primary`、`angle=hotspot_source` 并排在最前；
  `_build_source_context` 新增 `primary_source` 块，并指示模型「先从此文提炼叙事主线，再用其它来源佐证、补背景、补反向观点」。
- 素材裁剪：非主源素材由 12×900 字降为 6×400 字（主源单独放宽到 3000 字），显著降低 `prompt_tokens`。

#### 20.3.4 结构去模板化

- 重写 `_build_source_driven_sections`：保留叙事职责分桶（事件/证据/驱动/案例/张力），
  但**标题由该桶内最强 claim 生成**（新增共享工具 `workflow/utils/headings.py::subject_from_claim`），
  不再使用四个常量字符串。不同素材必然产生不同标题集合。
- `_build_fallback_draft` 同步去模板化：章节标题由证据生成，`alt_titles` 由真实候选或素材派生，
  移除 `已经发生的变化` / `数据把问题带向哪里` / `现在还不能下什么结论` 等固定文本。
- 蓝图 prompt 明确禁止通用占位标题，并要求「两个不同故事不得共享同一组标题」。
- **修复真实缺陷**：`plan_research` 中 `int(item.get("priority") or 99)` 会把合法的 `priority=0` 当成缺失值，
  导致原文派生检索词被排到末尾；已改为 falsy-safe 的 `_priority_of()`。
- **清理死代码**：删除重复定义的 `_build_fallback_blueprint`（后者覆盖前者）、
  无引用的 `_build_legacy_fallback_blueprint` 与 `_section_from_material`（合计约 250 行）。

### 20.4 降级可见化

- 状态新增：`planning_state.blueprint_source`（`llm`|`fallback`）、`planning_state.blueprint_degraded_reason`、
  `writing_state.draft_degraded_reason`、`viral_state.strategy_degraded_reason`、`writing_state.review_degraded_reason`。
- 任务详情页在正文区顶部显示醒目告警条，列出降级原因与处理建议（原信息埋在「开发者诊断」折叠区）。
- 模型配置页把「快速模型」改为「结构化模型（建议必填）」，未配置时显示警告。

### 20.5 配置项

新增：`LLM_STRUCTURED_TIER`、`LLM_STRONG_STAGES`、`LLM_TRUNCATION_RETRY_FACTOR`、
`LLM_MAX_TOKENS_{PLANNER,BLUEPRINT,STRATEGY,DRAFT,DRAFT_REVISION,REVIEW}`、
`SOURCE_MIN_CHARS`、`SOURCE_OFFICIAL_MIN_CHARS`、`SOURCE_MIN_SENTENCES`、`SOURCE_MIN_RELEVANCE`、
`SOURCE_NEAR_DUP_SIMILARITY`、`SOURCE_MAX_PER_DOMAIN`、`SOURCE_MIN_SURVIVORS`、`HOTSPOT_SOURCE_ENABLED`。
`.env.example` 已同步（含中文注释说明推理模型陷阱）。

### 20.6 状态与图变更

- `WorkflowState` 新增 `hotspot_sources`、`hotspot_source_status`、`hotspot_source_error`、`hotspot_source_queries`。
- 图新增 1 个节点（共 23 个），插在主干上，**不改变两处 fan-out 的分支深度**（上一轮修复的 join 竞态约束）。
- `fetch_hotspot_source` 失败不阻断：降级为 `unavailable` 并继续既有检索流程。

### 20.7 测试

新增：

- `tests/test_source_filter.py`（12 项）：四道关卡、官方豁免、低权威标记、掉因可审计、不足标记。
- `tests/test_hotspot_source_first.py`（12 项）：跳转链接解析、URL 去重、检索词派生、成功/过滤失败/异常/禁用四种状态。
- `tests/test_blueprint_structure_varies.py`（7 项）：**两个不同故事必须产出不同标题集合**、旧占位标题不再出现、
  标题不回显原始来源标题与 URL、热点原文改变结构且标题取自正文而非标题、降级来源被记录、原文检索词前移。
- `tests/test_structured_truncation.py`（7 项）：截断分类、放大预算重试、持续截断抛出精确错误、
  可配置关闭重试、非截断错误不重试、无模型时记录降级原因。
- `tests/test_graph_hotspot_source.py`（4 项）：新状态通道已声明、节点位于正确位置、状态更新不触碰未声明通道、检索词到达规划。
- 重写 `tests/test_model_factory.py` 以覆盖新的路由语义（`STRUCTURED_STAGES`、tier 切换、按阶段钉住、生效路由输出）。

更新：`test_run_research.py` 的样例文本改为真实长度且与主题相关（原为单句且与中文主题无关，被新的相关性与质量关卡正确拒绝）；
`test_review_article_draft.py`、`test_revision_targeted.py`、`test_plan_article_angle.py` 的 token 与 prompt 断言改为读取配置值。

### 20.8 验证

- 后端：**315 passed**（原 273，新增 42 项）。
- 前端：`tsc --noEmit` / `npm run lint` / `npm run build` 全部通过，`npm test` 66 passed / 1 skipped。
- `GET /api/config/model/effective` 正确报告当前误配：`fast_tier_configured=false`、全部阶段落在 `strong`，并给出警告。
- 本地 `data/` 完整无损（tasks/accounts/reviews/schedules/topics/users/article_stats 均在，无 `.imported` 残留）。

### 20.9 运维提示

**这是本项目最容易静默失败的一处配置**：把推理模型当作结构化输出模型使用时，每个阶段都会退回模板，
而表面上仍会「成功」生成一篇结构固定的文章。上线前请确认：

1. 「模型配置」页的**结构化模型**已填写，且是**非推理模型**；
2. 或调用 `GET /api/config/model/effective` 检查 `fast_tier_configured` 与 `warning`；
3. 日志中不出现 `llm_structured_truncated` / `*_fallback` 事件。


## 21. 2026-10-09 前端设计系统重建与公开门面页（已实现）

目标：以设计奖项（Awwwards 等）标准重做页面样式。用户明确的"页面模型需要配置"经确认为
**设计系统 / 令牌层需要先建立**。详细设计与实测数据见
`docs/2026-10-09-frontend-design-system-and-landing.md`。

### 21.1 已确认决策

| 决策项 | 选择 |
|---|---|
| 视觉方向 | 明亮极简瑞士风（International Typographic Style） |
| 范围 | 新增公开门面页 + 全面升级控制台 |
| antd 策略 | 保留 antd 并彻底重皮，页面骨架换自有布局组件 |
| 动效 | 大胆动效为主；移动端不做重点（门面页与登录页仍做完整响应式） |

### 21.2 改造前实测问题

- `frontend/public/` 为空，`index.html` 引用不存在的 `/vite.svg` → **favicon 是 404**；
- 令牌与 antd 主题声明 `Noto Sans SC` / `Noto Serif SC`，但**从未加载** → 期望的衬线排版完全没渲染；
- **两套令牌并存**（`--app-*` 暖纸+青 / `--color-*` 冷蓝灰），且浅色配色在 `variables.css` 里**复制两份**；
- **品牌色自相矛盾**：代码 `#0f766e` vs `CLAUDE.md:114` 的 `#1677FF`；
- **101 处内联 `style={{}}`**（TaskCreate 34、StyleConfig 25、ScheduleManage 14），7/15 页面无 CSS Module；
- **零动效**：`@keyframes` 0 个、`view-transition` 0 个、`prefers-reduced-motion` 0 条，`focus-visible` 仅 2 处；
- 导航元数据里的 `contextEyebrow` / `contextDescription` 被 Shell 用 `display: none` **主动隐藏**；
- `/` 在 `RequireAuth` 内重定向到 `/task`，**没有公开门面页**。

### 21.3 实现内容

- **令牌层**：新增 `styles/tokens.css`（原始层 + 语义层 + 深色仅覆盖语义层），删除两套并行体系；
  `variables.css` 降级为兼容别名块（`--app-bg-gradient` 与侧栏背景被抹平为纯色，卡片阴影改为 `none`）。
- **防漂移**：新增 `styles/tokens.ts` 镜像 antd 需要的字面量令牌，`theme.ts` 由令牌生成；
  `tokenParity.test.ts`（62 项）解析 CSS 逐值校验。**这直接消除了品牌色分歧的成因**。
- **基础层**：新增 `public/favicon.svg` 与 `og-image.svg`（修掉 404）、`BrandMark` 组件、
  `theme-color` / `og:*` 元信息；`global.css` 瑞士化并新增**全局 `:focus-visible`** 与
  **`prefers-reduced-motion` 兜底**。
- **布局组件**：新增 `components/layout/`：`PageHeader` / `Panel` / `Toolbar` / `StatGrid`+`Stat` /
  `EmptyState` / `KeyValueList` / `Stack`+`Split`+`Grid`。
- **Shell 重做**：直角侧栏、当前项用 2px 强调条（非填色）、**启用被隐藏的 eyebrow 与说明**、
  新增 **⌘K** 聚焦全局搜索、尺寸全部令牌化。
- **公开门面页**：`/` 改为公开 `LandingPage`（Hero + 八阶段管线滚动进度 + 能力网格 + 指标滚动 + 页脚），
  **纯静态、不新增公开接口**；`/login` 仍公开，控制台 14 条路由鉴权不变。
- **动效原语**（`src/motion/`，**不引入新依赖**）：`useReducedMotion` / `useReveal` /
  `useScrollProgress`（写 `--scroll-progress`）/ `useCountUp`；新增 4 个 keyframes（此前为 0），
  全部只动画 `transform`/`opacity` 且受 `prefers-reduced-motion` 约束。

### 21.4 测试与守卫

新增守卫生效：`noInlineStyle`（禁止新增内联样式对象）、`noLegacyTokens`（禁止新增旧令牌引用）、
`reducedMotion`（reduce 或缺少 API 时立即显示内容）、`Landing`（无需鉴权即可渲染、CTA 指向 `/login`）。
前两个守卫使用**「只减不增」的待迁移清单**：新文件违规失败，清单里修好的文件也因"陈旧项"失败。

**验证**：前端 **144 passed / 1 skipped**（原 66 passed / 1 skipped，净增 78 项）；
`tsc --noEmit` / `npm run lint`（0 warning）/ `npm run build` 全绿。

### 21.5 与计划的偏差（需知悉）

1. **未引入字体文件**：核查后 `node_modules` 无任何 woff2/woff、`public/` 为空、
   Windows 系统字体不可再分发。因此拉丁与中文统一走系统栈，瑞士身份建立在**排版纪律**上
   （严格模数、负字距、等宽大写小标签、`tabular-nums`、发丝线、网格），并在 `tokens.css` 留出接入点。
   这比加一个指向不存在文件的 `@font-face` 或塞入无授权字体更诚实。
2. **控制台 15 个页面已迁移 8 页**：Stats、History、TaskCreate、TaskDetail、TaskManage、TopicCenter、StyleConfig
   （外加 Shell 与门面页）。内联样式待迁移 **17 → 9 个文件**、旧令牌待迁移 **19 → 12 个文件**
   （其中 `global.css` 的 `.backstage-*` 为刻意保留，需待全部页面迁移完成后再删）。
   两个守卫中的清单即精确工单；清空后即可删除 `variables.css` 与 `.backstage-*` 层。
   剩余内联样式集中在 ScheduleManage（14 处）与其余配置类小页面（ModelConfig / AccountConfig /
   ImageManage / UserManage / ReviewCenter / Login）；
   剩余旧令牌集中在 7 个 `components/**` 的 CSS module 与 Login / ArticleManage。
3. **迁移中顺带修复的三个真实缺陷**：
   - `StyleConfig` 的三栏主题工作台**全部使用硬编码灰**（`#f0f0f0` 边框、`#f8fafc`/`#fff`/`#fafafa` 背景），
     因此深色模式下会渲染出浅灰线条与亮底面。迁移后全部改用语义令牌，深色模式恢复正常。
   - `TaskManage` 的汇总数字用内联硬编码色（`#059669`/`#d97706`/`#e11d48`）表示状态，
     已改为 `StatGrid` + `Stat` 的 `tone`（positive/warning/negative），由状态令牌着色。
   同理，`TaskDetail.module.css` 曾引用**从未定义过的** `--app-text-primary`，
   导致该 `color` 声明被浏览器整条丢弃（一直靠继承"碰巧"正常），迁移后已真正生效。
4. **性能**：门面页与 antd 同一 bundle（`App.tsx` 静态引入控制台），访问 `/` 也会下载整个 antd 包；
   若要冲性能分应把控制台改为 `React.lazy` 代码分割。
5. **无视觉回归测试**：需引入 Playwright/Chromatic 等新依赖，本次明确不做，改为每批人工清单。

### 21.6 部署检查项

`api/main.py` 只挂载 `/artifacts`，前端由外部服务器托管（已确认 FastAPI 不提供 `index.html`）。
新增的公开路由 `/` 需要 **SPA fallback**（nginx `try_files ... /index.html`），否则直访会 404。

### 21.7 顺带修复的既有偶发失败（已解决）

`TopicCenter.test.tsx` 原本存在**偶发失败**：单独运行必过，全量并发运行偶发
`Unable to find an element with the text: 账号匹配`。

排查后确认是**测试自身的竞态**，不是产品缺陷：`TopicCenter` 用**第二个 effect** 展开首张卡片
（`useEffect(() => { if (!expandedId && topics.length) setExpandedId(topics[0].topic_id) })`），
而 `账号匹配` 只在展开态渲染——标题先提交，详情面板晚一帧提交。
测试在 `await findByText(标题)` 之后用**同步** `getByText('账号匹配')`，
正好卡在两次提交之间，并发负载下偶发失败。

修复：改为 `await screen.findByText('账号匹配')`，等待自动展开那一帧。
**连续 3 次全量运行均为 144 passed**，确认偶发性消除。

### 21.8 规范治理

`CLAUDE.md` 的 UI 风格规范已整体重写：主色调统一为 `#0F766E`（并说明为何不用瑞士红）、
明确 `tokens.css` 为唯一样式真源、圆角/阴影/字阶/间距/动效规则、
把"禁止内联 style"细化为"禁止内联样式对象，动态值走 CSS 自定义属性"，
并声明两个守卫测试与 antd 由令牌生成。

## 22. 2026-10-10 图片生成链路重做（已实现，人工看图验收待运营确认）

### 22.1 问题

运营反馈：生成的图片与文章内容不符合、图片都是文本、风格有问题。三条都成立。

### 22.2 根因

**这条链路从来没有"描述画面"的步骤。** 提示词是字符串拼接：内部 role 标识符 + 主题 +
抓取正文 + 英文样板。实测发出去的提示词以 `cover for <主题>` 开头，
后面跟着 `Use these article/data signals: <转载样板原文>`，
并以 `no watermark, no unreadable small text, no fake UI screenshots` 收尾
——**既没有描述画面，又点名了 text/watermark/UI 三个概念**。

详见 `docs/2026-10-10-image-prompt-pipeline-fix.md`。

### 22.3 实现

| 改动 | 位置 |
|---|---|
| 新增视觉描述阶段（结构化输出，一次覆盖全部配图） | `workflow/agents/visual_describer.py` |
| 短提示词组装（默认 ≤400 字符，主体与文字排除句永不裁掉） | `workflow/utils/visual_spec.py` |
| 风格预设（默认编辑部摄影感），取代英文散串 | `workflow/utils/image_styles.py` |
| 角色 `infographic` → `data_scene`（不再要求画图表） | `workflow/nodes/visual_plan.py` |
| 抓取样板清洗（转载署名/URL/截断残留） | `workflow/utils/claim_clean.py` |
| 审核改为"仅结构检查"，删除写死的 82 分 | `workflow/agents/visual_reviewer.py` |
| 图片列表接口 + 风格预设接口 | `api/routers/images.py` |
| 「图片管理」由 11 行占位改为真实审计页 | `frontend/src/pages/ImageManage.tsx` |

### 22.4 顺带修掉的 5 个缺陷

1. **占位图通过审核**：`generated://<role>` 的 `path` 为真值，旧检查判为"有资产"，生成失败被算作通过。
2. **写死 `score: 82`**：与实际质量无关的伪分数，让运营以为审过了。
3. **子串误判**：新校验函数最初用子串匹配，**"photograph" 含 "graph"**、
   "quiet"/"equipment" 含 "ui"、"texture" 含 "text"，几乎会拒掉所有合法 spec。改为词边界正则。
4. **列表接口分页截断**：按 `limit` 逐任务切片导致 `total` 错误并丢数据。
5. **相对路径不可访问**：`artifacts/...` 未映射到 `/artifacts/...` 挂载点。

### 22.5 测试

后端 **315 → 363 passed**（新增 4 个测试文件）。关键回归断言：
提示词不以 role 作主语、不含抓取样板、只含一处文字排除句、
**主体在极紧预算下仍保留**、请求图表的 spec 被拒并降级、占位图判为缺失且不再返回分数。

### 22.6 遗留与前置

- **前置阻塞**：结构化模型（`OPENAI_FAST_MODEL`）仍未配置，文章本身仍走模板，
  配图上限被锁死。须先在「模型配置」页配好非推理模型。
- **人工验收必须由运营完成**：当前会话所用模型不支持图像输入，无法自动判断图中是否还有文字。
- 历史任务仍显示改造前的旧提示词，可用于前后对比。
- 生成图不清理：`artifacts/generated_images/` 已 ~90 张 / ≈110 MB。

## 23. 2026-10-21 文章结构自适应：让 Agent 自己决定类型与结构（已实现）

### 23.1 问题

> 文章结构还是有问题，不能固定化，应该让 agent 自己决定文章的结构，
> 自己根据不同的类型文章生成对应的文章结构。

### 23.2 根因（主因不是模型不听话，而是一个 bug）

**模型的正确回答被 schema 丢掉了。** 日志原文：

```
plan_article_angle_fallback ... error=9 validation errors for BlueprintOutput
sections.0.key_evidence
  Input should be a valid string [input_value=['高铁约100分钟', ...], input_type=list]
evidence_map.0.supporting_sources
  Input should be a valid string [input_value=['source_1', 'source_3'], input_type=list]
```

`BlueprintOutput` 声明 `list[dict[str, str]]`，而模型把 `key_evidence` 写成**证据列表**、
`supporting_sources` 写成**来源 id 列表**——两种表示都完全合理，却导致
**整份自适应蓝图被丢弃**，回退到固定骨架。提示词里"freely choose their number, order,
and shape""Never output a fixed template"全都写了，问题出在回答没有被接收。

叠加：`thesis` 是唯一必填字段（一票否决）；兜底骨架是单一固定套路且标题=抓取文本截断
（出现 `#法国骚乱…被烧#】法国数十万人1为何在此时发生`、`从"腾笼换鸟仍待验证的部分`）；
三套类型系统（`article_strategy`/`article_type`/`selected_skill`）互相打架且都偏技术向；
结构化阶段因 `text_fast` 未配置而全部被截断。

详见 `docs/2026-10-21-adaptive-article-structure.md`。

### 23.3 实现

| 改动 | 说明 |
|---|---|
| schema 宽容化 | 字符串列表不再要求 `str`；`thesis` 可缺省并从 `central_question` 回填；空 payload 可解析 |
| 自适应骨架 | 新增 `_order_shapes` / `_detect_opener`，按故事因果依赖排序而非遍历固定 job 表 |
| 标题质量闸门 | `_heading_quality` 拒绝抓取残句；`_recover_heading` 从该节自身证据重建标题 |
| 保留模型字段 | `_normalize_sections` 不再把小节压成 `{heading, goal, shape}` |
| 类型由 Agent 自命名 | 无预设枚举；`clamp_type_label` 把整句标题收窄为标签，但保留模型措辞 |
| 运营可覆盖 | `requested_article_type`（空/auto = 自动判断），在成功与降级两条路径都生效 |
| tier 预算放大 | `budget_for_tier`：`strong` tier 预算 ×6，避免推理模型在产出 JSON 前耗尽额度 |

### 23.4 实测

对真实模型调用，同一路径此前输出固定两段式骨架，现在得到
`article_type=事件复盘` 与 5 个故事专属小节（含一节由该节 `purpose` 重建的标题）。

### 23.5 测试

后端 **365 → 393 passed**（新增 `tests/test_adaptive_article_structure.py` 28 项）。
关键断言：生产现场 payload 不再抛错、缺 `thesis` 可回填、
真实残句标题被拒而可读标题被保留、**两个不同故事得到不同类型/spine/标题**、
覆盖设置端到端生效。另更新 5 处断言旧固定 token 预算的测试为 `budget_for_tier`。

### 23.6 遗留

- `selected_skill` 仍只有 2 个技能且偏技术向（法国骚乱 → 通用科技解读）；
  它现在只是输入提示，类型与结构已由 Agent 决定。
- `article_strategy` 与 `article_type` 语义重叠，前端同时暴露两个字段；
  按"不预设枚举"的决定暂留，后续可合并入口。
- 历史任务的 `article_type` 不会回填。
- `strong` tier 下蓝图预算放大到 18000，对非推理模型是浪费；
  配好 `OPENAI_FAST_MODEL` 后自动回到 3000。刻意保守：预算不足会静默退化成模板文章。

## 24. 2026-10-21 全项目日志优化（已实现）

### 24.1 问题

> 优化整个项目的日志

### 24.2 诊断（实测数据）

审计 `logs/app.log`（5.1 MB / 13,678 行）+ `app.log.1`（12.9 MB / 50,761 行）：

| 编号 | 问题 | 实测 |
|---|---|---|
| A1 | **测试写入生产日志** | `setup_logging()` 在 `api/main.py:43` **模块导入时**执行，任何 `TestClient(app)` 测试都会装上生产 handler。跑一个测试模块 → 生产日志 **+743 字节 / 8 行**；全量 **6,501/13,701 行（47%）来自 34 个测试 task_id** |
| A2 | **无任何堆栈** | 全仓库 `exc_info` 使用 **0** 次；321 条 error 行**全部无 traceback** |
| A3 | 密钥掩码 | 2,525 处 `api_key_masked` 全部已掩码，**0 泄漏**（无需修，已加测试） |
| B1 | **模型 payload 占 57% 体积** | 3.0 MB/5.1 MB，单行最长 **30,309 字符**；`MODEL_LOG_MAX_CHARS` 是逐字段截断 |
| B2 | **httpx 刷屏** | **2,208 行 `HTTP Request:`（16%）**，全项目未设置其级别 |
| C1 | **无关联 ID** | `merge_contextvars` 已配置但**无人调用 `bind_contextvars`** |
| C2/C3 | 无级别开关 / 默认非 JSON | 与 `CLAUDE.md` 的 JSON 约定不一致 |
| D1 | stdlib 与 structlog 混用 | 实测 stdlib 行**无时间戳、无级别、无 logger 名** |
| E | **原子写失败** | 27 次 `[WinError 5] data\workflow_run_steps.tmp -> .json`：临时文件名**所有并发写者共用** + `replace` 无重试且失败被静默降级 |

### 24.3 实现

| 改动 | 说明 |
|---|---|
| 测试日志隔离 | `setup_logging()` 幂等可重入；新增 `LOG_DIR`；`tests/conftest.py` autouse fixture 重定向到 `tmp_path` |
| 异常带堆栈 | `workflow/` 35 处 except 日志补 `exc_info=True`（保持原级别，不做 WARNING→ERROR 转换） |
| payload 分离 | 主日志只留 `payload_chars`/`payload_sha256`/`payload_truncated`；完整内容写 `logs/model.log`（JSON Lines）；上限改为**整份 payload** |
| 第三方静音 | `httpx`/`httpcore`/`openai`/`langchain*` 等固定 ≥WARNING；health 检查 access 行过滤 |
| 关联 ID | `RequestContextMiddleware` 绑定 `request_id` 并回写 `X-Request-ID`；`run_workflow` 绑定 `task_id`+`run_id` |
| 级别与格式 | 新增 `LOG_LEVEL`；**文件 JSON / 控制台文本**；`cache_logger_on_first_use=False`（否则重配置静默失效） |
| 降噪 | `persistence_flushed`、`ws_connected`、`ws_disconnected` → DEBUG |
| 统一 structlog | `api/auth.py`、`api/store.py` 改 structlog；修正一处 `%s` 占位 |
| 查询接口 | `GET /api/logs`、`GET /api/logs/files`（只做后端）：白名单文件键、尾部读取、输出再脱敏 |
| 原子写 | **每路径一把锁** + 唯一临时名 + 退避重试 + `fsync` + 失败抛出 |

### 24.4 与计划的两处偏离（均为核实后修正）

1. **`force=True` 会破坏宿主 handler**：最初用 `logging.basicConfig(force=True, ...)`，
   它会移除**所有**已存在的 root handler，包括 pytest 自己的日志捕获。
   已改为显式 `root.addHandler(...)`，并加测试守护。
2. **`skill_start`/`skill_done` 不降级**：计划依据是"合计约 1,600 行（12%）"。
   落实时核实发射点，发现 `search_web`/`fetch_and_extract` 都是**每次节点调用一行**
   （带 `query_count`/`url_count`），并非每查询/每 URL 一行。
   其高计数反映的是**该窗口的任务执行次数**，而该窗口 47% 的行来自测试（A1）。
   即**降噪依据本身是测试污染的产物**。修掉 A1 后它们是每个任务 10–15 对的叙事主线，
   故**保留 INFO**（详见 `docs/2026-10-21-logging-overhaul.md` §3.8）。

### 24.5 实测验证

| 验证 | 结果 |
|---|---|
| 跑测试对生产日志增量 | **0 字节** |
| 主日志含 prompt 正文 | **否** |
| `logs/model.log` 含完整 payload | **是**，JSON Lines，密钥已掩码 |
| 主日志含 `HTTP Request:` | **否** |
| 每行可 `json.loads` 且含四要素 | **是** |
| 异常带 traceback | **是** |
| 6 线程并发写同一 JSON | **不失败、不损坏、无 `.tmp` 残留** |
| 模拟 WinError 5 | **第 2 次尝试恢复** |

**压测复现了生产原故障**：6 个并发写者确实复现 `[WinError 5] 拒绝访问`，
与生产日志中的 27 次一致 —— 确认根因判断正确，且**仅靠重试不足**
（会耗尽重试并丢写入），故引入每路径锁。

### 24.6 测试

新增 3 个测试文件（+40 项）：`test_logging_config.py`（20）、`test_logs_router.py`（13）、
`test_persistence_atomic_write.py`（7）。后端合计 **393 → 436 passed**。

### 24.7 遗留

- **运行中的服务需重启**新配置才生效；现存 `app.log`（约 7 MB）仍含历史污染，
  会随轮转消失；`app.log.1` 已归档到 `logs/archive/`（确认后可手动删除）。
- 4 个 `__init__.py` 文件带 UTF-8 BOM（`workflow/{agents,nodes,services,tools}/`）。
  这是**既有**状态（Python 本身可正常解析，仅严格 `utf-8` 读取会报 U+FEFF），
  与本次改动无关，未修改。
- JSON 行中 `event`/`level`/`logger`/`timestamp` 位于 kwargs 之后（解析无影响，
  但 `tail -f | jq` 时时间戳不在行首）。
- 磁盘上限：主日志 5×10 MB + payload 3×20 MB ≈ 110 MB；`GET /api/logs/files` 可查总量。

## 25. 2026-10-22 热点获取：提炼 TrendRadar 核心逻辑 + 内建定时拉取（已实现）

### 25.1 问题

> 能否使用 mcp 方式然后每日定时拉取数据，我可以把 github 上的项目重新跑起来

### 25.2 结论：MCP 与 GitHub Actions 互斥（实测证据）

| 证据（`sansan0/TrendRadar/.github/workflows/crawler.yml`） | 含义 |
|---|---|
| `permissions: contents: read` | 只有读权限，**永远无法把数据 commit 回仓库** |
| 整个 workflow 无 commit/push 步骤 | 抓取结果不进仓库 |
| `timeout-minutes: 15` | 每轮最多 15 分钟即销毁、不监听端口 |
| 无监听端口 | **云端不存在 MCP 端点**；`trendradar-mcp:3333` 只在 Docker 形态存在 |

补充核实：你 fork 里 7 个 `output/news/*.db`（2025-12-21~27）**是模板自带示例数据**
（git SHA 与上游完全相同），且 fork 的 `pushed_at`（2026-03-24）早于最后一次运行（2026-08-09）；
fork 的 `crawler.yml` 状态为 **`disabled_inactivity`**（GitHub 对 60 天无活动仓库的自动禁用）。

按你的决定走**「提炼核心逻辑并嵌入」**。

### 25.3 TrendRadar 的核心逻辑（源码实证）

它并不爬各站 HTML，而是调用一个公开接口（`trendradar/crawler/fetcher.py`）：

```
GET https://newsnow.busiyi.world/api/s?id=<platform_id>&latest
→ {"status":"success"|"cache","items":[{"title","url","mobileUrl","extra"},…]}
```

**实测其 16 个平台 id 全部可用（16/16，0 失败）。** 移植的 6 条行为：状态校验、
抖动重试、**非字符串标题跳过**、标题去重 + 收集全部 rank、**域名安全校验**、请求间隔抖动。

> 第 3 条在实现时被我自己的测试抓到漏移植：`_clean_text(1.5)` 会得到 `"1.5"`，
> 浮点标题于是变成"热点标题"。改为要求 `isinstance(title, str)` 后才与它一致。

**GPL-3.0 处理**：TrendRadar 是 GPL-3.0，本仓库当前**没有 LICENSE**。故**不复制源码**
（否则整个仓库被迫 GPL-3.0），只移植行为/方法，并在 docstring 中署名 newsnow 与 TrendRadar。

### 25.4 实现

| 改动 | 说明 |
|---|---|
| 新来源 `newsnow` | `HotspotSource` 加枚举；`NewsNowHotspotProvider`；裸标识识别为 newsnow；16 平台预设并入目录 |
| 定时拉取 + 快照 | `api/hotspot_snapshot.py`：并发拉取 → 打分 → **原子落盘** `data/hotspot_snapshot.json`（复用上一轮加固的 `write_json_file`）；拿锁串行化；写盘失败保留内存快照 |
| 接入调度器 | 挂到既有 `SchedulerEngine._tick()`（20 秒循环），自限速且**吞掉自身异常**，不影响定时任务 |
| 任务优先读快照 | 新鲜则**完全不打上游**；**部分覆盖只实时抓未覆盖平台**；过期则走原实时路径（行为不退化）；任务自己的过滤器仍生效 |
| 查询接口 | `GET /api/hotspots/snapshot`、`POST /api/hotspots/snapshot/refresh`（上游异常 502） |
| 前端修复 | `buildHotspotConfig` 原**丢弃 `source`/`provider_id` 且硬编码 `source:'tophub'`**，现按平台保留 |

### 25.5 实测验证

| 验证 | 结果 |
|---|---|
| 16 平台可用性 | **16/16**（仅 `mktnews` 偶发返回 0 条） |
| 全量刷新 | **215 原始 → 205 候选，2.8 秒** |
| 快照落盘 | 192 KB |
| 快照被任务复用 | **0 次上游调用**仍产出候选、选中热点、改写 keywords |
| 部分覆盖 | 只对未覆盖平台发起 **1 次**调用 |
| 域名校验 | 放行 `s.weibo.com`；拦截 `weibo.com@evil.com` 等 4 种伪装 |

### 25.6 测试

新增 3 个文件（**+63 项**）：`test_hotspot_newsnow.py`（28）、`test_hotspot_snapshot.py`（24）、
`test_hotspot_snapshot_integration.py`（11）。后端合计 **436 → 499 passed**。

### 25.7 遗留：打分并列（**最值得先做**）

实测本次快照：205 条候选、60 个不同分值，但**最高分 71.2 有 8 条并列**，其中 3 条是**同一个故事**
（`西藏那曲巴青县发生7.0级地震` / `西藏那曲市7.0级地震` / `西藏7级地震`）。

原因：newsnow **不提供热度值**，`hot_value` 恒为 `None`；`rank` 与 `platform_weight` 相同时
`rank_hotspots` 无从区分。而 `pick_best_hotspot` 取 `candidates[0]`（排序键
`(selection_score, -rank)`），同分时等价于**平台目录顺序** → 选中结果"确定但无意义"。

**这正是 TrendRadar 用 `advanced.weight`（rank 0.6 / frequency 0.3 / hotness 0.1）解决的问题。**
我们已有现成数据（一条标题出现在几个平台 = 跨平台频次）。计划中已承诺**本轮不动
`rank_hotspots` 权重**（先换源再调参，避免同时改两件事无法归因），故留作下一步。

其余：`mktnews` 偶发空返回（已正确计为 failed）；Phase 3（MCP 适配器）未实现，
若将来本机跑起 `trendradar-mcp` 可复用同一骨架；`data/hotspot_snapshot.json` 属运行期状态。

## 26. 2026-10-23 热点排序补强 + 长文本撑破页面修复 + 存储现状核查（已实现）

### 26.1 三个需求

> 加上去（补跨平台频次信号）；页面的适配有问题，文本长应该省略号，现在把所有文本都展示了把页面撑坏了；目前的数据库 pgsql 是否有使用

### 26.2 跨平台频次信号

`newsnow` 不提供热度值 → `hot_value` 恒为 `None`，导致真实快照里最高分 71.2 **有 8 条并列**
（其中 3 条是同一场地震），而 `pick_best_hotspot` 取 `candidates[0]`，同分时等价于**平台目录顺序**。

新增 `frequency_score`（每多一个平台 +6，封顶 12），并新增可审计字段
`cross_platform_count` / `source_platforms`。

**两个相似度阈值刻意不同**：`DUPLICATE_SIMILARITY=0.90` 决定**行是否存活**（误判不可恢复，未变）；
`CROSS_PLATFORM_SIMILARITY=0.65` 只决定**看起来被多少平台报道**（误判最多多给 12 分，绝不删行）。
真实跨平台标题很少逐字相同：三条地震标题两两相似度约 0.76。

**自己的测试抓到实现 bug**：第一版按星形比对得到 `[2,3,2]`，因为三条标题构成**链**
（B 是桥，A 与 C 互不相似）。已改为**并查集连通分量**（可传递），并加长度预筛。
另补规则：**标题短于 4 字必须完全相同**（"召回"/"汽车召回" 相似度 0.67 会误判）。

实测（同一份 205 条候选快照）：

| 指标 | 前 | 后 |
|---|---|---|
| 最高分并列 | **8** 条 | 3 条（**全是同一故事，故无害**） |
| 不同分值数 | 60 | **70** |
| 跨平台故事得分 | 71.2 | **83.2**（高 12 分） |
| 最大覆盖平台数 | — | **4** |
| 耗时 | — | 425 ms |

### 26.3 长文本撑破页面

**根因**：`ArticleManage` 把完整标题与最长 200 字摘要直接渲染进 `<h2>`/`<p>`。
栅格列本身正确（`minmax(0,1fr)` + `min-width:0`），但**文本元素自己没有截断**，
卡片高度随内容无限增长。同样写法另有 4 处，其中 **`ViralityScorecard` 风险最高**
（渲染 LLM 生成的成段文字）。

**修复方式**：新增设计系统原语 `components/layout/TruncatedText.tsx`（+ `.truncated`/`.clamp1..4`），
而非逐页打补丁。三个要点：`min-width: 0`（"设了 ellipsis 却不生效"的常见原因）、
`overflow-wrap: anywhere`（长 URL 不溢出）、完整值保留在原生 `title`（零额外 DOM）。

**回归守卫**：`textOverflow.test.ts` 规定 `pages/`+`components/` 内
**不得出现裸的 `<h1-h3>{动态值}` / `<p>{动态值}`**（静态字面量不受限）；
允许清单只放 `WorkbenchShell`（渲染写死的导航元数据），并**有测试验证该条目仍然成立**以防清单腐烂。

顺带把 `ArticleManage` 的两处内联样式改为模块类 + `EmptyState`，该文件**已移出 `noInlineStyle` 待迁移清单**
（守卫的"清单不得含失效条目"主动报错提醒了我）。

### 26.4 PostgreSQL 现状：**未使用**

| 检查 | 结果 |
|---|---|
| `.env` 的 `DATABASE_URL` | **未设置**；`database_health()` = `disabled` |
| SQLAlchemy / psycopg2 | **都已安装**（2.1.3 / 2.9.13） |
| `.db`/`.sqlite` 文件 | 无 |
| 数据实际位置 | 全部 `data/*.json` |

**代码支持、驱动已装、从未启用**。双后端是有意设计（设了 `DATABASE_URL` 即切），不是遗留代码。

**顺带查到 JSON 后端的真实写放大**：

```
data/workflow_run_steps.json  磁盘 32.9 MB / 101 条记录 / JSON 内容仅 16.5 MB（indent=2 使其翻倍）
单条平均 167 KB（最大 508 KB）——内含三份高度重叠的状态快照：
  input_state 157 KB / output 169 KB / state_after 182 KB
```

而写入是**整文件重写** → **每个节点步骤重写整个 32.9 MB 文件** →
一个 20 节点任务约 **660 MB** 磁盘写入。这也解释了上一轮反复出现的
`[WinError 5] workflow_run_steps.tmp -> .json`（写窗口太长，Windows 下抢占概率升高）。

建议分两个独立问题看：**换 Postgres 解决"整文件重写"**；但**不解决"三份快照"**
（进库后三列各存一份仍是 3 倍）。另 `indent=2` 对运行期状态无收益，改紧凑可减半。
本次未改存储层（换库属部署决策，需确认目标环境是否有 Postgres）。

### 26.5 测试

后端 **499 → 521 passed**（新增 `test_hotspot_frequency.py` 22 项）；
前端 **144 → 156 passed**（新增 `TruncatedText.test.tsx` 8 项、`textOverflow.test.ts` 4 项）。

## 27. 2026-10-25 图片与文章匹配 + 复用参考文章真实照片（已实现）

### 27.1 需求

> 这里的照片生成有问题，内容应该和文章内容匹配，而且如果参考的文章有对应的照片，可以拿来添加到生成的文章中

两个需求是同一根因链的两端，第二个顺带绕开了第一个的阻塞点。

### 27.2 需求①根因：模型未配置 + 降级为全局常量

实测 `data/tasks.json`，两篇毫不相关的文章（Anthropic IPO / 微信红果）
**逐字节得到同一个 `subject`**：
`"A quiet workstation at night: an open laptop, a paper notebook and a cooling mug"`。

失败链（`visual_describer.py`）：`text_fast = None` → 结构化阶段回落到推理模型
（`logs/model.log` 证实调用确实发生）→ 调用成功但 **`batch.items` 为空** →
第 116 行 `no_spec_returned` → `build_fallback_spec(role)`，**该函数只接收 role，与文章无关**。

**所以不是"图片生成坏了"，而是"描述阶段没产出内容，降级到一张全局写死的图"。**

修复：`build_fallback_spec(role, topic=, section=, claim=)` + 主题→物理场景映射表。
实测不同主题得到不同场景（Anthropic → 财经桌面；地震 → 救援装备；国乒 → 体育场）。
**诚实定位**：这是缓解不是解决，它读不懂论点，只能判断大致领域。

### 27.3 需求②现状：数据早就抓到了，只是被丢弃

| | 位置 |
|---|---|
| 生产者 | `fetch_extract.py:101` → `extracted_contents[].images`（每页最多 5 张） |
| 消费者 | **没有**（全仓 grep 只有生产者和测试） |

投递链路**原本就支持外链图**：`illustrations` → `upload_article_image` → `_download_image`；
`[插图N]` 占位符由 `image_generation.py` **确定性插入**（不是写作 LLM 决定）。
故这属于**补齐**而非新建。

### 27.4 实现

- 新增 `workflow/utils/source_images.py`：HTTPS/扩展名/文件名/去重前置过滤；下载**带 Referer**
  （很多 CDN 无 Referer 直接 403）；**Pillow 真实像素校验**（不再信任 `<img width= height=>`
  标签属性——它们通常缺失，正是过去漏掉 logo/小图的直接原因）：真实尺寸 ≥600×300、
  宽高比 0.5–2.8、纯色判空白、动态图拒绝、**webp→jpeg 转码**（微信不接受 webp，
  而旧提取器接受 `.webp`，会在上传阶段才失败）、过大图下采样
- 接入 `generate_visual_assets_node`：照片排在生成资产之前，复用既有章节排序与占位符插入
- 封面裁到微信 2.35:1，**记录丢弃比例**，超阈值提示人工确认
- **只要有照片被使用就强制人工审核**（追加到既有 blocking 通道，不改变运维方策略）；
  **无标题且无域名 → 直接丢弃**（无法留痕就不满足所选策略）
- 可见署名 `SOURCE_IMAGE_CREDIT` **默认关闭**（对应"写入元数据与风险提示"）
- 前端 `TaskDetail` 画廊显示出处（可点击原文）与裁切警告

### 27.5 自己的测试抓到的 4 个真 bug

| # | 问题 | 证据 |
|---|---|---|
| 1 | **数量上限被并发击穿** | 上限 2，实测返回 **6**（4 个 worker 都在 append 前读到 0）→ 改为并发后强制截断 |
| 2 | **宽高比放行横幅** | 2400×700（3.43）通过 3.5 上限 → 收到 **2.8** |
| 3 | **资产引用远端 URL** | `_asset_ref` 优先 `url`=远端 → 上传时二次下载且**不带 Referer**，很可能 403（**上线才暴露**）→ 改为指向本地文件，远端地址移入 `attribution.image_url` |
| 4 | 动态图原因错报 | 探针构造问题；校验顺序本身正确 |

### 27.6 顺带修掉上一轮的功能缺陷

热点快照**刷新失败也会盖上新的 `captured_at`** → `due_for_refresh()` 整个周期都是 False，
一次上游抖动换来 60 分钟静默（2026-10-24 19:07 实测 16 个平台全挂）。
现在 `attempted_at` 始终记录，无候选时按 `HOTSPOT_RETRY_INTERVAL_MINUTES`（默认 5 分钟）重试；
`is_fresh()` 要求快照非空。

### 27.7 实测

真实页面 → 真实抽取 → 真实下载：**9 候选 → 4 张通过**，
`rejected={'duplicate_url':7,'too_small':5}`（logo/小图被正确拦下）；
封面 1262×726 → 1262×537 **ratio=2.350**，丢弃 26.0% → 正确提示人工确认。

### 27.8 测试

后端 **521 → 598 passed**（新增 `test_source_images.py` 38、`test_visual_fallback_matching.py` 19、
`test_source_image_pipeline.py` 12、`test_source_image_review.py` 8）；
前端 **156 → 163 passed**（新增 `TaskDetail.provenance.test.ts` 7）。

**新增依赖**：`Pillow>=11.0.0`。

### 27.9 需要用户确认

**需求①真正"匹配"的前提是把 `text_fast` 配成非推理模型** —— 无密钥无法验证。
即使不配，本轮改动仍有效：来源照片填满大部分图位，且降级路径不再是全局同一张图。




