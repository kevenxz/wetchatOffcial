"""FastAPI 应用入口。"""
from __future__ import annotations

import os
from pathlib import Path

import structlog
from dotenv import load_dotenv

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.auth import ensure_default_admin_user
from api.db import database_health
from api.logging_config import install_uvicorn_loggers, setup_logging
from api.models import HealthResponse
from api.request_context import RequestContextMiddleware
from api.routers import (
    accounts,
    articles,
    auth,
    config,
    hotspots,
    images,
    logs,
    reviews,
    schedules,
    search,
    stats,
    tasks,
    topics,
    users,
    workflow_runs,
    ws,
)
from api.scheduler import scheduler_engine
from api.store import bootstrap_storage
from workflow.utils.redis_client import get_redis

# 加载 .env 环境变量
load_dotenv()

# 初始化 structlog 日志（轮转文件 + 控制台）
# 注意：这里在模块导入时执行，因此测试必须通过 LOG_DIR 重定向文件日志
# （见 tests/conftest.py 的 isolate_logging fixture），否则测试输出会写进生产日志。
setup_logging()
install_uvicorn_loggers()

logger = structlog.get_logger(__name__)

APP_VERSION = "0.2.0"

app = FastAPI(
    title="微信公众号文章自动发布系统",
    description="基于 LangGraph 的微信公众号文章自动生成与发布 API",
    version=APP_VERSION,
)

# 开发期允许所有来源跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 为每个请求绑定 request_id（日志自动携带，并回写 X-Request-ID 响应头）。
# 加在 CORS 之后，使其成为最外层中间件，异常也能带上 request_id。
app.add_middleware(RequestContextMiddleware)

app.include_router(tasks.router, prefix="/api")
app.include_router(config.router, prefix="/api")
app.include_router(accounts.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(articles.router, prefix="/api")
app.include_router(schedules.router, prefix="/api")
app.include_router(hotspots.router, prefix="/api")
app.include_router(topics.router, prefix="/api")
app.include_router(reviews.router, prefix="/api")
app.include_router(workflow_runs.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
app.include_router(images.router, prefix="/api")
app.include_router(logs.router, prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(ws.router)

ARTIFACTS_DIR = Path("artifacts").resolve()
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/artifacts", StaticFiles(directory=str(ARTIFACTS_DIR)), name="artifacts")


@app.get("/api/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    """Report the health of storage, cache and the scheduler."""
    try:
        client = await get_redis()
        redis_status = "ok" if client is not None else "disabled"
    except Exception as exc:  # noqa: BLE001
        redis_status = f"error:{type(exc).__name__}"

    db_status = database_health()
    overall = "degraded" if db_status.startswith("error") else "ok"
    return HealthResponse(
        status=overall,
        database=db_status,
        redis=redis_status,
        scheduler=scheduler_engine.status(),
        version=APP_VERSION,
    )


@app.on_event("startup")
async def on_startup() -> None:
    summary = bootstrap_storage()
    logger.info(
        "storage_ready",
        backend=summary.get("backend"),
        created_tables=summary.get("created_tables"),
        imported=summary.get("imported"),
    )
    ensure_default_admin_user()
    await scheduler_engine.reconcile_on_startup()
    scheduler_engine.start()


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await scheduler_engine.stop()
