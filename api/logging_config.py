"""structlog 日志配置：JSON 格式输出到 logs/ 目录与控制台。"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import structlog


def setup_logging() -> None:
    """初始化 structlog 配置。

    - 开发环境：控制台输出人类可读格式
    - 所有环境：JSON 格式写入 logs/app.log
    """
    log_dir = Path(__file__).resolve().parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "app.log"

    # 标准库 logging 配置 —— structlog 桥接
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        level=logging.DEBUG,
        handlers=[file_handler, console_handler],
        force=True,
    )

    # 是否开发环境（默认 True）
    is_dev = os.getenv("ENV", "dev").lower() in ("dev", "development")

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if is_dev:
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer(ensure_ascii=False)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # 为 file_handler 使用 JSON 格式
    json_formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
    )
    file_handler.setFormatter(json_formatter)

    # 为 console_handler 使用可读格式
    console_formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    console_handler.setFormatter(console_formatter)
