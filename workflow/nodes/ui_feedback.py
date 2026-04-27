"""Skill 6: ui_feedback 节点实现。
通过 WebSocket 向前端推送任务最终状态和结果（由 graph 层的 run_workflow 处理实际发送，本节点负责标记到达终点）。
"""
from __future__ import annotations

import time

import structlog

from workflow.state import WorkflowState

logger = structlog.get_logger(__name__)


async def ui_feedback_node(state: WorkflowState) -> dict:
    """最终反馈节点。"""
    task_id = state["task_id"]
    
    start_time = time.monotonic()
    
    logger.info("skill_start", task_id=task_id, skill="ui_feedback", status="running")
    
    # 到达这里意味着前面的流程全都成功
    duration_ms = round((time.monotonic() - start_time) * 1000)
    
    logger.info(
        "skill_done",
        task_id=task_id,
        skill="ui_feedback",
        status="done",
        duration_ms=duration_ms,
    )
    
    return {
        "status": "done",
        "current_skill": "ui_feedback",
        "progress": 100,
    }
