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

STYLE_CONFIG_FILE = DATA_DIR / "style_config.json"

DEFAULT_STYLE = {
    "h1": "font-size: 22px; font-weight: bold; margin-top: 24px; margin-bottom: 16px; color: #333333; line-height: 1.4;",
    "h2": "font-size: 18px; font-weight: bold; margin-top: 20px; margin-bottom: 12px; color: #333333; border-left: 4px solid #1677ff; padding-left: 8px;",
    "h3": "font-size: 16px; font-weight: bold; margin-top: 16px; margin-bottom: 8px; color: #555555;",
    "p": "font-size: 15px; line-height: 1.75; margin-bottom: 16px; color: #3f3f3f; letter-spacing: 0.5px;",
    "strong": "font-weight: bold; color: #1677ff;",
    "blockquote": "padding: 10px 15px; border-left: 4px solid #e2e2e2; background-color: #f7f7f7; color: #666; font-size: 14px; margin-bottom: 16px;",
    "ul": "margin-bottom: 16px; padding-left: 20px; color: #3f3f3f;",
    "ol": "margin-bottom: 16px; padding-left: 20px; color: #3f3f3f;",
    "li": "font-size: 15px; line-height: 1.75; margin-bottom: 6px;",
    "a": "color: #1677ff; text-decoration: none;",
}

_style_config: dict[str, str] = {}

def get_style_config() -> dict[str, str]:
    """获取样式配置。"""
    global _style_config
    if _style_config:
        return _style_config
        
    if not STYLE_CONFIG_FILE.exists():
        _style_config = dict(DEFAULT_STYLE)
        return _style_config
        
    try:
        with open(STYLE_CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # 合并默认值以防缺少键
            _style_config = {**DEFAULT_STYLE, **data}
    except Exception as e:
        import structlog
        logger = structlog.get_logger(__name__)
        logger.error("load_style_config_failed", error=str(e))
        _style_config = dict(DEFAULT_STYLE)
        
    return _style_config

def save_style_config(new_style: dict[str, str]) -> dict[str, str]:
    """保存样式配置。"""
    global _style_config
    _style_config.update(new_style)
    
    try:
        if not DATA_DIR.exists():
            DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(STYLE_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(_style_config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        import structlog
        logger = structlog.get_logger(__name__)
        logger.error("save_style_config_failed", error=str(e))
        
    return _style_config

# 初始化时加载
load_tasks()
