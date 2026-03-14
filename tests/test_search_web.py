"""Tests for search_web skill."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from workflow.state import WorkflowState
from workflow.skills.search_web import search_web_node, _filter_links


@pytest.fixture
def mock_state():
    return WorkflowState(
        task_id="test_task_123",
        keywords="ai news",
        search_results=[],
        extracted_contents=[],
        generated_article={},
        draft_info=None,
        retry_count=0,
        error=None,
        status="running",
        current_skill="",
        progress=0,
    )


def test_filter_links():
    links = [
        "https://example.com/1",
        "https://example.com/1/",
        "https://example.com/2",
        "https://example.com/2"
    ]
    filtered = _filter_links(links)
    assert filtered == ["https://example.com/1", "https://example.com/2"]


@pytest.mark.asyncio
async def test_search_web_node_google_success(mock_state):
    with patch("workflow.skills.search_web.httpx.AsyncClient") as mock_client_class:
        with patch.dict("os.environ", {"SERPAPI_API_KEY": "fake_key"}):
            # Setup mock
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            mock_resp = MagicMock()
            mock_resp.json.return_value = {
                "organic_results": [
                    {"link": "https://example.com/a"},
                    {"link": "https://example.com/b"},
                ]
            }
            mock_client.get.return_value = mock_resp
            
            # Execute
            result = await search_web_node(mock_state)
            
            # Assert
            assert result["status"] == "running"
            assert "error" not in result
            assert result["current_skill"] == "search_web"
            assert result["search_results"] == ["https://example.com/a", "https://example.com/b"]
            assert result["retry_count"] == 0


@pytest.mark.asyncio
async def test_search_web_node_retry(mock_state):
    with patch("workflow.skills.search_web.httpx.AsyncClient") as mock_client_class:
        with patch("workflow.skills.search_web.asyncio.sleep") as mock_sleep:
            with patch.dict("os.environ", {"SERPAPI_API_KEY": "fake_key"}):
                mock_client = AsyncMock()
                mock_client_class.return_value.__aenter__.return_value = mock_client
                
                # First 2 times raise exception, 3rd time success
                mock_resp = MagicMock()
                mock_resp.json.return_value = {
                    "organic_results": [{"link": "https://example.com/c"}]
                }
                
                mock_client.get.side_effect = [
                    Exception("Network Error 1"),
                    Exception("Network Error 2"),
                    mock_resp
                ]
                
                result = await search_web_node(mock_state)
                
                assert result["status"] == "running"
                assert result["search_results"] == ["https://example.com/c"]
                assert result["retry_count"] == 2
                assert mock_client.get.call_count == 3


@pytest.mark.asyncio
async def test_search_web_node_no_api_key(mock_state):
    with patch.dict("os.environ", {}, clear=True):
        result = await search_web_node(mock_state)
        
        assert result["status"] == "failed"
        assert "未配置搜索引擎 API Key" in result["error"]
