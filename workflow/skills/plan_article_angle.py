"""Build the dynamic article blueprint from task brief and article type."""
from __future__ import annotations

from typing import Any

from workflow.state import WorkflowState


async def plan_article_angle_node(state: WorkflowState) -> dict[str, Any]:
    """Create a dynamic section plan for the current article."""
    planning_state = dict(state.get("planning_state") or {})
    topic = str(state.get("task_brief", {}).get("topic", ""))
    planning_state["article_blueprint"] = {
        "thesis": f"{topic} 正在从事件走向趋势",
        "sections": [
            {"heading": "发生了什么", "goal": "交代背景"},
            {"heading": "趋势判断", "goal": "解释驱动因素"},
            {"heading": "风险边界", "goal": "说明不确定性"},
        ],
    }
    return {
        "status": "running",
        "current_skill": "plan_article_angle",
        "progress": 44,
        "planning_state": planning_state,
    }
