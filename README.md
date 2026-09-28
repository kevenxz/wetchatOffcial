# 微信公众号智能编辑部

面向微信公众号的 Agentic 内容生产系统。系统以“提升合格点击、阅读完成、收藏与有效转发的概率”为目标，在事实边界内完成热点捕获、研究取证、传播策略、写作、双重评审、配图和草稿发布。

> 传播潜力评分是创作质量的领先指标，不是流量承诺。可信度始终是硬约束。

## 核心工作流

```text
热点捕获 → 任务简报 → 总体规划 → 选题评估
  → 研究规划 → 多轮检索 → 证据包 → 类型路由
  → 传播策略 → 文章大纲 → 写作成稿
  → 编辑审核 → 传播评审
  → 图片规划 → 图片生成 → 图片审核
  → 质量门禁 → 定向返工 / 人工复核 / 草稿发布
```

传播评审包含标题点击力、首屏留存、观点新颖度、读者共鸣、分享动机、证据可信度和阅读流畅度七个维度。默认质量线为 78 分，可通过 `review_policy.viral_threshold` 调整。

完整设计见 [爆文目标驱动的 Agent 架构](docs/2026-07-18-viral-agent-architecture.md)。

## 技术栈

- 后端：FastAPI、LangGraph、Pydantic、structlog
- 模型：OpenAI 兼容文本模型与图片模型
- 研究：多搜索源、网页抓取、证据包与引用追踪
- 前端：React 18、TypeScript、Vite、Ant Design、Zustand
- 发布：微信公众号草稿 API
- 测试：pytest、pytest-asyncio、Vitest、Testing Library、ESLint

## 项目结构

```text
api/                  FastAPI 路由、鉴权、调度、存储与 WebSocket
workflow/
  agents/             规划、写作、评审、传播策略、图片等领域 Agent
  nodes/              LangGraph 应用节点与质量路由
  tools/              搜索、抓取、图片、微信草稿等基础设施适配器
  utils/              证据、评分、文章类型与可观测性工具
frontend/src/         编辑部工作台
tests/                后端与工作流测试
data/                 本地运行状态（不要手工编辑或提交）
docs/                 架构、实现与迁移文档
```

## 本地启动

建议使用 Python 3.11+。

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
python main.py
```

后端默认地址为 `http://localhost:8001`，API 文档位于 `http://localhost:8001/docs`。

前端：

```powershell
Set-Location frontend
npm install
npm run dev
```

## 验证

```powershell
.\.venv\Scripts\python.exe -m pytest -q
Set-Location frontend
npm test
npm run lint
npm run build
```

## 配置与安全

- 复制 `.env.example` 后配置模型、搜索和微信公众号凭据。
- 不要提交 `.env`、API Key、生产账号数据、`data/` 运行状态或 `logs/`。
- 模型不可用时，关键 Agent 提供确定性降级结果；高风险、证据不足或超过返工预算的文章进入人工复核。
- 自动发布可通过 `publish_policy.auto_publish_to_draft` 关闭。
