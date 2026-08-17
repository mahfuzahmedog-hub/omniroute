"""Contracts for the error envelope and the audit trail."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from forge.db import SessionLocal
from forge.models.audit import AuditEvent
from tests.conftest import auth_headers, first_workspace_id, register_user


def test_error_envelope_shape_on_404(client: TestClient) -> None:
    token = register_user(client)["access_token"]
    ws = first_workspace_id(client, token)
    resp = client.get(
        f"/api/v1/workspaces/{ws}/projects/00000000-0000-0000-0000-000000000000",
        headers=auth_headers(token),
    )
    assert resp.status_code == 404
    body = resp.json()
    assert set(body.keys()) == {"error"}
    assert body["error"]["code"] == "not_found"
    assert "message" in body["error"]
    assert body["error"]["correlation_id"]


def test_audit_events_recorded_for_project_lifecycle(client: TestClient) -> None:
    token = register_user(client)["access_token"]
    ws = first_workspace_id(client, token)
    client.post(
        f"/api/v1/workspaces/{ws}/projects",
        json={"name": "Audited", "slug": "audited"},
        headers=auth_headers(token),
    )

    with SessionLocal() as session:
        actions = set(session.scalars(select(AuditEvent.action)).all())

    # Registration and project creation must both leave a durable audit trail.
    assert "user.registered" in actions
    assert "project.created" in actions


def test_audit_event_has_correlation_id(client: TestClient) -> None:
    register_user(client)
    with SessionLocal() as session:
        event = session.scalar(
            select(AuditEvent).where(AuditEvent.action == "user.registered")
        )
    assert event is not None
    assert event.correlation_id  # stamped from the request correlation id
