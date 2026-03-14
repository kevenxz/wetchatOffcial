"""共享内存存储。"""
from __future__ import annotations

import json
import os
from pathlib import Path

from api.models import TaskResponse

DATA_DIR = Path("data")
TASKS_FILE = DATA_DIR / "tasks.json"

# 进程内内存任务存储：task_id -> TaskResponse
task_store: dict[str, TaskResponse] = {}

def load_tasks() -> None:
    """从本地 JSON 文件加载任务到内存。"""
    if not TASKS_FILE.exists():
        return
    try:
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for k, v in data.items():
                task_store[k] = TaskResponse(**v)
    except Exception as e:
        import structlog
        logger = structlog.get_logger(__name__)
        logger.error("load_tasks_failed", error=str(e))

def save_tasks() -> None:
    """将内存中的任务持久化到本地 JSON 文件。"""
    try:
        if not DATA_DIR.exists():
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            
        data = {k: v.model_dump(mode="json") for k, v in task_store.items()}
        # 写入临时文件再重命名，避免写一半崩溃导致数据损坏
        temp_file = TASKS_FILE.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        temp_file.replace(TASKS_FILE)
    except Exception as e:
        import structlog
        logger = structlog.get_logger(__name__)
        logger.error("save_tasks_failed", error=str(e))

# 初始化时加载
load_tasks()
