"""Pydantic models used by API routers and storage."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, Field, field_validator, model_validator

from workflow.article_generation import DEFAULT_AUDIENCE_ROLES, DEFAULT_ARTICLE_STRATEGY


def _normalize_unique_strings(values: list[str] | None) -> list[str]:
    items: list[str] = []
    for value in values or []:
        if not isinstance(value, str):
            continue
        cleaned = value.strip()
        if cleaned and cleaned not in items:
            items.append(cleaned)
    return items


def _normalize_tophub_path(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("path cannot be blank")

    if cleaned.startswith(("https://", "http://")):
        parsed = urlsplit(cleaned)
        if parsed.netloc and parsed.netloc != "tophub.today":
            raise ValueError("only tophub.today paths are supported")
        cleaned = urlunsplit(("", "", parsed.path, parsed.query, ""))

    if not cleaned.startswith("/"):
        cleaned = f"/{cleaned.lstrip('/')}"
    if cleaned != "/" and "?" not in cleaned:
        cleaned = cleaned.rstrip("/")
    return cleaned


class TaskStatus(str, Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"


class TopicStatus(str, Enum):
    pending = "pending"
    ignored = "ignored"
    converted = "converted"


class ReviewStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    revision_requested = "revision_requested"


class ReviewTargetType(str, Enum):
    topic = "topic"
    task = "task"
    article = "article"
    workflow_step = "workflow_step"
    custom = "custom"


class WorkflowRunStepStatus(str, Enum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    skipped = "skipped"


class AccountProfileConfig(BaseModel):
    positioning: str = Field(default="", max_length=300)
    target_readers: list[str] = Field(default_factory=list)
    fit_tags: list[str] = Field(default_factory=list)
    avoid_topics: list[str] = Field(default_factory=list)

    @field_validator("target_readers", "fit_tags", "avoid_topics")
    @classmethod
    def normalize_lists(cls, value: list[str]) -> list[str]:
        return _normalize_unique_strings(value)


class ContentTemplateConfig(BaseModel):
    template_id: str = Field(default="auto", max_length=100)
    name: str = Field(default="自动选择", max_length=100)
    preferred_framework: str = Field(default="", max_length=200)
    article_length: Literal["short", "medium", "long"] = "medium"
    tone: str = Field(default="", max_length=200)


class ReviewPolicyConfig(BaseModel):
    strictness: Literal["lenient", "standard", "strict"] = "standard"
    auto_rewrite: bool = True
    require_human_review: bool = False
    block_high_risk: bool = True
    max_revision_rounds: int = Field(default=1, ge=0, le=3)


class WorkflowImagePolicyConfig(BaseModel):
    enabled: bool = True
    cover_enabled: bool = True
    inline_enabled: bool = True
    inline_count: int = Field(default=1, ge=0, le=4)
    style: str = Field(default="", max_length=200)
    brand_colors: list[str] = Field(default_factory=list)
    title_safe_area: bool = True

    @field_validator("brand_colors")
    @classmethod
    def normalize_brand_colors(cls, value: list[str]) -> list[str]:
        return _normalize_unique_strings(value)


class PublishPolicyConfig(BaseModel):
    auto_publish_to_draft: bool = True
    require_manual_confirmation: bool = False


class ResearchPolicyConfig(BaseModel):
    search_mode: Literal["quick", "standard", "deep", "strict"] = "standard"
    auto_deepen_for_sensitive_categories: bool = True
    min_sources: int = Field(default=6, ge=1, le=30)
    min_official_sources: int = Field(default=1, ge=0, le=10)
    min_cross_sources: int = Field(default=3, ge=1, le=20)
    require_opposing_view: bool = True
    freshness_window_days: int = Field(default=7, ge=1, le=365)


class GenerationConfig(BaseModel):
    audience_roles: list[str] = Field(
        default_factory=lambda: list(DEFAULT_AUDIENCE_ROLES),
        description="Target audience roles for article generation",
    )
    article_strategy: Literal["auto", "tech_breakdown", "application_review", "trend_outlook"] = Field(
        default=DEFAULT_ARTICLE_STRATEGY,
        description="Article writing strategy",
    )
    style_hint: str = Field(default="", max_length=500, description="Optional user-provided style hint")
    account_profile: AccountProfileConfig = Field(default_factory=AccountProfileConfig)
    content_template: ContentTemplateConfig = Field(default_factory=ContentTemplateConfig)
    review_policy: ReviewPolicyConfig = Field(default_factory=ReviewPolicyConfig)
    image_policy: WorkflowImagePolicyConfig = Field(default_factory=WorkflowImagePolicyConfig)
    publish_policy: PublishPolicyConfig = Field(default_factory=PublishPolicyConfig)
    research_policy: ResearchPolicyConfig = Field(default_factory=ResearchPolicyConfig)

    @field_validator("audience_roles")
    @classmethod
    def normalize_audience_roles(cls, value: list[str]) -> list[str]:
        roles: list[str] = []
        for role in value:
            cleaned = role.strip()
            if cleaned and cleaned not in roles:
                roles.append(cleaned)
        return roles or list(DEFAULT_AUDIENCE_ROLES)

    @field_validator("style_hint")
    @classmethod
    def normalize_style_hint(cls, value: str) -> str:
        return value.strip()


class TextModelConfig(BaseModel):
    api_key: str = Field(default="", description="API key for text generation")
    base_url: Optional[str] = Field(default=None, description="Base URL for text generation")
    model: str = Field(default="gpt-4o", min_length=1, max_length=200, description="Model name for text generation")

    @field_validator("api_key")
    @classmethod
    def strip_text_api_key(cls, value: str) -> str:
        return value.strip()

    @field_validator("model")
    @classmethod
    def strip_required_text_model(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("model cannot be blank")
        return cleaned

    @field_validator("base_url")
    @classmethod
    def normalize_base_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ImageModelConfig(BaseModel):
    enabled: bool = Field(default=False, description="Whether image generation is enabled")
    api_key: str = Field(default="", description="API key for image generation")
    base_url: Optional[str] = Field(default=None, description="Base URL for image generation")
    model: str = Field(default="dall-e-3", min_length=1, max_length=200, description="Model name for image generation")

    @field_validator("api_key")
    @classmethod
    def strip_image_api_key(cls, value: str) -> str:
        return value.strip()

    @field_validator("model")
    @classmethod
    def strip_image_model(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("model cannot be blank")
        return cleaned

    @field_validator("base_url")
    @classmethod
    def normalize_image_base_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ModelConfig(BaseModel):
    text: TextModelConfig = Field(default_factory=TextModelConfig)
    image: ImageModelConfig = Field(default_factory=ImageModelConfig)


class CreateTaskRequest(BaseModel):
    keywords: str = Field(..., min_length=1, max_length=200, description="Search keywords")
    generation_config: GenerationConfig = Field(default_factory=lambda: GenerationConfig())
    hotspot_capture_config: Optional[dict] = Field(default=None, description="Optional per-task hotspot capture config")

    @field_validator("keywords")
    @classmethod
    def keywords_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("keywords cannot be blank")
        return value.strip()


class TopicCandidate(BaseModel):
    topic_id: str = Field(..., description="Topic candidate id")
    title: str = Field(..., min_length=1, max_length=200)
    summary: str = Field(default="", max_length=2000)
    source: str = Field(default="", max_length=100)
    url: Optional[str] = Field(default=None, max_length=500)
    score: Optional[float] = Field(default=None, ge=0, le=100)
    tags: list[str] = Field(default_factory=list)
    status: TopicStatus = Field(default=TopicStatus.pending)
    task_id: Optional[str] = Field(default=None, description="Converted task id")
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: Optional[datetime] = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("title cannot be blank")
        return cleaned

    @field_validator("summary", "source")
    @classmethod
    def strip_optional_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("url")
    @classmethod
    def normalize_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        return _normalize_unique_strings(value)


class CreateTopicCandidateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    summary: str = Field(default="", max_length=2000)
    source: str = Field(default="", max_length=100)
    url: Optional[str] = Field(default=None, max_length=500)
    score: Optional[float] = Field(default=None, ge=0, le=100)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("title cannot be blank")
        return cleaned

    @field_validator("summary", "source")
    @classmethod
    def strip_optional_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("url")
    @classmethod
    def normalize_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        return _normalize_unique_strings(value)


class UpdateTopicCandidateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    summary: Optional[str] = Field(default=None, max_length=2000)
    source: Optional[str] = Field(default=None, max_length=100)
    url: Optional[str] = Field(default=None, max_length=500)
    score: Optional[float] = Field(default=None, ge=0, le=100)
    tags: Optional[list[str]] = None
    metadata: Optional[dict[str, Any]] = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("title cannot be blank")
        return cleaned

    @field_validator("summary", "source", "url")
    @classmethod
    def strip_optional_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: Optional[list[str]]) -> Optional[list[str]]:
        if value is None:
            return None
        return _normalize_unique_strings(value)


class ConvertTopicToTaskRequest(BaseModel):
    generation_config: GenerationConfig = Field(default_factory=lambda: GenerationConfig())
    hotspot_capture_config: Optional[dict] = None


class ReviewQueueItem(BaseModel):
    review_id: str = Field(..., description="Review queue item id")
    target_type: ReviewTargetType = Field(default=ReviewTargetType.custom)
    target_id: str = Field(..., min_length=1, max_length=200)
    title: str = Field(..., min_length=1, max_length=200)
    payload: dict[str, Any] = Field(default_factory=dict)
    status: ReviewStatus = Field(default=ReviewStatus.pending)
    decision: Optional[ReviewStatus] = None
    comment: Optional[str] = Field(default=None, max_length=2000)
    reviewer_id: Optional[str] = Field(default=None, max_length=100)
    created_at: datetime
    updated_at: Optional[datetime] = None
    decided_at: Optional[datetime] = None

    @field_validator("target_id", "title")
    @classmethod
    def not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("field cannot be blank")
        return cleaned

    @field_validator("comment", "reviewer_id")
    @classmethod
    def strip_nullable_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class CreateReviewQueueItemRequest(BaseModel):
    target_type: ReviewTargetType = Field(default=ReviewTargetType.custom)
    target_id: str = Field(..., min_length=1, max_length=200)
    title: str = Field(..., min_length=1, max_length=200)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("target_id", "title")
    @classmethod
    def not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("field cannot be blank")
        return cleaned


class ReviewDecisionRequest(BaseModel):
    comment: Optional[str] = Field(default=None, max_length=2000)
    reviewer_id: Optional[str] = Field(default=None, max_length=100)

    @field_validator("comment", "reviewer_id")
    @classmethod
    def strip_nullable_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class WorkflowRunStepRecord(BaseModel):
    run_step_id: str = Field(..., description="Workflow run step record id")
    run_id: Optional[str] = Field(default=None, max_length=100)
    task_id: Optional[str] = Field(default=None, max_length=100)
    step_name: str = Field(..., min_length=1, max_length=100)
    status: WorkflowRunStepStatus = Field(default=WorkflowRunStepStatus.pending)
    payload: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = Field(default=None, max_length=2000)
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    @field_validator("step_name")
    @classmethod
    def normalize_step_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("step_name cannot be blank")
        return cleaned

    @field_validator("run_id", "task_id", "error")
    @classmethod
    def strip_nullable_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class CreateWorkflowRunStepRequest(BaseModel):
    run_id: Optional[str] = Field(default=None, max_length=100)
    task_id: Optional[str] = Field(default=None, max_length=100)
    step_name: str = Field(..., min_length=1, max_length=100)
    status: WorkflowRunStepStatus = Field(default=WorkflowRunStepStatus.pending)
    payload: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = Field(default=None, max_length=2000)
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None

    @field_validator("step_name")
    @classmethod
    def normalize_step_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("step_name cannot be blank")
        return cleaned

    @field_validator("run_id", "task_id", "error")
    @classmethod
    def strip_nullable_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class UpdateWorkflowRunStepRequest(BaseModel):
    run_id: Optional[str] = Field(default=None, max_length=100)
    task_id: Optional[str] = Field(default=None, max_length=100)
    step_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    status: Optional[WorkflowRunStepStatus] = None
    payload: Optional[dict[str, Any]] = None
    error: Optional[str] = Field(default=None, max_length=2000)
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None

    @field_validator("step_name")
    @classmethod
    def normalize_step_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("step_name cannot be blank")
        return cleaned

    @field_validator("run_id", "task_id", "error")
    @classmethod
    def strip_nullable_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


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


class UserRole(str, Enum):
    admin = "admin"
    operator = "operator"


class UserAccount(BaseModel):
    user_id: str = Field(..., description="User id")
    username: str = Field(..., min_length=3, max_length=50, description="Username")
    password_hash: str = Field(..., min_length=1, max_length=500, description="Password hash")
    display_name: str = Field(..., min_length=1, max_length=100, description="Display name")
    role: UserRole = Field(default=UserRole.operator, description="Role")
    enabled: bool = Field(default=True, description="Whether enabled")
    created_at: datetime = Field(..., description="Created at")
    updated_at: Optional[datetime] = Field(default=None, description="Updated at")
    last_login_at: Optional[datetime] = Field(default=None, description="Last login at")

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not cleaned:
            raise ValueError("username cannot be blank")
        return cleaned

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("display_name cannot be blank")
        return cleaned


class UserPublic(BaseModel):
    user_id: str
    username: str
    display_name: str
    role: UserRole
    enabled: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=200)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not cleaned:
            raise ValueError("username cannot be blank")
        return cleaned

    @field_validator("password")
    @classmethod
    def normalize_password(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("password cannot be blank")
        return cleaned


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(..., ge=1)
    user: UserPublic


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=200)
    display_name: str = Field(..., min_length=1, max_length=100)
    role: UserRole = Field(default=UserRole.operator)
    enabled: bool = Field(default=True)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not cleaned:
            raise ValueError("username cannot be blank")
        return cleaned

    @field_validator("password")
    @classmethod
    def normalize_password(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 8:
            raise ValueError("password must be at least 8 characters")
        return cleaned

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("display_name cannot be blank")
        return cleaned


class UpdateUserRequest(BaseModel):
    display_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    role: Optional[UserRole] = None
    enabled: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=8, max_length=200)

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("display_name cannot be blank")
        return cleaned

    @field_validator("password")
    @classmethod
    def normalize_password(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        if len(cleaned) < 8:
            raise ValueError("password must be at least 8 characters")
        return cleaned


class TaskResponse(BaseModel):
    task_id: str = Field(..., description="Task id")
    mode: Optional[str] = Field(default=None, description="Workflow mode")
    keywords: str = Field(..., description="Search keywords")
    original_keywords: Optional[str] = Field(default=None, description="Original keywords before hotspot capture")
    generation_config: GenerationConfig = Field(default_factory=lambda: GenerationConfig(), description="Generation config")
    status: TaskStatus = Field(default=TaskStatus.pending, description="Task status")
    created_at: datetime = Field(..., description="Created at")
    updated_at: Optional[datetime] = Field(default=None, description="Updated at")
    error: Optional[str] = Field(default=None, description="Error message")
    task_brief: Optional[dict] = Field(default=None, description="Normalized task brief")
    config_snapshot: Optional[dict] = Field(default=None, description="Workflow config snapshot")
    planning_state: Optional[dict] = Field(default=None, description="Planner output and thresholds")
    research_state: Optional[dict] = Field(default=None, description="Research artifacts and evidence pack")
    writing_state: Optional[dict] = Field(default=None, description="Draft and review state")
    visual_state: Optional[dict] = Field(default=None, description="Visual briefs and generated assets")
    quality_state: Optional[dict] = Field(default=None, description="Quality reviews and next action")
    quality_report: Optional[dict] = Field(default=None, description="Unified quality summary report")
    user_intent: Optional[dict] = Field(default=None, description="Resolved user intent from LangGraph")
    style_profile: Optional[dict] = Field(default=None, description="Auto-generated writing style profile")
    article_blueprint: Optional[dict] = Field(default=None, description="Resolved article blueprint")
    article_plan: Optional[dict] = Field(default=None, description="Resolved article plan from LangGraph")
    outline_result: Optional[dict] = Field(default=None, description="AI-generated article outline")
    generated_article: Optional[dict] = Field(default=None, description="Generated article")
    draft_info: Optional[dict] = Field(default=None, description="Latest draft push result")
    hotspot_capture_config: Optional[dict] = Field(default=None, description="Resolved hotspot capture config")
    hotspot_candidates: list[dict] = Field(default_factory=list, description="Scored hotspot candidates")
    selected_hotspot: Optional[dict] = Field(default=None, description="Selected hotspot item")
    selected_topic: Optional[dict] = Field(default=None, description="Selected article topic")
    hotspot_capture_error: Optional[str] = Field(default=None, description="Hotspot capture fallback or error reason")
    human_review_required: bool = Field(default=False, description="Whether manual review is required before publish")
    article_theme: Optional[str] = Field(default=None, description="Theme name for this article push")
    final_article: Optional[dict] = Field(default=None, description="Final assembled article package")
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


class HotspotSource(str, Enum):
    tophub = "tophub"
    ranking_page = "ranking_page"
    rss_or_feed = "rss_or_feed"


class HotspotFilters(BaseModel):
    top_n_per_platform: int = Field(default=10, ge=1, le=50)
    min_selection_score: float = Field(default=60, ge=0, le=100)
    exclude_keywords: list[str] = Field(default_factory=list)
    prefer_keywords: list[str] = Field(default_factory=list)

    @field_validator("exclude_keywords", "prefer_keywords")
    @classmethod
    def normalize_keyword_lists(cls, value: list[str]) -> list[str]:
        return _normalize_unique_strings(value)


class HotspotPlatformConfig(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    path: str = Field(..., min_length=1, max_length=500)
    source: HotspotSource = Field(default=HotspotSource.tophub)
    provider_id: str = Field(default="", max_length=100)
    category: str = Field(default="", max_length=100)
    weight: float = Field(default=1.0, gt=0, le=10)
    enabled: bool = Field(default=True)
    parser_options: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name cannot be blank")
        return cleaned

    @field_validator("path")
    @classmethod
    def normalize_path(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("path cannot be blank")
        return cleaned

    @model_validator(mode="before")
    @classmethod
    def hydrate_endpoint_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        payload = dict(data)
        if not payload.get("path"):
            payload["path"] = payload.get("url") or payload.get("feed_url") or ""
        if not payload.get("source") and str(payload.get("path") or "").startswith(("http://", "https://")):
            endpoint = str(payload.get("path") or "")
            parsed = urlsplit(endpoint)
            endpoint_lower = endpoint.lower()
            if parsed.netloc == "tophub.today":
                payload["source"] = "tophub"
            else:
                payload["source"] = "rss_or_feed" if "rss" in endpoint_lower or "feed" in endpoint_lower else "ranking_page"
        return payload

    @model_validator(mode="after")
    def normalize_platform(self) -> HotspotPlatformConfig:
        if self.source == HotspotSource.tophub:
            self.path = _normalize_tophub_path(self.path)
        self.provider_id = self.provider_id.strip() or self.source.value
        self.category = self.category.strip()
        return self


class HotspotCaptureConfig(BaseModel):
    enabled: bool = Field(default=False)
    source: HotspotSource = Field(default=HotspotSource.tophub)
    categories: list[str] = Field(default_factory=list)
    platforms: list[HotspotPlatformConfig] = Field(default_factory=list)
    filters: HotspotFilters = Field(default_factory=HotspotFilters)
    fallback_topics: list[str] = Field(default_factory=list)

    @field_validator("categories", "fallback_topics")
    @classmethod
    def normalize_string_lists(cls, value: list[str]) -> list[str]:
        return _normalize_unique_strings(value)


class HotspotPlatformCatalogItem(HotspotPlatformConfig):
    @field_validator("category")
    @classmethod
    def normalize_category(cls, value: str) -> str:
        return value.strip()


class HotspotPlatformCatalogResponse(BaseModel):
    items: list[HotspotPlatformCatalogItem] = Field(default_factory=list)
    updated_at: datetime
    source: HotspotSource = Field(default=HotspotSource.tophub)


class HotspotPreviewRequest(BaseModel):
    keywords: str = Field(default="热点预览", min_length=1, max_length=200)
    hotspot_capture: HotspotCaptureConfig = Field(default_factory=HotspotCaptureConfig)

    @field_validator("keywords")
    @classmethod
    def keywords_not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("keywords cannot be blank")
        return cleaned


class HotspotPreviewResponse(BaseModel):
    keywords: str
    original_keywords: str
    hotspot_capture_config: dict
    hotspot_candidates: list[dict] = Field(default_factory=list)
    selected_hotspot: Optional[dict] = None
    hotspot_capture_error: Optional[str] = None


class HotspotMonitorItem(BaseModel):
    topic_id: str
    title: str
    summary: str = ""
    source: str = ""
    url: Optional[str] = None
    category: str = ""
    tags: list[str] = Field(default_factory=list)
    status: TopicStatus = Field(default=TopicStatus.pending)
    task_id: Optional[str] = None
    hot_score: int = Field(default=0, ge=0, le=100)
    account_fit_score: int = Field(default=0, ge=0, le=100)
    risk_score: int = Field(default=0, ge=0, le=100)
    channel_count: int = Field(default=1, ge=0)
    recommended: bool = False
    captured_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class HotspotMonitorStats(BaseModel):
    total: int = 0
    recommended: int = 0
    high_risk: int = 0
    source_count: int = 0
    latest_captured_at: Optional[datetime] = None


class HotspotMonitorResponse(BaseModel):
    items: list[HotspotMonitorItem] = Field(default_factory=list)
    stats: HotspotMonitorStats = Field(default_factory=HotspotMonitorStats)
    updated_at: datetime
    capture_error: Optional[str] = None


class HotspotMonitorCaptureRequest(BaseModel):
    keywords: str = Field(default="热点监控", min_length=1, max_length=200)
    hotspot_capture: HotspotCaptureConfig = Field(default_factory=HotspotCaptureConfig)

    @field_validator("keywords")
    @classmethod
    def keywords_not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("keywords cannot be blank")
        return cleaned


class ScheduleConfig(BaseModel):
    schedule_id: str
    name: str = Field(..., min_length=1, max_length=100)
    mode: ScheduleMode
    run_at: Optional[datetime] = None
    interval_minutes: Optional[int] = Field(default=None, ge=1, le=10080)
    theme_name: str = Field(default="__current__", min_length=1, max_length=100)
    account_ids: list[str] = Field(default_factory=list)
    hot_topics: list[str] = Field(default_factory=list)
    hotspot_capture: HotspotCaptureConfig = Field(default_factory=HotspotCaptureConfig)
    generation_config: GenerationConfig = Field(default_factory=lambda: GenerationConfig())
    status: ScheduleStatus = Field(default=ScheduleStatus.stopped)
    enabled: bool = Field(default=True)
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    last_error: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    @model_validator(mode="before")
    @classmethod
    def hydrate_hotspot_capture(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        payload = dict(data)
        legacy_hot_topics = _normalize_unique_strings(payload.get("hot_topics"))
        hotspot_capture = payload.get("hotspot_capture")

        if hotspot_capture is None:
            payload["hotspot_capture"] = {"fallback_topics": legacy_hot_topics}
        elif isinstance(hotspot_capture, dict):
            next_hotspot_capture = dict(hotspot_capture)
            if not next_hotspot_capture.get("fallback_topics") and legacy_hot_topics:
                next_hotspot_capture["fallback_topics"] = legacy_hot_topics
            payload["hotspot_capture"] = next_hotspot_capture
        return payload

    @model_validator(mode="after")
    def sync_legacy_hot_topics(self) -> ScheduleConfig:
        self.account_ids = _normalize_unique_strings(self.account_ids)
        self.hot_topics = list(self.hotspot_capture.fallback_topics)
        return self


class CreateScheduleRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    mode: ScheduleMode
    run_at: Optional[datetime] = None
    interval_minutes: Optional[int] = Field(default=None, ge=1, le=10080)
    theme_name: str = Field(default="__current__", min_length=1, max_length=100)
    account_ids: list[str] = Field(default_factory=list)
    hot_topics: list[str] = Field(default_factory=list)
    hotspot_capture: HotspotCaptureConfig = Field(default_factory=HotspotCaptureConfig)
    generation_config: GenerationConfig = Field(default_factory=lambda: GenerationConfig())
    enabled: bool = Field(default=True)

    @model_validator(mode="before")
    @classmethod
    def hydrate_hotspot_capture(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        payload = dict(data)
        legacy_hot_topics = _normalize_unique_strings(payload.get("hot_topics"))
        hotspot_capture = payload.get("hotspot_capture")

        if hotspot_capture is None:
            payload["hotspot_capture"] = {"fallback_topics": legacy_hot_topics}
        elif isinstance(hotspot_capture, dict):
            next_hotspot_capture = dict(hotspot_capture)
            if not next_hotspot_capture.get("fallback_topics") and legacy_hot_topics:
                next_hotspot_capture["fallback_topics"] = legacy_hot_topics
            payload["hotspot_capture"] = next_hotspot_capture
        return payload

    @model_validator(mode="after")
    def sync_legacy_hot_topics(self) -> CreateScheduleRequest:
        self.account_ids = _normalize_unique_strings(self.account_ids)
        self.hot_topics = list(self.hotspot_capture.fallback_topics)
        return self


class UpdateScheduleRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    mode: Optional[ScheduleMode] = None
    run_at: Optional[datetime] = None
    interval_minutes: Optional[int] = Field(default=None, ge=1, le=10080)
    theme_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    account_ids: Optional[list[str]] = None
    hot_topics: Optional[list[str]] = None
    hotspot_capture: Optional[HotspotCaptureConfig] = None
    generation_config: Optional[GenerationConfig] = None
    enabled: Optional[bool] = None

    @model_validator(mode="before")
    @classmethod
    def hydrate_hotspot_capture(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        payload = dict(data)
        legacy_hot_topics = (
            _normalize_unique_strings(payload.get("hot_topics"))
            if "hot_topics" in payload
            else None
        )
        hotspot_capture = payload.get("hotspot_capture")

        if hotspot_capture is None and legacy_hot_topics is not None:
            payload["hotspot_capture"] = {"fallback_topics": legacy_hot_topics}
        elif isinstance(hotspot_capture, dict):
            next_hotspot_capture = dict(hotspot_capture)
            if not next_hotspot_capture.get("fallback_topics") and legacy_hot_topics:
                next_hotspot_capture["fallback_topics"] = legacy_hot_topics
            payload["hotspot_capture"] = next_hotspot_capture
        return payload

    @model_validator(mode="after")
    def sync_legacy_hot_topics(self) -> UpdateScheduleRequest:
        if self.account_ids is not None:
            self.account_ids = _normalize_unique_strings(self.account_ids)
        if self.hotspot_capture is not None:
            self.hot_topics = list(self.hotspot_capture.fallback_topics)
        elif self.hot_topics is not None:
            self.hot_topics = _normalize_unique_strings(self.hot_topics)
        return self


class ScheduleExecuteResponse(BaseModel):
    message: str
    task_id: Optional[str] = None
