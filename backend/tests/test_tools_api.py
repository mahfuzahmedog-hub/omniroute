"""Tool catalog, grant, and invocation API contracts."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import auth_headers, seed_project


def _base(seed: dict) -> str:
    return f"/api/v1/workspaces/{seed['workspace_id']}/projects/{seed['project_id']}"


# --- catalog ----------------------------------------------------------------
def test_catalog_requires_auth(client: TestClient) -> None:
    assert client.get("/api/v1/tools").status_code == 401


def test_catalog_lists_tools(client: TestClient) -> None:
    seed = seed_project(client)
    h = auth_headers(seed["token"])
    tools = client.get("/api/v1/tools", headers=h).json()
    names = {t["name"] for t in tools}
    assert {"fs.read", "fs.write", "terminal.run", "http.request", "db.query"} <= names
    # The declared-only browser tool is present but not runnable.
    browser = client.get("/api/v1/tools/browser.navigate", headers=h).json()
    assert browser["runnable"] is False
    assert client.get("/api/v1/tools/nope", headers=h).status_code == 404


# --- grants -----------------------------------------------------------------
def test_grant_list_and_revoke(client: TestClient) -> None:
    seed = seed_project(client)
    h = auth_headers(seed["token"])
    base = _base(seed)

    assert client.get(f"{base}/tool-grants", headers=h).json() == []

    granted = client.put(
        f"{base}/tool-grants/filesystem", json={"auto_approve": True}, headers=h
    )
    assert granted.status_code == 200
    assert granted.json()["permission"] == "filesystem"
    assert granted.json()["auto_approve"] is True

    grants = client.get(f"{base}/tool-grants", headers=h).json()
    assert [g["permission"] for g in grants] == ["filesystem"]

    revoke = client.delete(f"{base}/tool-grants/filesystem", headers=h)
    assert revoke.status_code == 204
    assert client.get(f"{base}/tool-grants", headers=h).json() == []


def test_grant_unknown_capability_rejected(client: TestClient) -> None:
    seed = seed_project(client)
    h = auth_headers(seed["token"])
    resp = client.put(f"{_base(seed)}/tool-grants/telepathy", json={}, headers=h)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


# --- invocation -------------------------------------------------------------
def test_invoke_denied_without_grant(client: TestClient) -> None:
    seed = seed_project(client)
    h = auth_headers(seed["token"])
    resp = client.post(
        f"{_base(seed)}/tools/fs.read/invoke", json={"args": {"path": "x"}}, headers=h
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


def test_invoke_roundtrip_and_audit(client: TestClient) -> None:
    seed = seed_project(client)
    h = auth_headers(seed["token"])
    base = _base(seed)
    client.put(f"{base}/tool-grants/filesystem", json={"auto_approve": True}, headers=h)

    write = client.post(
        f"{base}/tools/fs.write/invoke",
        json={"args": {"path": "hello.txt", "content": "world"}},
        headers=h,
    )
    assert write.status_code == 200
    assert write.json()["status"] == "succeeded"

    read = client.post(
        f"{base}/tools/fs.read/invoke", json={"args": {"path": "hello.txt"}}, headers=h
    )
    assert read.json()["outputs"]["content"] == "world"

    # Invocations are listed newest-first, paginated.
    listing = client.get(f"{base}/tool-invocations", headers=h).json()
    assert listing["total"] == 2
    assert {i["tool_name"] for i in listing["items"]} == {"fs.write", "fs.read"}


def test_invoke_destructive_requires_approval(client: TestClient) -> None:
    seed = seed_project(client)
    h = auth_headers(seed["token"])
    base = _base(seed)
    # Grant without auto_approve: destructive ops need an explicit approval.
    client.put(f"{base}/tool-grants/filesystem", json={}, headers=h)
    client.post(
        f"{base}/tools/fs.write/invoke",
        json={"args": {"path": "d.txt", "content": "x"}},
        headers=h,
    )
    blocked = client.post(
        f"{base}/tools/fs.delete/invoke", json={"args": {"path": "d.txt"}}, headers=h
    )
    assert blocked.status_code == 409

    approved = client.post(
        f"{base}/tools/fs.delete/invoke",
        json={"args": {"path": "d.txt"}, "approved": True},
        headers=h,
    )
    assert approved.status_code == 200
    assert approved.json()["outputs"]["deleted"] is True


def test_invoke_unknown_tool(client: TestClient) -> None:
    seed = seed_project(client)
    h = auth_headers(seed["token"])
    resp = client.post(f"{_base(seed)}/tools/ghost/invoke", json={"args": {}}, headers=h)
    assert resp.status_code == 404


def test_invoke_browser_not_runnable(client: TestClient) -> None:
    seed = seed_project(client)
    h = auth_headers(seed["token"])
    base = _base(seed)
    client.put(f"{base}/tool-grants/browser", json={}, headers=h)
    resp = client.post(
        f"{base}/tools/browser.navigate/invoke",
        json={"args": {"url": "https://example.com"}},
        headers=h,
    )
    assert resp.status_code == 409
