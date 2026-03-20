"""账号配置管理路由。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

import httpx
import structlog
from fastapi import APIRouter, HTTPException, Path

from api.models import (
    AccountConfig,
    CreateAccountRequest,
    TestConnectionResponse,
    UpdateAccountRequest,
)
from api.store import (
    create_account,
    delete_account,
    get_account,
    list_accounts,
    update_account,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountConfig])
async def get_accounts() -> list[AccountConfig]:
    """获取所有账号配置列表。"""
    return list_accounts()


@router.post("", response_model=AccountConfig, status_code=201)
async def add_account(body: CreateAccountRequest) -> AccountConfig:
    """新增账号配置。"""
    account = AccountConfig(
        account_id=str(uuid.uuid4()),
        name=body.name,
        platform=body.platform,
        app_id=body.app_id,
        app_secret=body.app_secret,
        enabled=body.enabled,
        created_at=datetime.now(tz=timezone.utc),
    )
    result = create_account(account)
    logger.info("account_created", account_id=result.account_id, platform=result.platform)
    return result


@router.get("/{account_id}", response_model=AccountConfig)
async def get_account_detail(
    account_id: Annotated[str, Path(description="账号 ID")],
) -> AccountConfig:
    """获取单个账号详情。"""
    account = get_account(account_id)
    if account is None:
        raise HTTPException(status_code=404, detail=f"账号 {account_id!r} 不存在")
    return account


@router.put("/{account_id}", response_model=AccountConfig)
async def update_account_config(
    account_id: Annotated[str, Path(description="账号 ID")],
    body: UpdateAccountRequest,
) -> AccountConfig:
    """更新账号配置（差量更新）。"""
    patch = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    patch["updated_at"] = datetime.now(tz=timezone.utc)
    try:
        result = update_account(account_id, patch)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    logger.info("account_updated", account_id=account_id, fields=list(patch.keys()))
    return result


@router.delete("/{account_id}", status_code=204, response_model=None)
async def remove_account(
    account_id: Annotated[str, Path(description="账号 ID")],
) -> None:
    """删除账号配置。"""
    try:
        delete_account(account_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    logger.info("account_deleted", account_id=account_id)


@router.post("/{account_id}/test", response_model=TestConnectionResponse)
async def test_account_connection(
    account_id: Annotated[str, Path(description="账号 ID")],
) -> TestConnectionResponse:
    """测试账号连接（目前支持微信公众号）。"""
    account = get_account(account_id)
    if account is None:
        raise HTTPException(status_code=404, detail=f"账号 {account_id!r} 不存在")

    if account.platform.value == "wechat_mp":
        return await _test_wechat_connection(account)

    return TestConnectionResponse(success=False, message=f"平台 {account.platform.value} 暂不支持连接测试")


async def _test_wechat_connection(account: AccountConfig) -> TestConnectionResponse:
    """调用微信 access_token 接口验证凭证。"""
    url = (
        "https://api.weixin.qq.com/cgi-bin/token"
        f"?grant_type=client_credential"
        f"&appid={account.app_id}"
        f"&secret={account.app_secret}"
    )
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            data = response.json()

        if "access_token" in data:
            logger.info("account_test_success", account_id=account.account_id)
            return TestConnectionResponse(success=True, message="连接成功，凭证有效")
        else:
            errcode = data.get("errcode", "未知")
            errmsg = data.get("errmsg", "未知错误")
            logger.warning("account_test_failed", account_id=account.account_id, errcode=errcode)
            return TestConnectionResponse(success=False, message=f"验证失败：[{errcode}] {errmsg}")

    except Exception as exc:
        logger.exception("account_test_error", account_id=account.account_id, error=str(exc))
        return TestConnectionResponse(success=False, message=f"网络请求失败：{exc}")
