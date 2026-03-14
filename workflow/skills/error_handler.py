"""统一错误处理节点。"""
from __future__ import annotations

import structlog

from workflow.state import WorkflowState

logger = structlog.get_logger(__name__)


async def error_handler(state: WorkflowState) -> dict:
    """记录错误日志并将任务状态标记为 failed。

    当工作流中任何节点发生异常且被 conditional edge 路由到此节点时，
    负责统一的错误记录和状态收尾。
    """
    error_msg = state.get("error") or "未知错误"

    logger.error(
        "workflow_error",
        task_id=state["task_id"],
        skill="error_handler",
        status="failed",
        duration_ms=0,
        error=error_msg,
    )

    return {
        "status": "failed",
        "current_skill": "error_handler",
        "progress": 0,
    }
