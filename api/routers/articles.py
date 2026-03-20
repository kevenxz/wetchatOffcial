"""Article management and multi-account push APIs."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from api.models import (
    AccountConfig,
    BatchPushRequest,
    BatchPushResponse,
    PlatformType,
    PushArticleRequest,
    PushOperationResult,
    PushRecord,
    PushStatus,
    TaskResponse,
    UpdateArticleThemeRequest,
)
from api.store import (
    get_account,
    get_custom_themes,
    get_preset_themes,
    get_style_config,
    save_tasks,
    task_store,
)
from workflow.utils.wechat_draft_service import push_article_to_wechat_draft

router = APIRouter(prefix="/articles", tags=["articles"])


def _resolve_accounts(account_ids: list[str]) -> list[AccountConfig]:
    """Resolve and validate push target accounts.

    Only enabled WeChat public accounts are accepted for article push.
    """
    accounts: list[AccountConfig] = []
    for account_id in account_ids:
        account = get_account(account_id)
        if account is None:
            raise HTTPException(status_code=404, detail=f"account {account_id!r} not found")
        if not account.enabled:
            raise HTTPException(status_code=400, detail=f"account {account.name!r} is disabled")
        if account.platform != PlatformType.wechat_mp:
            raise HTTPException(
                status_code=400,
                detail=f"account {account.name!r} is not a WeChat public account",
            )
        accounts.append(account)
    return accounts


def _resolve_theme_config(theme_name: str | None) -> tuple[str, dict[str, str]]:
    """Resolve theme name to concrete style config used for html rendering."""
    normalized_name = (theme_name or "").strip()
    if not normalized_name or normalized_name == "__current__":
        return "__current__", get_style_config()

    preset_themes = get_preset_themes()
    if normalized_name in preset_themes:
        return normalized_name, preset_themes[normalized_name]

    custom_themes = get_custom_themes()
    if normalized_name in custom_themes:
        return normalized_name, custom_themes[normalized_name]

    raise HTTPException(status_code=400, detail=f"theme {normalized_name!r} not found")


async def _push_single(
    task: TaskResponse,
    account: AccountConfig,
    theme_name: str,
    style_config: dict[str, str],
) -> PushOperationResult:
    """Push one article task to one account and append push record."""
    now = datetime.now(tz=timezone.utc)
    try:
        draft_info = await push_article_to_wechat_draft(
            article=task.generated_article or {},
            app_id=account.app_id,
            app_secret=account.app_secret,
            style_config=style_config,
        )
        record = PushRecord(
            push_id=str(uuid.uuid4()),
            account_id=account.account_id,
            account_name=account.name,
            platform=account.platform,
            pushed_at=now,
            status=PushStatus.success,
            draft_info=draft_info,
        )
        task.draft_info = draft_info
        result = PushOperationResult(
            task_id=task.task_id,
            account_id=account.account_id,
            account_name=account.name,
            status=PushStatus.success,
            draft_info=draft_info,
        )
    except Exception as exc:  # noqa: BLE001
        error_msg = str(exc)
        record = PushRecord(
            push_id=str(uuid.uuid4()),
            account_id=account.account_id,
            account_name=account.name,
            platform=account.platform,
            pushed_at=now,
            status=PushStatus.failed,
            error=error_msg,
        )
        result = PushOperationResult(
            task_id=task.task_id,
            account_id=account.account_id,
            account_name=account.name,
            status=PushStatus.failed,
            error=error_msg,
        )

    task.push_records.append(record)
    # Persist the actual theme used in this push for future traceability.
    task.article_theme = theme_name
    task.updated_at = now
    return result


@router.get("", response_model=list[TaskResponse])
async def list_articles() -> list[TaskResponse]:
    """List generated-article tasks only (as article entities)."""
    articles = [task for task in task_store.values() if task.generated_article]
    return sorted(articles, key=lambda item: item.created_at, reverse=True)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_article(task_id: str) -> TaskResponse:
    """Get one article by task id."""
    task = task_store.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"task {task_id!r} not found")
    if not task.generated_article:
        raise HTTPException(status_code=400, detail="task does not have generated article")
    return task


@router.put("/{task_id}/theme", response_model=TaskResponse)
async def update_article_theme(task_id: str, body: UpdateArticleThemeRequest) -> TaskResponse:
    """Update default theme bound to one article."""
    task = task_store.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"task {task_id!r} not found")
    if not task.generated_article:
        raise HTTPException(status_code=400, detail="task does not have generated article")

    theme_name, _ = _resolve_theme_config(body.theme_name)
    task.article_theme = theme_name
    task.updated_at = datetime.now(tz=timezone.utc)
    save_tasks()
    return task


@router.post("/{task_id}/push", response_model=BatchPushResponse)
async def push_article(task_id: str, body: PushArticleRequest) -> BatchPushResponse:
    """Push one article to multiple accounts with selected theme."""
    task = task_store.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"task {task_id!r} not found")
    if not task.generated_article:
        raise HTTPException(status_code=400, detail="task does not have generated article")

    accounts = _resolve_accounts(body.account_ids)
    theme_name, style_config = _resolve_theme_config(body.theme_name or task.article_theme)
    results: list[PushOperationResult] = []
    for account in accounts:
        results.append(await _push_single(task, account, theme_name, style_config))

    save_tasks()
    success = sum(1 for item in results if item.status == PushStatus.success)
    failed = len(results) - success
    return BatchPushResponse(total=len(results), success=success, failed=failed, results=results)


@router.post("/batch-push", response_model=BatchPushResponse)
async def batch_push_articles(body: BatchPushRequest) -> BatchPushResponse:
    """Batch push multiple articles to multiple accounts.

    Theme priority for each task:
    1. `task_themes[task_id]`
    2. `theme_name`
    3. task.article_theme
    """
    accounts = _resolve_accounts(body.account_ids)
    theme_map = body.task_themes or {}
    results: list[PushOperationResult] = []

    for task_id in body.task_ids:
        task = task_store.get(task_id)
        if task is None:
            for account in accounts:
                results.append(
                    PushOperationResult(
                        task_id=task_id,
                        account_id=account.account_id,
                        account_name=account.name,
                        status=PushStatus.failed,
                        error=f"task {task_id!r} not found",
                    )
                )
            continue

        if not task.generated_article:
            for account in accounts:
                results.append(
                    PushOperationResult(
                        task_id=task.task_id,
                        account_id=account.account_id,
                        account_name=account.name,
                        status=PushStatus.failed,
                        error="task does not have generated article",
                    )
                )
            continue

        task_theme = theme_map.get(task.task_id) or body.theme_name or task.article_theme
        # Resolve theme per task so different selected rows can use different styles.
        theme_name, style_config = _resolve_theme_config(task_theme)
        for account in accounts:
            results.append(await _push_single(task, account, theme_name, style_config))

    save_tasks()
    success = sum(1 for item in results if item.status == PushStatus.success)
    failed = len(results) - success
    return BatchPushResponse(total=len(results), success=success, failed=failed, results=results)
