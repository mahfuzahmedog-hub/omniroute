"""Project request/response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from forge.models.project import ProjectStatus


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=255, pattern=r"^[a-z0-9][a-z0-9-]*$")
    specification: str | None = Field(default=None, max_length=100_000)


class ProjectUpdate(BaseModel):
    """Partial update. ``expected_version`` enables optimistic concurrency control."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    specification: str | None = Field(default=None, max_length=100_000)
    status: ProjectStatus | None = None
    expected_version: int | None = Field(
        default=None,
        description="If set, the update is rejected with 409 unless it matches the "
        "project's current version.",
    )


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    slug: str
    specification: str | None
    status: ProjectStatus
    version: int
    created_at: datetime
    updated_at: datetime
