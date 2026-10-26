"""统一错误处理节点。"""
from __future__ import annotations

import structlog

from api.alerts import send_alert
from workflow.state import WorkflowState

logger = structlog.get_logger(__name__)


async def error_handler(state: WorkflowState) -> dict:
    """记录错误日志、发送告警，并将任务状态标记为 failed。

    当工作流中任何节点发生异常且被 conditional edge 路由到此节点时，
    负责统一的错误记录、告警和状态收尾。告警本身失败不会影响任务收尾。
    """
    task_id = str(state.get("task_id") or "")
    error_msg = state.get("error") or "未知错误"
    failed_skill = str(state.get("current_skill") or "")
    completed_nodes = list(state.get("completed_nodes") or [])

    logger.error(
        "workflow_error",
        task_id=task_id,
        skill="error_handler",
        status="failed",
        duration_ms=0,
        error=error_msg,
        failed_skill=failed_skill,
        completed_nodes=completed_nodes,
    )

    await send_alert(
        task_id=task_id,
        skill=failed_skill,
        error=error_msg,
        status="failed",
        extra={"completed_nodes": completed_nodes, "keywords": state.get("keywords")},
    )

    return {
        "status": "failed",
        "current_skill": "error_handler",
        "progress": 0,
    }
