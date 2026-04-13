"""Configuration management routes."""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from api.models import ModelConfig
from api.store import (
    create_custom_theme,
    delete_custom_theme,
    get_custom_themes,
    get_model_config,
    get_preset_themes,
    get_style_config,
    import_custom_themes,
    save_model_config,
    save_style_config,
    update_custom_theme,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/config", tags=["config"])


class ThemePayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    config: dict[str, str]


@router.get("/style", response_model=dict[str, str])
async def get_styles() -> dict[str, str]:
    return get_style_config()


@router.put("/style", response_model=dict[str, str])
async def update_styles(body: dict[str, str] = Body(...)) -> dict[str, str]:
    updated = save_style_config(body)
    logger.info("style_config_updated", keys_updated=len(updated))
    return updated


@router.get("/model", response_model=ModelConfig)
async def get_models() -> ModelConfig:
    return get_model_config()


@router.put("/model", response_model=ModelConfig)
async def update_models(body: ModelConfig) -> ModelConfig:
    updated = save_model_config(body)
    logger.info(
        "model_config_updated",
        text_model=updated.text.model,
        image_enabled=updated.image.enabled,
        image_model=updated.image.model,
    )
    return updated


@router.get("/themes")
async def list_themes() -> dict[str, dict[str, str]]:
    return get_preset_themes()


@router.get("/themes/custom")
async def list_custom_themes() -> dict[str, dict[str, str]]:
    return get_custom_themes()


@router.post("/themes/custom")
async def create_theme(payload: ThemePayload) -> dict[str, dict[str, str]]:
    try:
        return create_custom_theme(payload.name, payload.config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/themes/custom/{theme_name}")
async def update_theme(theme_name: str, payload: ThemePayload) -> dict[str, dict[str, str]]:
    try:
        return update_custom_theme(theme_name, payload.name, payload.config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/themes/custom/{theme_name}")
async def remove_theme(theme_name: str) -> dict[str, dict[str, str]]:
    try:
        return delete_custom_theme(theme_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/themes/custom/import")
async def import_themes(payload: dict[str, dict[str, str]] = Body(...)) -> dict[str, dict[str, str]]:
    try:
        return import_custom_themes(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
