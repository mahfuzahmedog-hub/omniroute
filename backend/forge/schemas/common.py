"""Shared response schemas."""

from __future__ import annotations

from pydantic import BaseModel


class HealthStatus(BaseModel):
    """Health/readiness probe payload."""

    status: str
    version: str
    environment: str
    database: str
