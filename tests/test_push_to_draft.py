"""Tests for push_to_draft skill."""
from unittest.mock import AsyncMock, patch

import pytest

from workflow.skills.push_to_draft import push_to_draft_node
from workflow.state import WorkflowState


@pytest.fixture
def mock_state():
    return WorkflowState(
        task_id="test_task_123",
        keywords="ai news",
        generation_config={"audience_roles": ["泛科技读者"], "article_strategy": "auto"},
        search_results=[],
        extracted_contents=[],
        article_plan={},
        generated_article={
            "title": "Title",
            "content": "Para 1 [插图1]\n\nPara 2 [插图2]",
            "illustrations": ["http://test.com/1.jpg", "http://test.com/2.jpg"],
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
async def test_push_to_draft_mock_no_appid(mock_state):
    with patch.dict("os.environ", {}, clear=True):
        result = await push_to_draft_node(mock_state)

        assert result["status"] == "running"
        assert result["current_skill"] == "push_to_draft"
        assert result["draft_info"]["media_id"] == "mock_media_id_12345"


@pytest.mark.asyncio
async def test_push_to_draft_success(mock_state):
    with patch.dict("os.environ", {"WECHAT_APP_ID": "id1", "WECHAT_APP_SECRET": "sec1"}):
        with patch("workflow.skills.push_to_draft.push_article_to_wechat_draft", new_callable=AsyncMock) as mock_push:
            mock_push.return_value = {"media_id": "real_media_id_789"}

            result = await push_to_draft_node(mock_state)

            assert result["status"] == "running"
            assert result["draft_info"]["media_id"] == "real_media_id_789"
            mock_push.assert_awaited_once()


@pytest.mark.asyncio
async def test_push_to_draft_no_article(mock_state):
    mock_state["generated_article"] = {}
    result = await push_to_draft_node(mock_state)
    assert result["status"] == "failed"
