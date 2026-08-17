"""Agent catalog + execution API contracts."""

from __future__ import annotations

from fastapi.testclient import TestClient

from forge.agents.runner import register_agents
from forge.db import SessionLocal
from forge.orchestration.worker import HandlerRegistry, Worker
from tests.conftest import auth_headers, register_user, seed_project


def test_agent_catalog_lists_roster_and_examples(client: TestClient) -> None:
    token = register_user(client)["access_token"]
    resp = client.get("/api/v1/agents", headers=auth_headers(token))
    assert resp.status_code == 200
    by_key = {a["key"]: a for a in resp.json()}
    assert by_key["commander"]["runnable"] is False
    assert by_key["example.sum"]["runnable"] is True
    assert by_key["researcher"]["role"] == "Researcher"


def test_agent_catalog_requires_auth(client: TestClient) -> None:
    assert client.get("/api/v1/agents").status_code == 401


def test_get_unknown_agent_404(client: TestClient) -> None:
    token = register_user(client)["access_token"]
    resp = client.get("/api/v1/agents/nope", headers=auth_headers(token))
    assert resp.status_code == 404


def test_agent_executions_listed_for_run(client: TestClient) -> None:
    seed = seed_project(client)
    h = auth_headers(seed["token"])
    base = f"/api/v1/workspaces/{seed['workspace_id']}/projects/{seed['project_id']}"

    run = client.post(f"{base}/runs", json={"name": "agents"}, headers=h).json()
    client.post(
        f"{base}/runs/{run['id']}/tasks",
        json={"name": "sum", "kind": "example.sum", "inputs": {"numbers": [1, 2, 3, 4]}},
        headers=h,
    )
    client.post(f"{base}/runs/{run['id']}/start", headers=h)

    # Drain with a worker that has the agents registered.
    reg = HandlerRegistry()
    register_agents(worker_registry=reg)
    Worker(SessionLocal, registry=reg).run()

    resp = client.get(f"{base}/runs/{run['id']}/agent-executions", headers=h)
    assert resp.status_code == 200
    executions = resp.json()
    assert len(executions) == 1
    assert executions[0]["agent_key"] == "example.sum"
    assert executions[0]["status"] == "succeeded"
    assert executions[0]["output"] == {"sum": 10}


def test_agent_executions_require_membership(client: TestClient) -> None:
    seed = seed_project(client, email="owner@example.com")
    base = f"/api/v1/workspaces/{seed['workspace_id']}/projects/{seed['project_id']}"
    run = client.post(
        f"{base}/runs", json={"name": "r"}, headers=auth_headers(seed["token"])
    ).json()
    intruder = register_user(client, email="intruder@example.com")["access_token"]
    resp = client.get(f"{base}/runs/{run['id']}/agent-executions", headers=auth_headers(intruder))
    assert resp.status_code == 404
