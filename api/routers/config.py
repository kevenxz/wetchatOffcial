"""配置管理路由。"""
from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Body

from api.store import get_style_config, save_style_config, get_preset_themes

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/style", response_model=dict[str, str])
async def get_styles() -> dict[str, str]:
    """获取公众号排版样式配置。"""
    return get_style_config()


@router.put("/style", response_model=dict[str, str])
async def update_styles(body: dict[str, str] = Body(...)) -> dict[str, str]:
    """更新公众号排版样式配置。"""
    updated = save_style_config(body)
    logger.info("style_config_updated", keys_updated=len(updated))
    return updated


@router.get("/themes")
async def list_themes() -> dict[str, dict[str, str]]:
    """获取所有预设主题列表。"""
    return get_preset_themes()
