"""Run/task control API contracts."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from forge.db import SessionLocal
from forge.orchestration.worker import Worker
from tests.conftest import auth_headers, register_user, seed_project


def test_run_lifecycle_via_api(client: TestClient) -> None:
    seed = seed_project(client)
    h = auth_headers(seed["token"])
    base = f"/api/v1/workspaces/{seed['workspace_id']}/projects/{seed['project_id']}"

    # Create a run
    run = client.post(f"{base}/runs", json={"name": "build"}, headers=h).json()
    assert run["status"] == "pending"

    # Add two tasks, B depends on A
    a = client.post(
        f"{base}/runs/{run['id']}/tasks",
        json={"name": "A", "kind": "noop"},
        headers=h,
    ).json()
    b = client.post(
        f"{base}/runs/{run['id']}/tasks",
        json={"name": "B", "kind": "noop", "depends_on": [a["id"]]},
        headers=h,
    )
    assert b.status_code == 201

    # Start it
    started = client.post(f"{base}/runs/{run['id']}/start", headers=h)
    assert started.status_code == 200
    assert started.json()["status"] == "running"

    # Tasks visible; A ready, B pending
    tasks = client.get(f"{base}/runs/{run['id']}/tasks", headers=h).json()
    by_name = {t["name"]: t for t in tasks}
    assert by_name["A"]["status"] == "ready"
    assert by_name["B"]["status"] == "pending"

    # Drain the queue with a worker, then the run should be succeeded.
    Worker(SessionLocal).run()
    final = client.get(f"{base}/runs/{run['id']}", headers=h).json()
    assert final["status"] == "succeeded"


def test_cannot_add_task_after_start(client: TestClient) -> None:
    seed = seed_project(client)
    h = auth_headers(seed["token"])
    base = f"/api/v1/workspaces/{seed['workspace_id']}/projects/{seed['project_id']}"
    run = client.post(f"{base}/runs", json={"name": "r"}, headers=h).json()
    client.post(f"{base}/runs/{run['id']}/start", headers=h)
    resp = client.post(
        f"{base}/runs/{run['id']}/tasks", json={"name": "late", "kind": "noop"}, headers=h
    )
    assert resp.status_code == 409


def test_cancel_run_via_api(client: TestClient) -> None:
    seed = seed_project(client)
    h = auth_headers(seed["token"])
    base = f"/api/v1/workspaces/{seed['workspace_id']}/projects/{seed['project_id']}"
    run = client.post(f"{base}/runs", json={"name": "r"}, headers=h).json()
    client.post(f"{base}/runs/{run['id']}/tasks", json={"name": "A", "kind": "noop"}, headers=h)
    client.post(f"{base}/runs/{run['id']}/start", headers=h)
    resp = client.post(f"{base}/runs/{run['id']}/cancel", headers=h)
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


def test_runs_require_workspace_membership(client: TestClient) -> None:
    seed = seed_project(client, email="owner@example.com")
    base = f"/api/v1/workspaces/{seed['workspace_id']}/projects/{seed['project_id']}"
    # A different user must not see another workspace's runs (404, not 403).
    other = register_user(client, email="intruder@example.com")["access_token"]
    resp = client.get(f"{base}/runs", headers=auth_headers(other))
    assert resp.status_code == 404


def test_run_scoped_to_project(client: TestClient) -> None:
    seed = seed_project(client)
    h = auth_headers(seed["token"])
    base = f"/api/v1/workspaces/{seed['workspace_id']}/projects/{seed['project_id']}"
    run = client.post(f"{base}/runs", json={"name": "r"}, headers=h).json()

    # Fetch via a random (non-existent) project id under the same workspace → 404.
    bogus = uuid.uuid4()
    resp = client.get(
        f"/api/v1/workspaces/{seed['workspace_id']}/projects/{bogus}/runs/{run['id']}",
        headers=h,
    )
    assert resp.status_code == 404
