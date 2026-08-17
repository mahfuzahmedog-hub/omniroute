"""Project contracts: CRUD, workspace isolation, pagination, optimistic concurrency."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import auth_headers, first_workspace_id, register_user


def _create_project(client: TestClient, token: str, ws: str, slug: str = "web-app") -> dict:
    resp = client.post(
        f"/api/v1/workspaces/{ws}/projects",
        json={"name": "Web App", "slug": slug, "specification": "Build a SaaS."},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_and_get_project(client: TestClient) -> None:
    token = register_user(client)["access_token"]
    ws = first_workspace_id(client, token)
    created = _create_project(client, token, ws)
    assert created["status"] == "draft"
    assert created["version"] == 1

    resp = client.get(
        f"/api/v1/workspaces/{ws}/projects/{created['id']}", headers=auth_headers(token)
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Web App"


def test_list_projects_paginated(client: TestClient) -> None:
    token = register_user(client)["access_token"]
    ws = first_workspace_id(client, token)
    for i in range(3):
        _create_project(client, token, ws, slug=f"proj-{i}")

    resp = client.get(
        f"/api/v1/workspaces/{ws}/projects?limit=2&offset=0", headers=auth_headers(token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["limit"] == 2


def test_duplicate_slug_in_workspace_conflicts(client: TestClient) -> None:
    token = register_user(client)["access_token"]
    ws = first_workspace_id(client, token)
    _create_project(client, token, ws, slug="dupe")
    resp = client.post(
        f"/api/v1/workspaces/{ws}/projects",
        json={"name": "Dup", "slug": "dupe"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 409


def test_project_isolation_between_workspaces(client: TestClient) -> None:
    # User A creates a project; user B must not be able to read it.
    token_a = register_user(client, email="a@example.com")["access_token"]
    token_b = register_user(client, email="b@example.com")["access_token"]
    ws_a = first_workspace_id(client, token_a)
    created = _create_project(client, token_a, ws_a)

    resp = client.get(
        f"/api/v1/workspaces/{ws_a}/projects/{created['id']}", headers=auth_headers(token_b)
    )
    # 404 (not 403) so B cannot even confirm the workspace exists.
    assert resp.status_code == 404


def test_update_project(client: TestClient) -> None:
    token = register_user(client)["access_token"]
    ws = first_workspace_id(client, token)
    created = _create_project(client, token, ws)

    resp = client.patch(
        f"/api/v1/workspaces/{ws}/projects/{created['id']}",
        json={"name": "Renamed", "status": "active"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Renamed"
    assert body["status"] == "active"
    assert body["version"] == 2  # optimistic-concurrency counter advanced


def test_optimistic_concurrency_conflict(client: TestClient) -> None:
    token = register_user(client)["access_token"]
    ws = first_workspace_id(client, token)
    created = _create_project(client, token, ws)

    # Providing a stale expected_version is rejected with 409.
    resp = client.patch(
        f"/api/v1/workspaces/{ws}/projects/{created['id']}",
        json={"name": "Nope", "expected_version": 999},
        headers=auth_headers(token),
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "conflict"


def test_delete_project(client: TestClient) -> None:
    token = register_user(client)["access_token"]
    ws = first_workspace_id(client, token)
    created = _create_project(client, token, ws)

    resp = client.delete(
        f"/api/v1/workspaces/{ws}/projects/{created['id']}", headers=auth_headers(token)
    )
    assert resp.status_code == 204

    resp = client.get(
        f"/api/v1/workspaces/{ws}/projects/{created['id']}", headers=auth_headers(token)
    )
    assert resp.status_code == 404


def test_create_project_requires_auth(client: TestClient) -> None:
    token = register_user(client)["access_token"]
    ws = first_workspace_id(client, token)
    resp = client.post(
        f"/api/v1/workspaces/{ws}/projects", json={"name": "X", "slug": "x"}
    )
    assert resp.status_code == 401
