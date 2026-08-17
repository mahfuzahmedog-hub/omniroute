"""Test fixtures.

We bind Forge to an isolated temporary SQLite database *before* importing the app, so
the module-level engine/session pick it up. Each test gets a freshly created schema for
full isolation, which is cheap at this scale and avoids cross-test state leakage.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator

import pytest

# Configure the environment before importing any forge module (settings are read once).
# Honor a preset FORGE_DATABASE_URL (e.g. Postgres in CI); otherwise use a temp SQLite DB.
if not os.environ.get("FORGE_DATABASE_URL"):
    _DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db", prefix="forge_test_")
    os.close(_DB_FD)
    os.environ["FORGE_DATABASE_URL"] = f"sqlite+pysqlite:///{_DB_PATH}"
os.environ.setdefault("FORGE_SECRET_KEY", "test-secret-key-not-used-in-production-abcdefgh")
os.environ.setdefault("FORGE_ENVIRONMENT", "local")

from fastapi.testclient import TestClient  # noqa: E402

from forge.db import engine  # noqa: E402
from forge.main import app  # noqa: E402
from forge.models import Base  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_schema() -> Iterator[None]:
    """Recreate the schema before each test for isolation."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def register_user(
    client: TestClient,
    email: str = "alice@example.com",
    password: str = "sup3rsecret",
    full_name: str = "Alice",
) -> dict:
    """Register a user and return the parsed token response body."""
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": full_name},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def first_workspace_id(client: TestClient, token: str) -> str:
    """Return the id of the personal workspace provisioned at registration."""
    resp = client.get("/api/v1/workspaces", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    workspaces = resp.json()
    assert workspaces, "expected a personal workspace"
    return workspaces[0]["id"]


def seed_project(client: TestClient, email: str = "eng@example.com") -> dict[str, str]:
    """Register a user and create a project; return token + workspace + project ids."""
    token = register_user(client, email=email)["access_token"]
    workspace_id = first_workspace_id(client, token)
    resp = client.post(
        f"/api/v1/workspaces/{workspace_id}/projects",
        json={"name": "Engine", "slug": "engine"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return {
        "token": token,
        "workspace_id": workspace_id,
        "project_id": resp.json()["id"],
    }
