"""Tests for generate_article skill."""
import pytest
from unittest.mock import AsyncMock, patch

from workflow.state import WorkflowState
from workflow.skills.generate_article import generate_article_node, ArticleOutput


@pytest.fixture
def mock_state():
    return WorkflowState(
        task_id="test_task_123",
        keywords="ai news",
        search_results=["https://example.com/1"],
        extracted_contents=[
            {"url": "https://example.com/1", "title": "Page 1", "text": "Some text content here"}
        ],
        generated_article={},
        draft_info=None,
        retry_count=0,
        error=None,
        status="running",
        current_skill="",
        progress=0,
    )


@pytest.mark.asyncio
async def test_generate_article_success(mock_state):
    with patch("workflow.skills.generate_article.ChatPromptTemplate") as mock_prompt_class:
        with patch.dict("os.environ", {"OPENAI_API_KEY": "fake_key"}):
            # Create a mock chain fake
            mock_chain = AsyncMock()
            mock_prompt_class.from_messages.return_value.__or__.return_value = mock_chain
            
            # Mock the return of ainvoke
            fake_output = ArticleOutput(
                title="Test Title",
                alt_titles=["Alt 1", "Alt 2"],
                content="A" * 600  # >= 500 chars to pass validation
            )
            mock_chain.ainvoke.return_value = fake_output
            
            result = await generate_article_node(mock_state)
            
            assert result["status"] == "running"
            assert result["current_skill"] == "generate_article"
            assert "generated_article" in result
            assert result["generated_article"]["title"] == "Test Title"
            assert result["generated_article"]["content"] == "A" * 600


@pytest.mark.asyncio
async def test_generate_article_missing_api_key(mock_state):
    with patch.dict("os.environ", {}, clear=True):
        result = await generate_article_node(mock_state)
        
        assert result["status"] == "failed"
        assert "未配置 OPENAI_API_KEY" in result["error"]


@pytest.mark.asyncio
async def test_generate_article_too_short(mock_state):
    with patch("workflow.skills.generate_article.ChatPromptTemplate") as mock_prompt_class:
        with patch.dict("os.environ", {"OPENAI_API_KEY": "fake_key"}):
            mock_chain = AsyncMock()
            mock_prompt_class.from_messages.return_value.__or__.return_value = mock_chain
            
            # Output is too short
            fake_output = ArticleOutput(
                title="Test Title",
                alt_titles=["Alt 1", "Alt 2"],
                content="Too short" # < 500 chars
            )
            mock_chain.ainvoke.return_value = fake_output
            
            result = await generate_article_node(mock_state)
            
            assert result["status"] == "failed"
            assert "文章生成失败" in result["error"] or "生成的文章过短" in result["error"]
