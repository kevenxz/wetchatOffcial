"""Pydantic models used by API routers and storage."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class TaskStatus(str, Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"


class CreateTaskRequest(BaseModel):
    keywords: str = Field(..., min_length=1, max_length=200, description="Search keywords")

    @field_validator("keywords")
    @classmethod
    def keywords_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("keywords cannot be blank")
        return value.strip()


class PlatformType(str, Enum):
    wechat_mp = "wechat_mp"
    toutiao = "toutiao"


class PushStatus(str, Enum):
    success = "success"
    failed = "failed"


class PushRecord(BaseModel):
    push_id: str = Field(..., description="Push record id")
    account_id: str = Field(..., description="Target account id")
    account_name: str = Field(..., description="Target account name")
    platform: PlatformType = Field(..., description="Target platform")
    pushed_at: datetime = Field(..., description="Push timestamp")
    status: PushStatus = Field(..., description="Push result")
    draft_info: Optional[dict] = Field(default=None, description="Draft response payload")
    error: Optional[str] = Field(default=None, description="Failure reason")


class TaskResponse(BaseModel):
    task_id: str = Field(..., description="Task id")
    keywords: str = Field(..., description="Search keywords")
    status: TaskStatus = Field(default=TaskStatus.pending, description="Task status")
    created_at: datetime = Field(..., description="Created at")
    updated_at: Optional[datetime] = Field(default=None, description="Updated at")
    error: Optional[str] = Field(default=None, description="Error message")
    generated_article: Optional[dict] = Field(default=None, description="Generated article")
    draft_info: Optional[dict] = Field(default=None, description="Latest draft push result")
    article_theme: Optional[str] = Field(default=None, description="Theme name for this article push")
    push_records: list[PushRecord] = Field(default_factory=list, description="All push records")


class WsMessage(BaseModel):
    task_id: str = Field(..., description="Task id")
    status: str = Field(..., description="Task status")
    current_skill: str = Field(default="", description="Current workflow skill")
    progress: int = Field(default=0, ge=0, le=100, description="Progress 0-100")
    message: str = Field(default="", description="Status message")
    result: Optional[Any] = Field(default=None, description="Workflow result payload")


class AccountConfig(BaseModel):
    account_id: str = Field(..., description="Account id")
    name: str = Field(..., min_length=1, max_length=100, description="Display name")
    platform: PlatformType = Field(..., description="Platform")
    app_id: str = Field(..., min_length=1, max_length=200, description="App id")
    app_secret: str = Field(..., min_length=1, max_length=200, description="App secret")
    enabled: bool = Field(default=True, description="Whether enabled")
    created_at: datetime = Field(..., description="Created at")
    updated_at: Optional[datetime] = Field(default=None, description="Updated at")


class CreateAccountRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    platform: PlatformType
    app_id: str = Field(..., min_length=1, max_length=200)
    app_secret: str = Field(..., min_length=1, max_length=200)
    enabled: bool = Field(default=True)

    @field_validator("name", "app_id", "app_secret")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field cannot be blank")
        return value.strip()


class UpdateAccountRequest(BaseModel):
    name: Optional[str] = None
    platform: Optional[PlatformType] = None
    app_id: Optional[str] = None
    app_secret: Optional[str] = None
    enabled: Optional[bool] = None


class TestConnectionResponse(BaseModel):
    success: bool
    message: str


class PushArticleRequest(BaseModel):
    account_ids: list[str] = Field(..., min_length=1, description="Target account ids")
    theme_name: Optional[str] = Field(default=None, description="Theme name")


class BatchPushRequest(BaseModel):
    task_ids: list[str] = Field(..., min_length=1, description="Target article task ids")
    account_ids: list[str] = Field(..., min_length=1, description="Target account ids")
    theme_name: Optional[str] = Field(default=None, description="Theme name for all tasks")
    task_themes: Optional[dict[str, str]] = Field(
        default=None,
        description="Per-task theme map; key is task_id, value is theme name",
    )


class UpdateArticleThemeRequest(BaseModel):
    theme_name: str = Field(..., min_length=1, max_length=100, description="Theme name")


class PushOperationResult(BaseModel):
    task_id: str
    account_id: str
    account_name: str
    status: PushStatus
    draft_info: Optional[dict] = None
    error: Optional[str] = None


class BatchPushResponse(BaseModel):
    total: int
    success: int
    failed: int
    results: list[PushOperationResult]


class ScheduleMode(str, Enum):
    once = "once"
    interval = "interval"


class ScheduleStatus(str, Enum):
    running = "running"
    stopped = "stopped"


class ScheduleConfig(BaseModel):
    schedule_id: str
    name: str = Field(..., min_length=1, max_length=100)
    mode: ScheduleMode
    run_at: Optional[datetime] = None
    interval_minutes: Optional[int] = Field(default=None, ge=1, le=10080)
    theme_name: str = Field(default="__current__", min_length=1, max_length=100)
    account_ids: list[str] = Field(default_factory=list)
    hot_topics: list[str] = Field(default_factory=list)
    status: ScheduleStatus = Field(default=ScheduleStatus.stopped)
    enabled: bool = Field(default=True)
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    last_error: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class CreateScheduleRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    mode: ScheduleMode
    run_at: Optional[datetime] = None
    interval_minutes: Optional[int] = Field(default=None, ge=1, le=10080)
    theme_name: str = Field(default="__current__", min_length=1, max_length=100)
    account_ids: list[str] = Field(default_factory=list)
    hot_topics: list[str] = Field(default_factory=list)
    enabled: bool = Field(default=True)


class UpdateScheduleRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    mode: Optional[ScheduleMode] = None
    run_at: Optional[datetime] = None
    interval_minutes: Optional[int] = Field(default=None, ge=1, le=10080)
    theme_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    account_ids: Optional[list[str]] = None
    hot_topics: Optional[list[str]] = None
    enabled: Optional[bool] = None


class ScheduleExecuteResponse(BaseModel):
    message: str
    task_id: Optional[str] = None
