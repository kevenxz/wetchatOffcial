"""WebSocket 连接管理器。"""
from __future__ import annotations

import json
from collections import defaultdict

import structlog
from fastapi import WebSocket

logger = structlog.get_logger(__name__)


class ConnectionManager:
    """管理按 task_id 分组的 WebSocket 连接。"""

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, task_id: str, ws: WebSocket) -> None:
        """接受并注册一个 WebSocket 连接。"""
        await ws.accept()
        self._connections[task_id].add(ws)
        logger.info("ws_connected", task_id=task_id)

    def disconnect(self, task_id: str, ws: WebSocket) -> None:
        """移除一个 WebSocket 连接。"""
        self._connections[task_id].discard(ws)
        if not self._connections[task_id]:
            del self._connections[task_id]
        logger.info("ws_disconnected", task_id=task_id)

    async def broadcast(self, task_id: str, data: dict) -> None:
        """向指定 task_id 的所有客户端广播 JSON 消息。"""
        dead: list[WebSocket] = []
        for ws in self._connections.get(task_id, set()):
            try:
                await ws.send_text(json.dumps(data, ensure_ascii=False))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections[task_id].discard(ws)


# 全局单例
manager = ConnectionManager()
