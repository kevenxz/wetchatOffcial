# 基于 LangGraph 的微信公众号文章自动发布系统需求文档

版本：v1.3
更新日期：2026-03-22

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
| `workflow/graph.py` | 工作流编排：initialize → interpret_user_intent → infer_style_profile → build_article_blueprint → plan_search_queries → search_web → rank_sources → fetch_extract → generate_article → generate_images → push_to_draft/ui_feedback |
| `workflow/article_generation.py` | 统一 `generation_config` 默认值、策略枚举、风格原型与兼容 `article_plan` 辅助函数 |
| `workflow/skills/interpret_user_intent.py` | 解析主题、主角色、文章目标与实际策略 |
| `workflow/skills/infer_style_profile.py` | 自动生成风格画像，支持 `style_hint` 融合 |
| `workflow/skills/build_article_blueprint.py` | 生成结构化文章蓝图，并派生 `article_plan` |
| `workflow/skills/plan_search_queries.py` | 根据蓝图生成结构化搜索词与搜索意图 |
| `workflow/skills/search_web.py` | 多搜索源检索（SerpApi/Bing/DuckDuckGo），输出结构化来源结果 |
| `workflow/skills/rank_sources.py` | 对来源做可信度、相关度和多样性排序 |
| `workflow/skills/fetch_extract.py` | 并发抓取高分来源、正文提取（trafilatura + bs4）、图片筛选 |
| `workflow/skills/plan_article_strategy.py` | 旧版策略节点，保留兼容测试与历史逻辑 |
| `workflow/skills/generate_article.py` | 按 `user_intent + style_profile + article_blueprint + extracted_contents` 生成正文，并校验章节/插图标记 |
| `workflow/skills/generate_images.py` | 根据正文 `[插图N]` 标记分配封面图与插图 |
| `workflow/skills/push_to_draft.py` + `workflow/utils/wechat_*.py` | 微信 token 获取、素材上传、Markdown 转 HTML、草稿箱推送 |
| `api/routers/config.py` + `api/store.py` | 主题、样式与模型配置：内置主题、自定义主题增删改查、导入导出、全局样式保存、文本模型/图像模型配置 |
| `api/routers/accounts.py` | 多账号配置管理（当前可测试微信连接） |
| `api/routers/articles.py` | 文章列表、文章主题绑定、单篇/批量推送、推送记录 |
| `api/routers/schedules.py` + `api/scheduler.py` | 定时任务 CRUD、启停、立即执行、热点关键词随机触发，并复用文章生成配置 |
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
