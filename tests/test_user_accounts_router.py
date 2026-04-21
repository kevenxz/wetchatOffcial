from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import store
from api.auth import create_access_token, hash_password
from api.models import UserAccount, UserRole
from api.routers import auth, users


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(auth.router, prefix="/api")
    app.include_router(users.router, prefix="/api")
    return app


def _seed_user(
    *,
    user_id: str,
    username: str,
    role: UserRole,
    enabled: bool = True,
) -> UserAccount:
    user = UserAccount(
        user_id=user_id,
        username=username,
        password_hash=hash_password("Passw0rd!"),
        display_name=username,
        role=role,
        enabled=enabled,
        created_at=datetime.now(tz=timezone.utc),
    )
    store.create_user(user)
    return user


def _token_for(user: UserAccount) -> str:
    return create_access_token({"sub": user.user_id, "username": user.username, "role": user.role.value})


def test_admin_can_crud_user_accounts(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(store, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(store, "_user_store", {})
    monkeypatch.setenv("AUTH_SECRET_KEY", "test-secret")

    admin = _seed_user(user_id="u-admin", username="admin", role=UserRole.admin)
    admin_headers = {"Authorization": f"Bearer {_token_for(admin)}"}
    client = TestClient(_build_app())

    create_response = client.post(
        "/api/users",
        headers=admin_headers,
        json={
            "username": "editor",
            "password": "EditorPass123",
            "display_name": "Editor",
            "role": "operator",
            "enabled": True,
        },
    )
    assert create_response.status_code == 201
    created_user = create_response.json()
    assert created_user["username"] == "editor"
    assert "password_hash" not in created_user

    list_response = client.get("/api/users", headers=admin_headers)
    assert list_response.status_code == 200
    usernames = [item["username"] for item in list_response.json()]
    assert "admin" in usernames
    assert "editor" in usernames

    update_response = client.put(
        f"/api/users/{created_user['user_id']}",
        headers=admin_headers,
        json={"display_name": "Editor 2", "enabled": False},
    )
    assert update_response.status_code == 200
    assert update_response.json()["display_name"] == "Editor 2"
    assert update_response.json()["enabled"] is False

    delete_response = client.delete(f"/api/users/{created_user['user_id']}", headers=admin_headers)
    assert delete_response.status_code == 204

    list_after_delete = client.get("/api/users", headers=admin_headers)
    usernames_after_delete = [item["username"] for item in list_after_delete.json()]
    assert "editor" not in usernames_after_delete


def test_non_admin_cannot_manage_users(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(store, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(store, "_user_store", {})
    monkeypatch.setenv("AUTH_SECRET_KEY", "test-secret")

    operator = _seed_user(user_id="u-operator", username="operator", role=UserRole.operator)
    operator_headers = {"Authorization": f"Bearer {_token_for(operator)}"}
    client = TestClient(_build_app())

    response = client.get("/api/users", headers=operator_headers)

    assert response.status_code == 403
    assert "管理员" in response.json()["detail"]
