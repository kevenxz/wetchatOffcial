from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import store
from api.auth import create_access_token, hash_password
from api.models import UserAccount, UserRole
from api.routers import auth


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(auth.router, prefix="/api")
    return app


def _seed_user(*, role: UserRole = UserRole.admin, enabled: bool = True) -> UserAccount:
    now = datetime.now(tz=timezone.utc)
    user = UserAccount(
        user_id="user-admin-1",
        username="admin",
        password_hash=hash_password("admin123456"),
        display_name="Admin",
        role=role,
        enabled=enabled,
        created_at=now,
    )
    store.create_user(user)
    return user


def test_login_returns_token_for_valid_credentials(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(store, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(store, "_user_store", {})
    monkeypatch.setenv("AUTH_SECRET_KEY", "test-secret")

    _seed_user()

    client = TestClient(_build_app())
    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123456"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["access_token"]
    assert payload["user"]["username"] == "admin"
    assert payload["user"]["role"] == "admin"


def test_login_rejects_invalid_password(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(store, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(store, "_user_store", {})
    monkeypatch.setenv("AUTH_SECRET_KEY", "test-secret")

    _seed_user()

    client = TestClient(_build_app())
    response = client.post("/api/auth/login", json={"username": "admin", "password": "wrong-password"})

    assert response.status_code == 401
    assert "用户名或密码错误" in response.json()["detail"]


def test_me_requires_bearer_token(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(store, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(store, "_user_store", {})
    monkeypatch.setenv("AUTH_SECRET_KEY", "test-secret")

    _seed_user()

    client = TestClient(_build_app())
    response = client.get("/api/auth/me")

    assert response.status_code == 401


def test_me_returns_current_user(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(store, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(store, "_user_store", {})
    monkeypatch.setenv("AUTH_SECRET_KEY", "test-secret")

    user = _seed_user(role=UserRole.operator)
    token = create_access_token({"sub": user.user_id, "username": user.username, "role": user.role.value})

    client = TestClient(_build_app())
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["user_id"] == user.user_id
    assert payload["username"] == "admin"
    assert payload["role"] == "operator"
