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

- 主色调：`#1677FF`（Ant Design 默认蓝）
- 整体风格：简洁商务，参考 Ant Design Pro
- 布局：左侧导航（Sider）+ 右侧内容区（Content）
- 间距：统一使用 Ant Design Space/gap 系统（8px 基础单位）
- 禁止内联 style，样式统一用 CSS Modules 或 Ant Design token

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

- 使用 `structlog` 输出 JSON 格式结构化日志
- 日志存储于 `logs/` 目录
- 每个 Skill 节点执行开始/结束、异常必须记录日志
- 日志字段至少包含：`task_id`、`skill`、`status`、`duration_ms`

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
