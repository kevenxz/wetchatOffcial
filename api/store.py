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
    "container": "padding: 0 8px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif; color: #2c3e50; line-height: 1.8; font-size: 16px; letter-spacing: 0.3px; word-break: break-word; overflow-wrap: break-word;",
    "h1": "font-size: 28px; font-weight: 700; color: #1a1a1a; margin: 10px 0 20px; text-align: center; padding-bottom: 12px; border-bottom: 2px solid #07c160; letter-spacing: 1px; line-height: 1.4;",
    "h2": "font-size: 22px; font-weight: 600; color: #2c3e50; margin: 20px 0 14px; padding-left: 12px; border-left: 4px solid #07c160; line-height: 1.4; letter-spacing: 0.5px;",
    "h3": "font-size: 19px; font-weight: 600; color: #34495e; margin: 24px 0 12px; padding-left: 10px; border-left: 3px solid #07c160; letter-spacing: 0.3px;",
    "h4": "font-size: 17px; font-weight: 600; color: #07c160; margin: 20px 0 10px; letter-spacing: 0.3px;",
    "h5": "font-size: 16px; font-weight: 600; color: #5a6c7d; margin: 18px 0 8px;",
    "h6": "font-size: 15px; font-weight: 600; color: #7f8c8d; margin: 16px 0 8px;",
    "p": "margin: 8px 0; font-size: 16px; color: #34495e; line-height: 1.8; letter-spacing: 0.5px;",
    "strong": "font-weight: 600; color: #07c160; letter-spacing: 0.2px;",
    "em": "font-style: italic; color: #07c160; font-weight: 500;",
    "del": "text-decoration: line-through; color: #94a3b8; opacity: 0.7;",
    "blockquote": "border-left: 4px solid #07c160; background: #f6f8fa; padding: 16px 20px; margin: 20px 0; color: #475569; border-radius: 2px;",
    "ul": "padding-left: 24px; list-style-type: disc; color: #34495e; margin: 8px 0;",
    "ol": "padding-left: 24px; list-style-type: decimal; color: #34495e; margin: 8px 0;",
    "li": "padding-left: 4px; margin: 8px 0; line-height: 1.8; font-size: 16px; color: #34495e;",
    "a": "color: #07c160; text-decoration: none; border-bottom: 1px solid #07c160; font-weight: 500;",
    "hr": "border: none; height: 1px; background: #e2e8f0; margin: 28px 0;",
    "img": "display: block; margin: 24px auto; max-width: 100%; border-radius: 4px;",
    "figure": "margin: 24px 0; display: flex; flex-direction: column; justify-content: center; align-items: center;",
    "figcaption": "text-align: center; font-size: 14px; color: #94a3b8; margin-top: 8px; letter-spacing: 0.2px;",
    "code": "background: #f0fdf4; padding: 3px 6px; border-radius: 3px; color: #059669; font-family: 'SF Mono', Monaco, 'Cascadia Code', 'Roboto Mono', Consolas, monospace; font-size: 0.9em; margin: 0 3px; border: 1px solid #bbf7d0;",
    "pre": "margin: 16px 0; overflow-x: auto;",
    "pre code": "display: block; background: #f8fafc; padding: 16px; border-radius: 4px; overflow-x: auto; font-family: 'SF Mono', Monaco, 'Cascadia Code', 'Roboto Mono', Consolas, monospace; font-size: 14px; line-height: 1.6; color: #334155; border: 1px solid #e2e8f0;",
    "table": "display: table; width: 100%; text-align: left; border-collapse: collapse; margin: 16px 0;",
    "th": "border: 1px solid #e2e8f0; padding: 10px 14px; font-size: 15px; color: #065f46; line-height: 1.6; background: #f0fdf4; font-weight: 600; letter-spacing: 0.3px;",
    "td": "border: 1px solid #e2e8f0; padding: 10px 14px; font-size: 15px; color: #334155; line-height: 1.6;",
}

PRESET_THEMES: dict[str, dict[str, str]] = {
    "默认主题": DEFAULT_STYLE,
    "学术论文": {
        "h1": "font-size: 24px; font-weight: bold; margin-top: 28px; margin-bottom: 16px; color: #1a1a1a; line-height: 1.35; text-align: center;",
        "h2": "font-size: 18px; font-weight: bold; margin-top: 24px; margin-bottom: 12px; color: #1a1a1a; border-bottom: 2px solid #333; padding-bottom: 4px;",
        "h3": "font-size: 16px; font-weight: bold; margin-top: 18px; margin-bottom: 8px; color: #333;",
        "p": "font-size: 15px; line-height: 2; margin-bottom: 14px; color: #333; text-indent: 2em; letter-spacing: 0.3px;",
        "strong": "font-weight: bold; color: #000;",
        "blockquote": "padding: 12px 16px; border-left: 3px solid #999; background-color: #fafafa; color: #555; font-size: 14px; margin-bottom: 14px; font-style: italic;",
        "ul": "margin-bottom: 14px; padding-left: 24px; color: #333;",
        "ol": "margin-bottom: 14px; padding-left: 24px; color: #333;",
        "li": "font-size: 15px; line-height: 2; margin-bottom: 4px;",
        "a": "color: #0645AD; text-decoration: underline;",
    },
    "极光玻璃": {
        "h1": "font-size: 24px; font-weight: 800; margin-top: 28px; margin-bottom: 16px; color: #6366f1; line-height: 1.3; background: linear-gradient(90deg, #6366f1, #a855f7); -webkit-background-clip: text; -webkit-text-fill-color: transparent;",
        "h2": "font-size: 19px; font-weight: 700; margin-top: 22px; margin-bottom: 12px; color: #7c3aed; border-left: 4px solid #a855f7; padding-left: 10px;",
        "h3": "font-size: 16px; font-weight: 600; margin-top: 16px; margin-bottom: 8px; color: #8b5cf6;",
        "p": "font-size: 15px; line-height: 1.8; margin-bottom: 16px; color: #4b5563; letter-spacing: 0.5px;",
        "strong": "font-weight: bold; color: #7c3aed;",
        "blockquote": "padding: 12px 16px; border-left: 4px solid #c084fc; background: linear-gradient(135deg, #f5f3ff, #ede9fe); color: #6d28d9; font-size: 14px; margin-bottom: 16px; border-radius: 0 8px 8px 0;",
        "ul": "margin-bottom: 16px; padding-left: 20px; color: #4b5563;",
        "ol": "margin-bottom: 16px; padding-left: 20px; color: #4b5563;",
        "li": "font-size: 15px; line-height: 1.8; margin-bottom: 6px;",
        "a": "color: #7c3aed; text-decoration: none; border-bottom: 1px dashed #a78bfa;",
    },
    "赛博朋克": {
        "h1": "font-size: 24px; font-weight: 900; margin-top: 28px; margin-bottom: 16px; color: #00ff9f; line-height: 1.3; text-transform: uppercase; letter-spacing: 2px;",
        "h2": "font-size: 19px; font-weight: 700; margin-top: 22px; margin-bottom: 12px; color: #00d4ff; border-left: 4px solid #ff0080; padding-left: 10px;",
        "h3": "font-size: 16px; font-weight: 600; margin-top: 16px; margin-bottom: 8px; color: #ff0080;",
        "p": "font-size: 15px; line-height: 1.75; margin-bottom: 16px; color: #e0e0e0; letter-spacing: 0.5px;",
        "strong": "font-weight: bold; color: #ff0080;",
        "blockquote": "padding: 12px 16px; border-left: 4px solid #00ff9f; background-color: #1a1a2e; color: #00d4ff; font-size: 14px; margin-bottom: 16px;",
        "ul": "margin-bottom: 16px; padding-left: 20px; color: #e0e0e0;",
        "ol": "margin-bottom: 16px; padding-left: 20px; color: #e0e0e0;",
        "li": "font-size: 15px; line-height: 1.75; margin-bottom: 6px;",
        "a": "color: #00ff9f; text-decoration: none;",
    },
    "莫兰迪森林": {
        "h1": "font-size: 22px; font-weight: bold; margin-top: 28px; margin-bottom: 16px; color: #4a6741; line-height: 1.4;",
        "h2": "font-size: 18px; font-weight: bold; margin-top: 22px; margin-bottom: 12px; color: #5b7a50; border-left: 4px solid #8fae82; padding-left: 8px;",
        "h3": "font-size: 16px; font-weight: bold; margin-top: 16px; margin-bottom: 8px; color: #6b8c5e;",
        "p": "font-size: 15px; line-height: 1.8; margin-bottom: 16px; color: #5c5c5c; letter-spacing: 0.3px;",
        "strong": "font-weight: bold; color: #4a6741;",
        "blockquote": "padding: 12px 16px; border-left: 4px solid #8fae82; background-color: #f2f5ef; color: #6b8c5e; font-size: 14px; margin-bottom: 16px;",
        "ul": "margin-bottom: 16px; padding-left: 20px; color: #5c5c5c;",
        "ol": "margin-bottom: 16px; padding-left: 20px; color: #5c5c5c;",
        "li": "font-size: 15px; line-height: 1.8; margin-bottom: 6px;",
        "a": "color: #4a6741; text-decoration: none; border-bottom: 1px solid #8fae82;",
    },
    "黑金奢华": {
        "h1": "font-size: 24px; font-weight: 800; margin-top: 28px; margin-bottom: 16px; color: #d4af37; line-height: 1.35;",
        "h2": "font-size: 19px; font-weight: 700; margin-top: 22px; margin-bottom: 12px; color: #c5a028; border-left: 4px solid #d4af37; padding-left: 10px;",
        "h3": "font-size: 16px; font-weight: 600; margin-top: 16px; margin-bottom: 8px; color: #b8960f;",
        "p": "font-size: 15px; line-height: 1.75; margin-bottom: 16px; color: #d0d0d0; letter-spacing: 0.5px;",
        "strong": "font-weight: bold; color: #d4af37;",
        "blockquote": "padding: 12px 16px; border-left: 4px solid #d4af37; background-color: #1c1c1c; color: #c5a028; font-size: 14px; margin-bottom: 16px;",
        "ul": "margin-bottom: 16px; padding-left: 20px; color: #d0d0d0;",
        "ol": "margin-bottom: 16px; padding-left: 20px; color: #d0d0d0;",
        "li": "font-size: 15px; line-height: 1.75; margin-bottom: 6px;",
        "a": "color: #d4af37; text-decoration: none;",
    },
}

def get_preset_themes() -> dict[str, dict[str, str]]:
    """获取所有预设主题。"""
    return {theme_name: {**DEFAULT_STYLE, **theme_style} for theme_name, theme_style in PRESET_THEMES.items()}

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
