"""Tests for ui_feedback skill."""
import pytest
from unittest.mock import patch

from workflow.state import WorkflowState
from workflow.skills.ui_feedback import ui_feedback_node


@pytest.fixture
def mock_state():
    return WorkflowState(
        task_id="test_task_123",
        keywords="ai",
        search_results=[],
        extracted_contents=[],
        generated_article={},
        draft_info={"media_id": "abc"},
        retry_count=0,
        error=None,
        status="running",
        current_skill="",
        progress=0,
    )


@pytest.mark.asyncio
async def test_ui_feedback_node_success(mock_state):
    result = await ui_feedback_node(mock_state)
    
    assert result["status"] == "done"
    assert result["current_skill"] == "ui_feedback"
    assert result["progress"] == 100
    assert "error" not in result
