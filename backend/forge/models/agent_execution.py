"""Agent execution model — a durable, episodic record of one agent run.

The database spec lists "agent executions" as a core entity, and the agent spec requires
that an agent cannot be considered complete unless its outputs exist and its verification
contract passes. This table records every attempt (input, output, verification result,
model, and cost/usage) so agent behavior is auditable and replayable.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from forge.db import GUID
from forge.models.base import Base, TimestampMixin, UUIDMixin


class AgentStatus(enum.StrEnum):
    """Agent execution lifecycle (per spec 04_AGENT_SYSTEM)."""

    created = "created"
    queued = "queued"
    running = "running"
    waiting = "waiting"
    verifying = "verifying"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class AgentExecution(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "agent_executions"

    task_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    agent_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[AgentStatus] = mapped_column(
        String(32), default=AgentStatus.created, nullable=False, index=True
    )

    input: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Structured verification result: {"passed": bool, "checks": [{name, passed, detail}]}.
    verification: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Model + cost attribution (populated once the model runtime exists in later phases).
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
