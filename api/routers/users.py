"""System user management routes."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status

from api.auth import get_current_user, hash_password, require_admin, to_user_public
from api.models import CreateUserRequest, UpdateUserRequest, UserAccount, UserPublic
from api.store import create_user, delete_user, list_users, update_user

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserPublic])
async def get_users(_: Annotated[UserAccount, Depends(require_admin)]) -> list[UserPublic]:
    return [to_user_public(user) for user in list_users()]


@router.post("", response_model=UserPublic, status_code=201)
async def add_user(
    body: CreateUserRequest,
    _: Annotated[UserAccount, Depends(require_admin)],
) -> UserPublic:
    now = datetime.now(tz=timezone.utc)
    user = UserAccount(
        user_id=str(uuid.uuid4()),
        username=body.username,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        role=body.role,
        enabled=body.enabled,
        created_at=now,
    )
    try:
        created = create_user(user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return to_user_public(created)


@router.put("/{user_id}", response_model=UserPublic)
async def edit_user(
    user_id: Annotated[str, Path(description="用户 ID")],
    body: UpdateUserRequest,
    admin_user: Annotated[UserAccount, Depends(get_current_user)],
) -> UserPublic:
    if admin_user.role.value != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅管理员可执行此操作")

    if admin_user.user_id == user_id and body.enabled is False:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能禁用当前登录账号")

    patch = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if "password" in patch:
        patch["password_hash"] = hash_password(patch.pop("password"))
    patch["updated_at"] = datetime.now(tz=timezone.utc)

    try:
        updated = update_user(user_id, patch)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return to_user_public(updated)


@router.delete("/{user_id}", status_code=204, response_model=None)
async def remove_user(
    user_id: Annotated[str, Path(description="用户 ID")],
    admin_user: Annotated[UserAccount, Depends(require_admin)],
) -> None:
    if admin_user.user_id == user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能删除当前登录账号")

    try:
        delete_user(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
