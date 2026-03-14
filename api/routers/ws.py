"""WebSocket 路由：推送任务实时进度。"""
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.ws_manager import manager

router = APIRouter()


@router.websocket("/ws/tasks/{task_id}")
async def task_ws(ws: WebSocket, task_id: str) -> None:
    """客户端通过此端点订阅指定任务的实时进度推送。"""
    await manager.connect(task_id, ws)
    try:
        # 保持连接存活，等待客户端主动断开
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(task_id, ws)
