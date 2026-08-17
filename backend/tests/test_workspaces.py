"""Workspace contracts: creation, listing, and slug conflicts."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import auth_headers, register_user


def test_create_workspace(client: TestClient) -> None:
    token = register_user(client)["access_token"]
    resp = client.post(
        "/api/v1/workspaces",
        json={"name": "Acme", "slug": "acme"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["slug"] == "acme"
    assert body["role"] == "owner"


def test_create_workspace_requires_auth(client: TestClient) -> None:
    resp = client.post("/api/v1/workspaces", json={"name": "Acme", "slug": "acme"})
    assert resp.status_code == 401


def test_duplicate_slug_conflicts(client: TestClient) -> None:
    token = register_user(client)["access_token"]
    client.post(
        "/api/v1/workspaces", json={"name": "Acme", "slug": "acme"}, headers=auth_headers(token)
    )
    resp = client.post(
        "/api/v1/workspaces", json={"name": "Acme 2", "slug": "acme"}, headers=auth_headers(token)
    )
    assert resp.status_code == 409


def test_invalid_slug_rejected(client: TestClient) -> None:
    token = register_user(client)["access_token"]
    resp = client.post(
        "/api/v1/workspaces",
        json={"name": "Bad", "slug": "Has Spaces"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 422


def test_list_workspaces_scoped_to_user(client: TestClient) -> None:
    token_a = register_user(client, email="a@example.com")["access_token"]
    token_b = register_user(client, email="b@example.com")["access_token"]
    client.post(
        "/api/v1/workspaces",
        json={"name": "A-only", "slug": "a-only"},
        headers=auth_headers(token_a),
    )
    # User B should see only their own personal workspace, not A's workspaces.
    resp = client.get("/api/v1/workspaces", headers=auth_headers(token_b))
    slugs = {w["slug"] for w in resp.json()}
    assert "a-only" not in slugs
