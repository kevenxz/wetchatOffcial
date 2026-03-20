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


class PlatformType(str, Enum):
    """平台类型枚举。"""

    wechat_mp = "wechat_mp"  # 微信公众号
    toutiao = "toutiao"  # 头条号


class AccountConfig(BaseModel):
    """账号配置数据模型。"""

    account_id: str = Field(..., description="账号唯一 ID")
    name: str = Field(..., min_length=1, max_length=100, description="显示名称")
    platform: PlatformType = Field(..., description="平台类型")
    app_id: str = Field(..., min_length=1, max_length=200, description="AppID")
    app_secret: str = Field(..., min_length=1, max_length=200, description="AppSecret")
    enabled: bool = Field(default=True, description="是否启用")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: Optional[datetime] = Field(default=None, description="最后更新时间")


class CreateAccountRequest(BaseModel):
    """创建账号请求体。"""

    name: str = Field(..., min_length=1, max_length=100)
    platform: PlatformType
    app_id: str = Field(..., min_length=1, max_length=200)
    app_secret: str = Field(..., min_length=1, max_length=200)
    enabled: bool = Field(default=True)

    @field_validator("name", "app_id", "app_secret")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("字段不能为空或纯空格")
        return v.strip()


class UpdateAccountRequest(BaseModel):
    """更新账号请求体（所有字段可选）。"""

    name: Optional[str] = None
    platform: Optional[PlatformType] = None
    app_id: Optional[str] = None
    app_secret: Optional[str] = None
    enabled: Optional[bool] = None


class TestConnectionResponse(BaseModel):
    """测试连接响应体。"""

    success: bool
    message: str
