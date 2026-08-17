"""Health probe contract."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_ok(client: TestClient) -> None:
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert "version" in body


def test_correlation_id_header_echoed(client: TestClient) -> None:
    resp = client.get("/api/v1/health", headers={"X-Request-ID": "corr-123"})
    assert resp.headers.get("X-Request-ID") == "corr-123"


def test_correlation_id_generated_when_absent(client: TestClient) -> None:
    resp = client.get("/api/v1/health")
    assert resp.headers.get("X-Request-ID")
