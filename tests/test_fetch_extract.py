"""Tests for fetch_extract skill."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from workflow.state import WorkflowState
from workflow.skills.fetch_extract import fetch_extract_node, _is_valid_image


@pytest.fixture
def mock_state():
    return WorkflowState(
        task_id="test_task_123",
        keywords="ai news",
        generation_config={"audience_roles": ["泛科技读者"], "article_strategy": "auto"},
        search_results=["https://example.com/1", "https://example.com/2"],
        extracted_contents=[],
        article_plan={},
        generated_article={},
        draft_info=None,
        retry_count=0,
        error=None,
        status="running",
        current_skill="",
        progress=0,
        skip_auto_push=False,
    )


def test_is_valid_image():
    assert _is_valid_image("https://example.com/img.jpg") == True
    assert _is_valid_image("https://example.com/img.png") == True
    assert _is_valid_image("https://example.com/img.gif") == False
    assert _is_valid_image("data:image/jpeg;base64,xxxx") == False
    
    # Test with size
    assert _is_valid_image("https://example.com/img.jpg", {"width": "200", "height": "400"}) == False
    assert _is_valid_image("https://example.com/img.jpg", {"width": "400", "height": "400"}) == True
    assert _is_valid_image("https://example.com/img.jpg", {"width": "auto"}) == True


@pytest.mark.asyncio
async def test_fetch_extract_node_success(mock_state):
    with patch("workflow.skills.fetch_extract.httpx.AsyncClient") as mock_client_class:
        with patch("workflow.skills.fetch_extract.trafilatura.extract") as mock_extract:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            mock_resp1 = MagicMock()
            mock_resp1.text = "<html><title>Page 1</title><body><img src='http://test.com/1.jpg' width='400' height='400'></body></html>"
            
            mock_resp2 = MagicMock()
            mock_resp2.text = "<html><title>Page 2</title><body><p>This is page 2 content</p></body></html>"
            
            # They will be processed in some order, we can mock side_effect based on url or just generic
            mock_client.get.side_effect = [mock_resp1, mock_resp2]
            
            mock_extract.side_effect = [
                "This is a long enough extracted content for page 1 that exceeds 50 characters limit.",
                "This is a long enough extracted content for page 2 that exceeds 50 characters limit."
            ]
            
            result = await fetch_extract_node(mock_state)
            
            assert result["status"] == "running"
            assert result["current_skill"] == "fetch_and_extract"
            assert "error" not in result
            assert len(result["extracted_contents"]) == 2
            
            contents = sorted(result["extracted_contents"], key=lambda x: x["url"])
            
            # Since gather order is same as input order (result order matches tasks order)
            assert contents[0]["url"] == "https://example.com/1"
            assert contents[0]["title"] == "Page 1"
            assert contents[0]["images"] == ["http://test.com/1.jpg"]
            assert contents[0]["text"] == "This is a long enough extracted content for page 1 that exceeds 50 characters limit."


@pytest.mark.asyncio
async def test_fetch_extract_node_no_urls(mock_state):
    mock_state["search_results"] = []
    
    result = await fetch_extract_node(mock_state)
    
    assert result["status"] == "failed"
    assert "没有找到可提取的 URL" in result["error"]


@pytest.mark.asyncio
async def test_fetch_extract_node_all_failed(mock_state):
    with patch("workflow.skills.fetch_extract.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get.side_effect = Exception("Fetch failed")
        
        result = await fetch_extract_node(mock_state)
        
        assert result["status"] == "failed"
        assert "所有页面抓取或内容提取均失败" in result["error"]
