"""Tests for concurrent image generation."""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from api.models import ImageModelConfig, ModelConfig, TextModelConfig
from workflow.tools.image_generation import generate_visual_assets_node


def _config(enabled: bool = True) -> ModelConfig:
    return ModelConfig(
        text=TextModelConfig(api_key=""),
        image=ImageModelConfig(enabled=enabled, api_key="image-key", model="image-model"),
    )


def _state(brief_count: int) -> dict:
    return {
        "task_id": "task-image",
        "visual_state": {
            "image_briefs": [
                {"role": f"role{i}", "compressed_prompt": f"prompt{i}"} for i in range(brief_count)
            ]
        },
        "generated_article": {"content": "## 一\n\n正文\n\n## 二\n\n正文"},
    }


@pytest.mark.asyncio
async def test_images_generate_concurrently_and_keep_brief_order() -> None:
    active = 0
    max_active = 0

    async def fake_generate(task_id: str, brief: dict, *, model: str, api_key: str, base_url):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        # Earlier briefs take longer, so serial execution would reorder nothing but
        # concurrent execution must still preserve the original index order.
        await asyncio.sleep(0.05 if brief["role"] == "role0" else 0.01)
        active -= 1
        return {"url": f"https://cdn.example.com/{brief['role']}.png", "path": "", "mime_type": "image/png"}

    with patch("workflow.tools.image_generation.get_model_config", return_value=_config()):
        with patch("workflow.tools.image_generation._generate_image_asset", side_effect=fake_generate):
            result = await generate_visual_assets_node(_state(brief_count=3))

    assert max_active > 1, "images were generated serially"
    roles = [asset["role"] for asset in result["visual_state"]["assets"]]
    assert roles == ["role0", "role1", "role2"]


@pytest.mark.asyncio
async def test_failed_image_degrades_to_placeholder() -> None:
    async def fake_generate(task_id: str, brief: dict, *, model: str, api_key: str, base_url):
        if brief["role"] == "role1":
            raise RuntimeError("provider rejected the prompt")
        return {"url": f"https://cdn.example.com/{brief['role']}.png", "path": "", "mime_type": "image/png"}

    with patch("workflow.tools.image_generation.get_model_config", return_value=_config()):
        with patch("workflow.tools.image_generation._generate_image_asset", side_effect=fake_generate):
            result = await generate_visual_assets_node(_state(brief_count=3))

    assets = result["visual_state"]["assets"]
    assert len(assets) == 3
    assert assets[1]["path"] == "generated://role1"
    assert assets[1]["url"] == ""


@pytest.mark.asyncio
async def test_disabled_image_model_uses_placeholders_without_calling_provider() -> None:
    with patch("workflow.tools.image_generation.get_model_config", return_value=_config(enabled=False)):
        with patch("workflow.tools.image_generation._generate_image_asset") as mock_generate:
            result = await generate_visual_assets_node(_state(brief_count=2))

    mock_generate.assert_not_called()
    assert [asset["path"] for asset in result["visual_state"]["assets"]] == [
        "generated://role0",
        "generated://role1",
    ]
