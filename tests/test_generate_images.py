"""Tests for generate_images skill."""
import pytest
from unittest.mock import patch

from workflow.state import WorkflowState
from workflow.skills.generate_images import generate_images_node


@pytest.fixture
def mock_state():
    return WorkflowState(
        task_id="test_task_123",
        keywords="ai news",
        search_results=[],
        extracted_contents=[
            {"url": "1", "title": "A", "text": "...", "images": ["http://test.com/img1.jpg", "http://test.com/img2.jpg"]},
            {"url": "2", "title": "B", "text": "...", "images": ["http://test.com/img3.jpg"]}
        ],
        generated_article={
            "title": "Title",
            "content": "This is a paragraph. [插图1]\n\nThis is another. [插图2]\n\nLast one. [插图3]"
        },
        draft_info=None,
        retry_count=0,
        error=None,
        status="running",
        current_skill="",
        progress=0,
    )


@pytest.mark.asyncio
async def test_generate_images_node_success(mock_state):
    result = await generate_images_node(mock_state)
    
    assert result["status"] == "running"
    assert "error" not in result
    article = result["generated_article"]
    
    # 1 cover + 2 illustrations = 3 images used out of 3 total. 
    # [插图1] [插图2] [插图3] means 3 required, but we only have 2 left after cover.
    # So cover = img1, illustrations = [img2, img3]
    assert article["cover_image"] == "http://test.com/img1.jpg"
    assert len(article["illustrations"]) == 2
    assert article["illustrations"] == ["http://test.com/img2.jpg", "http://test.com/img3.jpg"]


@pytest.mark.asyncio
async def test_generate_images_no_article(mock_state):
    mock_state["generated_article"] = {}
    
    result = await generate_images_node(mock_state)
    
    assert result["status"] == "failed"
    assert "缺少 generated_article" in result["error"]
