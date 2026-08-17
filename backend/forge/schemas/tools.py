"""Tool catalog, grant, and invocation API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ToolOut(BaseModel):
    """A tool contract as exposed by the read-only catalog."""

    name: str
    description: str
    permission: str
    version: str
    cost_class: str
    side_effect: str
    requires_network: bool
    approval_gated: bool
    runnable: bool
    timeout_seconds: float
    input_schema: dict
    output_schema: dict


class ToolGrantIn(BaseModel):
    """Request body to grant (or update) a capability for a project."""

    auto_approve: bool = False
    allowed_hosts: list[str] | None = None


class ToolGrantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    permission: str
    auto_approve: bool
    allowed_hosts: list[str] | None
    created_at: datetime


class ToolInvokeIn(BaseModel):
    """Request body to invoke a tool directly through the API."""

    args: dict = Field(default_factory=dict)
    approved: bool = False


class ToolInvokeOut(BaseModel):
    invocation_id: uuid.UUID
    tool: str
    status: str
    outputs: dict
    duration_ms: int | None


class ToolInvocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    run_id: uuid.UUID | None
    task_id: uuid.UUID | None
    agent_key: str | None
    tool_name: str
    tool_version: str
    permission: str
    status: str
    side_effect: str
    cost_class: str
    args_metadata: dict | None
    result_summary: dict | None
    error: str | None
    duration_ms: int | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
