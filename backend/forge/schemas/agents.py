"""Agent catalog and execution-record schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BudgetOut(BaseModel):
    max_usd: float | None
    max_tokens: int | None
    max_seconds: float | None


class AgentOut(BaseModel):
    key: str
    role: str
    objective: str
    allowed_tools: list[str]
    model_policy: dict
    budget: BudgetOut
    max_attempts: int
    escalation_target: str | None
    runnable: bool


class AgentExecutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    run_id: uuid.UUID
    agent_key: str
    role: str
    status: str
    input: dict | None
    output: dict | None
    verification: dict | None
    error: str | None
    model: str | None
    tokens_used: int
    cost_usd: float
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
