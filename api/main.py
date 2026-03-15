"""FastAPI 应用入口。"""
from __future__ import annotations

import os
from dotenv import load_dotenv

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.logging_config import setup_logging
from api.routers import tasks, ws, config

# 加载 .env 环境变量
load_dotenv()

# 初始化 structlog 日志（JSON 输出到 logs/ + 控制台）
setup_logging()

app = FastAPI(
    title="微信公众号文章自动发布系统",
    description="基于 LangGraph 的微信公众号文章自动生成与发布 API",
    version="0.1.0",
)

# 开发期允许所有来源跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks.router, prefix="/api")
app.include_router(config.router, prefix="/api")
app.include_router(ws.router)
