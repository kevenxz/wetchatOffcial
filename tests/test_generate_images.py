from __future__ import annotations

"""Tests for the generate_images workflow skill."""

import base64
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from api.models import ImageModelConfig, ModelConfig, TextModelConfig
from workflow.skills.generate_images import (
    _extract_generated_image_from_chat_response,
    _extract_generated_image_from_images_response,
    generate_images_node,
)
from workflow.state import WorkflowState


def _model_config(
    enabled: bool = False,
    api_key: str = "",
    model: str = "image-model",
    base_url: str | None = "https://image.example.com/v1",
) -> ModelConfig:
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


@pytest.mark.asyncio
async def test_generate_images_waits_before_retrying_empty_result(mock_state: WorkflowState) -> None:
    sleep_mock = AsyncMock()
    with patch("workflow.skills.generate_images.get_model_config", return_value=_model_config(enabled=True, api_key="image-key")):
        with patch("openai.AsyncOpenAI"):
            with patch(
                "workflow.skills.generate_images._generate_dalle_image",
                new=AsyncMock(
                    side_effect=[
                        "",
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


@pytest.mark.asyncio
async def test_generate_images_waits_before_retrying_temporary_generation_failure(mock_state: WorkflowState) -> None:
    sleep_mock = AsyncMock()
    with patch("workflow.skills.generate_images.get_model_config", return_value=_model_config(enabled=True, api_key="image-key")):
        with patch("openai.AsyncOpenAI"):
            with patch(
                "workflow.skills.generate_images._generate_dalle_image",
                new=AsyncMock(
                    side_effect=[
                        RuntimeError("temporary connection issue"),
                        "http://gen/cover.png",
                        "http://gen/1.png",
                        "http://gen/2.png",
                        "http://gen/3.png",
                    ]
                ),
            ):
                with patch(
                    "workflow.skills.generate_images._generate_chat_completion_image",
                    new=AsyncMock(side_effect=RuntimeError("temporary server error")),
                ):
                    with patch("workflow.skills.generate_images.asyncio.sleep", new=sleep_mock):
                        result = await generate_images_node(mock_state)

    article = result["generated_article"]
    assert article["cover_image"] == "http://gen/cover.png"
    assert article["illustrations"] == ["http://gen/1.png", "http://gen/2.png", "http://gen/3.png"]
    sleep_mock.assert_awaited_once_with(5)


@pytest.mark.asyncio
async def test_generate_images_uses_chart_prompt_for_markdown_chart_blocks(mock_state: WorkflowState) -> None:
    mock_state["generated_article"]["title"] = "原油市场深度分析"
    mock_state["generated_article"]["content"] = (
        "## 市场概况\n"
        "先交代市场背景。[插图1]\n\n"
        "## 数据图表观察\n"
        "### 图表2：近5年国际原油价格走势图\n"
        "[插图2]\n"
        "- 数据来源：EIA、FRED\n"
        "- 图表说明：展示油价长期趋势与关键拐点。\n\n"
        "## 未来展望\n"
        "总结后市风险。[插图3]"
    )

    image_generate_mock = AsyncMock(
        side_effect=[
            "http://gen/cover.png",
            "http://gen/1.png",
            "http://gen/2.png",
            "http://gen/3.png",
        ]
    )
    with patch("workflow.skills.generate_images.get_model_config", return_value=_model_config(enabled=True, api_key="image-key")):
        with patch("openai.AsyncOpenAI"):
            with patch("workflow.skills.generate_images._generate_dalle_image", new=image_generate_mock):
                result = await generate_images_node(mock_state)

    article = result["generated_article"]
    assert article["illustrations"] == ["http://gen/1.png", "http://gen/2.png", "http://gen/3.png"]

    chart_prompt = image_generate_mock.await_args_list[2].args[1]
    assert "图表型信息图" in chart_prompt
    assert "图表标题：近5年国际原油价格走势图" in chart_prompt
    assert "数据来源参考：EIA、FRED" in chart_prompt
    assert "图表说明：展示油价长期趋势与关键拐点" in chart_prompt


def test_extract_generated_image_from_chat_response_string_content() -> None:
    response = type(
        "Response",
        (),
        {
            "choices": [
                type(
                    "Choice",
                    (),
                    {
                        "message": type(
                            "Message",
                            (),
                            {"content": "https://cdn.example.com/generated-image.png"},
                        )()
                    },
                )()
            ]
        },
    )()

    assert _extract_generated_image_from_chat_response(response, task_id="task", image_kind="cover") == "https://cdn.example.com/generated-image.png"


def test_extract_generated_image_from_images_response_saves_b64_file(tmp_path: Path) -> None:
    image_bytes = b"\x89PNG\r\n\x1a\nabc"
    response = type(
        "Response",
        (),
        {
            "data": [type("ImageData", (), {"b64_json": base64.b64encode(image_bytes).decode("ascii")})()],
            "output_format": "png",
        },
    )()

    with patch("workflow.skills.generate_images.GENERATED_IMAGES_DIR", tmp_path):
        image_ref = _extract_generated_image_from_images_response(response, task_id="task", image_kind="cover")

    saved_path = Path(image_ref)
    assert saved_path.is_file()
    assert saved_path.read_bytes() == image_bytes


def test_extract_generated_image_from_chat_response_saves_inline_b64_file(tmp_path: Path) -> None:
    image_bytes = b"\x89PNG\r\n\x1a\nabc"
    response = type(
        "Response",
        (),
        {
            "choices": [
                type(
                    "Choice",
                    (),
                    {
                        "message": type(
                            "Message",
                            (),
                            {
                                "content": [
                                    {
                                        "b64_json": base64.b64encode(image_bytes).decode("ascii"),
                                        "output_format": "png",
                                    }
                                ]
                            },
                        )()
                    },
                )()
            ]
        },
    )()

    with patch("workflow.skills.generate_images.GENERATED_IMAGES_DIR", tmp_path):
        image_ref = _extract_generated_image_from_chat_response(response, task_id="task", image_kind="illustration_1")

    saved_path = Path(image_ref)
    assert saved_path.is_file()
    assert saved_path.read_bytes() == image_bytes


@pytest.mark.asyncio
async def test_generate_images_falls_back_to_chat_completions(mock_state: WorkflowState) -> None:
    unsupported_error = RuntimeError("images.generate is not supported by this provider")
    with patch("workflow.skills.generate_images.get_model_config", return_value=_model_config(enabled=True, api_key="image-key", model="gemini-3.1-flash-image-preview")):
        with patch("openai.AsyncOpenAI") as mock_async_openai:
            with patch(
                "workflow.skills.generate_images._generate_dalle_image",
                new=AsyncMock(side_effect=unsupported_error),
            ):
                with patch(
                    "workflow.skills.generate_images._generate_chat_completion_image",
                    new=AsyncMock(
                        side_effect=[
                            ("http://gen/cover.png", object()),
                            ("http://gen/1.png", object()),
                            ("http://gen/2.png", object()),
                            ("http://gen/3.png", object()),
                        ]
                    ),
                ) as chat_mock:
                    result = await generate_images_node(mock_state)

    article = result["generated_article"]
    assert article["cover_image"] == "http://gen/cover.png"
    assert article["illustrations"] == ["http://gen/1.png", "http://gen/2.png", "http://gen/3.png"]
    assert chat_mock.await_count == 4
    mock_async_openai.assert_called_once_with(api_key="image-key", base_url="https://image.example.com/v1")
