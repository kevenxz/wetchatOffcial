from api.models import TaskResponse
from workflow.state import WorkflowState


def test_workflow_state_supports_new_agent_blocks() -> None:
    state: WorkflowState = {
        "task_id": "task-1",
        "keywords": "AI agent",
        "original_keywords": "AI agent",
        "generation_config": {},
        "task_brief": {},
        "planning_state": {},
        "research_state": {},
        "writing_state": {},
        "visual_state": {},
        "quality_state": {},
        "status": "pending",
        "current_skill": "",
        "progress": 0,
        "retry_count": 0,
        "error": None,
        "generated_article": {},
    }

    assert "task_brief" in state
    assert "quality_state" in state


def test_task_response_exposes_new_agent_blocks() -> None:
    assert "task_brief" in TaskResponse.model_fields
    assert "planning_state" in TaskResponse.model_fields
    assert "research_state" in TaskResponse.model_fields
    assert "writing_state" in TaskResponse.model_fields
    assert "visual_state" in TaskResponse.model_fields
    assert "quality_state" in TaskResponse.model_fields
