"""Pydantic 数据模型定义。"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class TaskStatus(str, Enum):
    """任务状态枚举。"""

    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"


class CreateTaskRequest(BaseModel):
    """创建任务请求体。"""

    keywords: str = Field(..., min_length=1, max_length=200, description="搜索关键词")

    @field_validator("keywords")
    @classmethod
    def keywords_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("关键词不能为空或纯空格")
        return v.strip()


class TaskResponse(BaseModel):
    """任务响应体。"""

    task_id: str = Field(..., description="任务唯一 ID")
    keywords: str = Field(..., description="搜索关键词")
    status: TaskStatus = Field(default=TaskStatus.pending, description="任务状态")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: Optional[datetime] = Field(default=None, description="最后更新时间")
    error: Optional[str] = Field(default=None, description="错误信息")
    generated_article: Optional[dict] = Field(default=None, description="生成的文章内容")
    draft_info: Optional[dict] = Field(default=None, description="推送到草稿箱的信息")


class WsMessage(BaseModel):
    """WebSocket 推送消息体。"""

    task_id: str = Field(..., description="任务 ID")
    status: str = Field(..., description="任务状态")
    current_skill: str = Field(default="", description="当前执行的 Skill 节点")
    progress: int = Field(default=0, ge=0, le=100, description="进度百分比")
    message: str = Field(default="", description="可读状态描述")
    result: Optional[Any] = Field(default=None, description="结果数据")
