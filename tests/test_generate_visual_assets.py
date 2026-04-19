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


@pytest.mark.asyncio
async def test_generate_visual_assets_passes_visual_revision_brief_to_regeneration() -> None:
    state = {
        "task_id": "task-3",
        "visual_state": {
            "image_briefs": [
                {
                    "role": "cover",
                    "compressed_prompt": "cover for robotics funding",
                    "provider_size": "1536x1024",
                    "target_aspect_ratio": "2.35:1",
                }
            ],
            "revision_brief": {
                "mode": "targeted_revision",
                "guidance": ["主体不明确", "增加中心对象"],
                "findings": [{"role": "cover", "message": "主体不明确"}],
            },
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

            seen_brief: dict = {}

            async def fake_generate_image_asset(task_id: str, brief: dict, **_: str) -> dict[str, str]:
                seen_brief.update(brief)
                return {"url": "https://img.example.com/cover-v2.png", "path": "", "mime_type": "image/png"}

            mock_generate_image_asset.side_effect = fake_generate_image_asset

            result = await generate_visual_assets_node(state)

    assert "主体不明确" in seen_brief["compressed_prompt"]
    assert result["visual_state"]["assets"][0]["url"] == "https://img.example.com/cover-v2.png"
    assert result["visual_state"]["revision_brief"] == {}


@pytest.mark.asyncio
async def test_generate_visual_assets_maps_assets_back_to_generated_article() -> None:
    state = {
        "task_id": "task-4",
        "generated_article": {
            "title": "机器人商业化进入验证期",
            "content": "正文",
        },
        "visual_state": {
            "image_briefs": [
                {
                    "role": "cover",
                    "compressed_prompt": "cover for robotics",
                    "provider_size": "1536x1024",
                    "target_aspect_ratio": "2.35:1",
                },
                {
                    "role": "infographic",
                    "compressed_prompt": "infographic for robotics",
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
                {"url": "https://img.example.com/info.png", "path": "", "mime_type": "image/png"},
            ]

            result = await generate_visual_assets_node(state)

    article = result["generated_article"]
    assert article["cover_image"] == "https://img.example.com/cover.png"
    assert article["illustrations"] == ["https://img.example.com/info.png"]
    assert len(article["visual_assets"]) == 2


@pytest.mark.asyncio
async def test_generate_visual_assets_inserts_illustration_placeholders_into_content() -> None:
    state = {
        "task_id": "task-5",
        "generated_article": {
            "title": "机器人商业化进入验证期",
            "content": "开头段\n\n## 第一部分\n内容A\n\n## 第二部分\n内容B",
        },
        "visual_state": {
            "image_briefs": [
                {
                    "role": "cover",
                    "compressed_prompt": "cover for robotics",
                    "provider_size": "1536x1024",
                    "target_aspect_ratio": "2.35:1",
                },
                {
                    "role": "infographic",
                    "compressed_prompt": "infographic for robotics",
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
                {"url": "https://img.example.com/info.png", "path": "", "mime_type": "image/png"},
            ]

            result = await generate_visual_assets_node(state)

    content = result["generated_article"]["content"]
    assert "[插图1]" in content
    assert content.index("[插图1]") > content.index("## 第一部分")


@pytest.mark.asyncio
async def test_generate_visual_assets_places_infographic_near_evidence_section_and_scene_image_near_case_section() -> None:
    state = {
        "task_id": "task-6",
        "generated_article": {
            "title": "机器人商业化进入验证期",
            "content": "开头段\n\n## 哪些数据最值得看\n内容A\n\n## 典型公司在怎么做\n内容B\n\n## 风险边界在哪里\n内容C",
        },
        "visual_state": {
            "image_briefs": [
                {
                    "role": "cover",
                    "compressed_prompt": "cover for robotics",
                    "provider_size": "1536x1024",
                    "target_aspect_ratio": "2.35:1",
                },
                {
                    "role": "contextual_illustration",
                    "compressed_prompt": "scene for robotics company",
                    "provider_size": "1024x1024",
                    "target_aspect_ratio": "16:9",
                },
                {
                    "role": "infographic",
                    "compressed_prompt": "infographic for robotics",
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
                {"url": "https://img.example.com/scene.png", "path": "", "mime_type": "image/png"},
                {"url": "https://img.example.com/info.png", "path": "", "mime_type": "image/png"},
            ]

            result = await generate_visual_assets_node(state)

    article = result["generated_article"]
    content = article["content"]
    assert article["illustrations"] == [
        "https://img.example.com/info.png",
        "https://img.example.com/scene.png",
    ]
    assert content.index("[插图1]") > content.index("## 哪些数据最值得看")
    assert content.index("[插图1]") < content.index("## 典型公司在怎么做")
    assert content.index("[插图2]") > content.index("## 典型公司在怎么做")
