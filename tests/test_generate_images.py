from __future__ import annotations

"""Tests for generate_images skill."""
from unittest.mock import AsyncMock, patch

import pytest

from api.models import ImageModelConfig, ModelConfig, TextModelConfig
from workflow.skills.generate_images import generate_images_node
from workflow.state import WorkflowState


def _model_config(enabled: bool = False, api_key: str = "", model: str = "image-model", base_url: str | None = "https://image.example.com/v1") -> ModelConfig:
    return ModelConfig(
        text=TextModelConfig(api_key="text-key", model="text-model", base_url="https://text.example.com/v1"),
        image=ImageModelConfig(enabled=enabled, api_key=api_key, model=model, base_url=base_url),
    )


@pytest.fixture
def mock_state() -> WorkflowState:
    return WorkflowState(
        task_id="test_task_123",
        keywords="ai news",
        generation_config={"audience_roles": ["泛科技读者"], "article_strategy": "auto"},
        search_results=[],
        extracted_contents=[
            {"url": "1", "title": "A", "text": "...", "images": ["http://test.com/img1.jpg", "http://test.com/img2.jpg"]},
            {"url": "2", "title": "B", "text": "...", "images": ["http://test.com/img3.jpg"]},
        ],
        article_plan={},
        generated_article={
            "title": "Title",
            "content": "This is a paragraph. [插图1]\n\nThis is another. [插图2]\n\nLast one. [插图3]",
        },
        draft_info=None,
        retry_count=0,
        error=None,
        status="running",
        current_skill="",
        progress=0,
        skip_auto_push=False,
    )


@pytest.mark.asyncio
async def test_generate_images_node_success(mock_state: WorkflowState) -> None:
    with patch("workflow.skills.generate_images.get_model_config", return_value=_model_config(enabled=False, base_url=None)):
        result = await generate_images_node(mock_state)

    assert result["status"] == "running"
    article = result["generated_article"]
    assert article["cover_image"] == "http://test.com/img1.jpg"
    assert article["illustrations"] == ["http://test.com/img2.jpg", "http://test.com/img3.jpg"]


@pytest.mark.asyncio
async def test_generate_images_no_article(mock_state: WorkflowState) -> None:
    mock_state["generated_article"] = {}

    result = await generate_images_node(mock_state)

    assert result["status"] == "failed"
    assert "generated_article" in result["error"]


@pytest.mark.asyncio
async def test_generate_images_enabled_without_key_fallback(mock_state: WorkflowState) -> None:
    with patch("workflow.skills.generate_images.get_model_config", return_value=_model_config(enabled=True, api_key="", base_url=None)):
        result = await generate_images_node(mock_state)

    assert result["status"] == "running"
    article = result["generated_article"]
    assert article["cover_image"] == "http://test.com/img1.jpg"
    assert article["illustrations"] == ["http://test.com/img2.jpg", "http://test.com/img3.jpg"]


@pytest.mark.asyncio
async def test_generate_images_uses_separate_image_model_config(mock_state: WorkflowState) -> None:
    with patch("workflow.skills.generate_images.get_model_config", return_value=_model_config(enabled=True, api_key="image-key", model="flux-dev")):
        with patch("openai.AsyncOpenAI") as mock_async_openai:
            with patch(
                "workflow.skills.generate_images._generate_dalle_image",
                new=AsyncMock(side_effect=["http://gen/cover.png", "http://gen/1.png", "http://gen/2.png", "http://gen/3.png"]),
            ):
                result = await generate_images_node(mock_state)

    article = result["generated_article"]
    assert article["cover_image"] == "http://gen/cover.png"
    assert article["illustrations"] == ["http://gen/1.png", "http://gen/2.png", "http://gen/3.png"]
    mock_async_openai.assert_called_once_with(api_key="image-key", base_url="https://image.example.com/v1")


@pytest.mark.asyncio
async def test_generate_images_retries_on_rate_limit(mock_state: WorkflowState) -> None:
    class _RateLimitError(Exception):
        status_code = 429

    sleep_mock = AsyncMock()
    with patch("workflow.skills.generate_images.get_model_config", return_value=_model_config(enabled=True, api_key="image-key")):
        with patch("openai.AsyncOpenAI"):
            with patch(
                "workflow.skills.generate_images._generate_dalle_image",
                new=AsyncMock(
                    side_effect=[
                        _RateLimitError("rate limit reached"),
                        "http://gen/cover.png",
                        "http://gen/1.png",
                        "http://gen/2.png",
                        "http://gen/3.png",
                    ]
                ),
            ):
                with patch("workflow.skills.generate_images.asyncio.sleep", new=sleep_mock):
                    result = await generate_images_node(mock_state)

    article = result["generated_article"]
    assert article["cover_image"] == "http://gen/cover.png"
    assert article["illustrations"] == ["http://gen/1.png", "http://gen/2.png", "http://gen/3.png"]
    sleep_mock.assert_awaited_once_with(5)
