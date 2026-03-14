"""Tests for push_to_draft skill."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from workflow.state import WorkflowState
from workflow.skills.push_to_draft import push_to_draft_node, _build_html_content


@pytest.fixture
def mock_state():
    return WorkflowState(
        task_id="test_task_123",
        keywords="ai news",
        search_results=[],
        extracted_contents=[],
        generated_article={
            "title": "Title",
            "content": "Para 1 [插图1]\n\nPara 2 [插图2]",
            "illustrations": ["http://test.com/1.jpg", "http://test.com/2.jpg"]
        },
        draft_info=None,
        retry_count=0,
        error=None,
        status="running",
        current_skill="",
        progress=0,
    )


def test_build_html_content():
    article = {
        "content": "Hello [插图1]\n\nWorld [插图2]",
        "illustrations": ["img1.jpg", "img2.jpg"]
    }
    html = _build_html_content(article)
    assert '<img src="img1.jpg"' in html
    assert '<img src="img2.jpg"' in html
    assert '<p>' in html
    assert '</p>' in html


@pytest.mark.asyncio
async def test_push_to_draft_mock_no_appid(mock_state):
    with patch.dict("os.environ", {}, clear=True):
        result = await push_to_draft_node(mock_state)
        
        assert result["status"] == "running"
        assert result["current_skill"] == "push_to_draft"
        assert result["draft_info"]["media_id"] == "mock_media_id_12345"


@pytest.mark.asyncio
async def test_push_to_draft_success(mock_state):
    with patch.dict("os.environ", {"WECHAT_APP_ID": "id1", "WECHAT_APP_SECRET": "sec1"}):
        with patch("workflow.skills.push_to_draft.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            mock_token_resp = MagicMock()
            mock_token_resp.json.return_value = {"access_token": "TOKEN", "expires_in": 7200}
            
            mock_draft_resp = MagicMock()
            mock_draft_resp.json.return_value = {"media_id": "real_media_id_789"}
            
            # 1. token, 2. draft post
            mock_client.get.return_value = mock_token_resp
            mock_client.post.return_value = mock_draft_resp
            
            result = await push_to_draft_node(mock_state)
            
            assert result["status"] == "running"
            assert result["draft_info"]["media_id"] == "real_media_id_789"


@pytest.mark.asyncio
async def test_push_to_draft_no_article(mock_state):
    mock_state["generated_article"] = {}
    result = await push_to_draft_node(mock_state)
    assert result["status"] == "failed"
