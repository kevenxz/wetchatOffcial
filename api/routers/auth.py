"""Authentication routes."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from api.auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    to_user_public,
    token_expires_in,
)
from api.models import LoginRequest, LoginResponse, UserAccount, UserPublic
from api.store import update_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest) -> LoginResponse:
    user = authenticate_user(body.username, body.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    now = datetime.now(tz=timezone.utc)
    user = update_user(user.user_id, {"last_login_at": now, "updated_at": now})
    token = create_access_token({"sub": user.user_id, "username": user.username, "role": user.role.value})
    return LoginResponse(
        access_token=token,
        expires_in=token_expires_in(),
        user=to_user_public(user),
    )


@router.get("/me", response_model=UserPublic)
async def get_me(current_user: Annotated[UserAccount, Depends(get_current_user)]) -> UserPublic:
    return to_user_public(current_user)
