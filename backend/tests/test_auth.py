"""Authentication contracts: register, login, current-user, and failure paths."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import auth_headers, register_user


def test_register_returns_token_and_user(client: TestClient) -> None:
    body = register_user(client)
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["email"] == "alice@example.com"
    assert body["user"]["is_active"] is True


def test_register_provisions_personal_workspace(client: TestClient) -> None:
    token = register_user(client)["access_token"]
    resp = client.get("/api/v1/workspaces", headers=auth_headers(token))
    assert resp.status_code == 200
    workspaces = resp.json()
    assert len(workspaces) == 1
    assert workspaces[0]["role"] == "owner"


def test_register_duplicate_email_conflicts(client: TestClient) -> None:
    register_user(client)
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "alice@example.com", "password": "anotherpw1", "full_name": "A2"},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "conflict"


def test_register_rejects_short_password(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "bob@example.com", "password": "short"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


def test_login_success(client: TestClient) -> None:
    register_user(client)
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": "alice@example.com", "password": "sup3rsecret"},
    )
    assert resp.status_code == 200
    assert resp.json()["access_token"]


def test_login_wrong_password_unauthorized(client: TestClient) -> None:
    register_user(client)
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": "alice@example.com", "password": "wrongpassword"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


def test_login_unknown_user_unauthorized(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": "nobody@example.com", "password": "whatever12"},
    )
    assert resp.status_code == 401


def test_me_requires_auth(client: TestClient) -> None:
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_me_returns_current_user(client: TestClient) -> None:
    token = register_user(client)["access_token"]
    resp = client.get("/api/v1/auth/me", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["email"] == "alice@example.com"


def test_me_rejects_garbage_token(client: TestClient) -> None:
    resp = client.get("/api/v1/auth/me", headers=auth_headers("not-a-real-token"))
    assert resp.status_code == 401
