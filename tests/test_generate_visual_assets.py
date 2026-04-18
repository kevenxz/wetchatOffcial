from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from workflow.skills.generate_visual_assets import generate_visual_assets_node


@pytest.mark.asyncio
async def test_generate_visual_assets_uses_image_model_for_visual_briefs() -> None:
    state = {
        "task_id": "task-1",
        "visual_state": {
            "image_briefs": [
                {
                    "role": "cover",
                    "compressed_prompt": "cover for robotics funding",
                    "provider_size": "1536x1024",
                    "target_aspect_ratio": "2.35:1",
                },
                {
                    "role": "infographic",
                    "compressed_prompt": "infographic for robotics funding",
                    "provider_size": "1024x1024",
                    "target_aspect_ratio": "4:5",
                },
            ]
        },
    }

    with patch("workflow.skills.generate_visual_assets.get_model_config") as mock_get_model_config:
        with patch("workflow.skills.generate_visual_assets._generate_image_asset") as mock_generate_image_asset:
            model_config = MagicMock()
            model_config.image.enabled = True
            model_config.image.api_key = "image-key"
            model_config.image.base_url = "https://image.example.com/v1"
            model_config.image.model = "gpt-image-1"
            mock_get_model_config.return_value = model_config

            mock_generate_image_asset.side_effect = [
                {"url": "https://img.example.com/cover.png", "path": "", "mime_type": "image/png"},
                {"url": "https://img.example.com/infographic.png", "path": "", "mime_type": "image/png"},
            ]

            result = await generate_visual_assets_node(state)

    assets = result["visual_state"]["assets"]

    assert assets[0]["role"] == "cover"
    assert assets[0]["url"] == "https://img.example.com/cover.png"
    assert assets[1]["role"] == "infographic"
    assert assets[1]["url"] == "https://img.example.com/infographic.png"
    assert mock_generate_image_asset.await_count == 2


@pytest.mark.asyncio
async def test_generate_visual_assets_falls_back_to_placeholder_assets_when_image_model_disabled() -> None:
    state = {
        "task_id": "task-2",
        "visual_state": {
            "image_briefs": [
                {
                    "role": "cover",
                    "compressed_prompt": "cover for robotics funding",
                    "provider_size": "1536x1024",
                    "target_aspect_ratio": "2.35:1",
                }
            ]
        },
    }

    with patch("workflow.skills.generate_visual_assets.get_model_config") as mock_get_model_config:
        model_config = MagicMock()
        model_config.image.enabled = False
        model_config.image.api_key = ""
        model_config.image.base_url = None
        model_config.image.model = "gpt-image-1"
        mock_get_model_config.return_value = model_config

        result = await generate_visual_assets_node(state)

    asset = result["visual_state"]["assets"][0]
    assert asset["role"] == "cover"
    assert asset["path"] == "generated://cover"
