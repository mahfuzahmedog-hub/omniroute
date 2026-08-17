"""Run and task API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from forge.models.run import RunStatus
from forge.models.task import TaskStatus


class RunCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    status: RunStatus
    error: str | None
    version: int
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class TaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    kind: str = Field(min_length=1, max_length=64)
    inputs: dict | None = None
    priority: int = Field(default=100, ge=0)
    max_attempts: int = Field(default=3, ge=1, le=20)
    depends_on: list[uuid.UUID] = Field(default_factory=list)


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    name: str
    kind: str
    status: TaskStatus
    priority: int
    inputs: dict | None
    outputs: dict | None
    attempts: int
    max_attempts: int
    error: str | None
    version: int
    created_at: datetime
