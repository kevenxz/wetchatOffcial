# 微信公众号文章自动生成与发布系统

## 项目功能
- 基于 FastAPI 与 LangGraph 的后端，输入关键词即可自动完成“搜索网页 → 抽取内容 → 大模型生成稿件 → 配图 → 推送公众号草稿”整条流水线。
- 任务管理 API：`POST /api/tasks` 创建任务，`GET /api/tasks`/`/api/tasks/{id}` 查询，`DELETE /api/tasks/{id}` 删除，`POST /api/tasks/{id}/retry` 从失败节点继续；任务状态持久化在 `data/tasks.json`。
- WebSocket 实时进度：`/ws/tasks/{task_id}` 推送节点进展（状态、进度百分比、结果摘要）。
- 样式配置 API：`GET/PUT /api/config/style` 读取或更新文章样式，持久化到 `data/style_config.json`，方便前端按需渲染。
- 前端位于 `frontend/`（React + Vite + Ant Design），用于可视化创建任务、查看生成文章与草稿信息。

## 配置
- 复制 `.env.example` 为 `.env` 并填写：
  - `WECHAT_APP_ID`、`WECHAT_APP_SECRET`：公众号凭证，用于草稿上传。
  - `SERPAPI_API_KEY` 或 `BING_SEARCH_API_KEY`：网页搜索所需的 API Key（二选一或同时提供）。
  - `OPENAI_API_KEY`、`OPENAI_API_BASE`、`OPENAI_MODEL`：大模型访问配置，默认使用 OpenAI 兼容接口。
  - `DALLE_ENABLED`：设置为 `true` 时启用图片生成节点，为 `false` 则仅使用网页抽取的配图。
  - `API_HOST`、`API_PORT`：后端监听地址与端口。
- Python 依赖列表见 `requirements.txt`，运行时将在 `data/` 目录下生成 `tasks.json` 与 `style_config.json` 作为持久化存储。

## 启动流程
1. 准备 Python 3.9+ 环境（建议）并创建虚拟环境：`python -m venv .venv && .\\.venv\\Scripts\\activate`（Windows PowerShell）。
2. 安装后端依赖：`pip install -r requirements.txt`。
3. 初始化配置：`copy .env.example .env`，按上文填入各类密钥与模型配置。
4. 启动后端服务：
   - 开发模式：`python main.py`（等价于 `uvicorn api.main:app --host 0.0.0.0 --port 8001 --reload`）。
   - Swagger 文档：`http://localhost:8001/docs`；创建任务示例请求体 `{"keywords": "输入要生成的主题"}`。
   - 订阅进度：连接 WebSocket `ws://localhost:8001/ws/tasks/{task_id}` 获取实时状态与结果。
5. 启动前端（可选，用于可视化操作）：
   - `cd frontend && npm install`
   - 开发预览：`npm run dev`（若需修改后端地址，可在前端代码中调整 API 基础路径）。
   - 生产构建/预览：`npm run build && npm run preview`。

完成以上步骤后，即可通过前端界面或直接调用 API 触发文章生成并推送到公众号草稿箱。持续运行时注意妥善保管 `.env` 中的密钥，并定期备份 `data/` 目录以保留历史任务和样式配置。
## Agent Workflow

The workflow now runs through `intake_task_brief`, `planner_agent`, `analyze_hotspot_opportunities`, `plan_research`, `run_research`, `build_evidence_pack`, `resolve_article_type`, `plan_article_angle`, `compose_draft`, `review_article_draft`, `plan_visual_assets`, `generate_visual_assets`, `review_visual_assets`, and `quality_gate` before draft publishing.

Status: Implemented in branch `feature/agent-redesign-spec`
Verified by: `pytest -v`
