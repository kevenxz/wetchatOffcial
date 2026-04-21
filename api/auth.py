"""Authentication helpers and dependencies."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.models import UserAccount, UserPublic, UserRole
from api.store import create_user, get_user, get_user_by_username, list_users

logger = logging.getLogger(__name__)

_PASSWORD_HASH_ALGO = "pbkdf2_sha256"
_DEFAULT_PASSWORD_ITERATIONS = 120_000
_DEFAULT_TOKEN_EXPIRE_SECONDS = 24 * 60 * 60
_DEFAULT_AUTH_SECRET = "change-me-in-production"

bearer_scheme = HTTPBearer(auto_error=False)


def _urlsafe_b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _urlsafe_b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")


def _auth_secret_key() -> str:
    return (os.getenv("AUTH_SECRET_KEY") or _DEFAULT_AUTH_SECRET).strip() or _DEFAULT_AUTH_SECRET


def _password_iterations() -> int:
    raw = (os.getenv("AUTH_PASSWORD_ITERATIONS") or "").strip()
    if not raw:
        return _DEFAULT_PASSWORD_ITERATIONS
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_PASSWORD_ITERATIONS
    return max(10_000, value)


def token_expires_in() -> int:
    raw = (os.getenv("AUTH_TOKEN_EXPIRE_SECONDS") or "").strip()
    if not raw:
        return _DEFAULT_TOKEN_EXPIRE_SECONDS
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_TOKEN_EXPIRE_SECONDS
    return max(60, value)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    iterations = _password_iterations()
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{_PASSWORD_HASH_ALGO}${iterations}${_urlsafe_b64encode(salt)}${_urlsafe_b64encode(derived)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, iterations_text, salt_text, digest_text = encoded.split("$", maxsplit=3)
    except ValueError:
        return False
    if algo != _PASSWORD_HASH_ALGO:
        return False
    try:
        iterations = int(iterations_text)
    except ValueError:
        return False

    salt = _urlsafe_b64decode(salt_text)
    expected = _urlsafe_b64decode(digest_text)
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(expected, actual)


def create_access_token(claims: dict[str, Any]) -> str:
    now = int(time.time())
    payload = dict(claims)
    payload["iat"] = now
    payload["exp"] = now + token_expires_in()

    body = _urlsafe_b64encode(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = hmac.new(_auth_secret_key().encode("utf-8"), body.encode("utf-8"), hashlib.sha256).digest()
    return f"{body}.{_urlsafe_b64encode(signature)}"


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        body, signature = token.split(".", maxsplit=1)
    except ValueError as exc:
        raise ValueError("token format invalid") from exc

    expected = hmac.new(_auth_secret_key().encode("utf-8"), body.encode("utf-8"), hashlib.sha256).digest()
    provided = _urlsafe_b64decode(signature)
    if not hmac.compare_digest(expected, provided):
        raise ValueError("token signature invalid")

    try:
        payload = json.loads(_urlsafe_b64decode(body).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ValueError("token payload invalid") from exc

    exp = payload.get("exp")
    if not isinstance(exp, int):
        raise ValueError("token exp invalid")
    if exp < int(time.time()):
        raise ValueError("token expired")
    return payload


def to_user_public(user: UserAccount) -> UserPublic:
    return UserPublic(
        user_id=user.user_id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        enabled=user.enabled,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login_at=user.last_login_at,
    )


def authenticate_user(username: str, password: str) -> UserAccount | None:
    user = get_user_by_username(username)
    if user is None:
        return None
    if not user.enabled:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> UserAccount:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录或登录已过期")
    try:
        payload = decode_access_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录或登录已过期") from exc

    user_id = payload.get("sub")
    if not isinstance(user_id, str) or not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录或登录已过期")

    user = get_user(user_id)
    if user is None or not user.enabled:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号不可用，请联系管理员")
    return user


def require_admin(current_user: UserAccount = Depends(get_current_user)) -> UserAccount:
    if current_user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅管理员可执行此操作")
    return current_user


def ensure_default_admin_user() -> None:
    if list_users():
        return

    username = ((os.getenv("ADMIN_USERNAME") or "admin").strip().lower()) or "admin"
    password = ((os.getenv("ADMIN_PASSWORD") or "admin123456").strip()) or "admin123456"
    display_name = ((os.getenv("ADMIN_DISPLAY_NAME") or "管理员").strip()) or "管理员"

    user = UserAccount(
        user_id=str(uuid.uuid4()),
        username=username,
        password_hash=hash_password(password),
        display_name=display_name,
        role=UserRole.admin,
        enabled=True,
        created_at=datetime.now(tz=timezone.utc),
    )
    create_user(user)
    logger.warning("default_admin_created username=%s", username)
