"""Tool grant + tool invocation models.

Two durable records back the tool runtime:

- :class:`ProjectToolGrant` — the project-scoped permission grants. Absence of a row means
  the capability is denied (spec: "tools are denied by default").
- :class:`ToolInvocation` — an append-only, structured audit record of every tool call:
  who/what invoked it, against which project/run/task, redacted argument metadata, a result
  summary, duration, and the final state. Secrets are never stored verbatim.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from forge.db import GUID
from forge.models.base import Base, TimestampMixin, UUIDMixin


class ProjectToolGrant(Base, UUIDMixin, TimestampMixin):
    """A project's grant of one tool capability. Presence of the row = granted."""

    __tablename__ = "project_tool_grants"
    __table_args__ = (
        UniqueConstraint("project_id", "permission", name="uq_project_tool_grant"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # The granted capability, e.g. "filesystem", "terminal" (see tools.permissions).
    permission: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # When true, approval-gated (destructive) tools under this capability may run without a
    # per-call human approval. Defaults to false: destructive actions require an explicit gate.
    auto_approve: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Optional network egress allow-list (hostnames) scoped to this capability grant.
    allowed_hosts: Mapped[list | None] = mapped_column(JSON, nullable=True)


class ToolInvocationStatus(enum.StrEnum):
    """Lifecycle of a single tool call."""

    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    denied = "denied"  # permission not granted
    approval_required = "approval_required"  # destructive call without an approval gate


class ToolInvocation(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "tool_invocations"

    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("runs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # The agent that made the call, if any (agents reference tools by capability).
    agent_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    tool_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tool_version: Mapped[str] = mapped_column(String(32), nullable=False)
    permission: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[ToolInvocationStatus] = mapped_column(
        String(32), default=ToolInvocationStatus.running, nullable=False, index=True
    )
    side_effect: Mapped[str] = mapped_column(String(16), nullable=False)
    cost_class: Mapped[str] = mapped_column(String(16), nullable=False)

    # Redacted argument metadata and a compact result summary — never raw secrets/bodies.
    args_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
