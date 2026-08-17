"""Run model — a top-level execution of autonomous work for a project.

A run owns a graph of tasks. It is durable: its state survives API restarts and worker
crashes, and it can be resumed. The ``version`` counter guards concurrent writes.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from forge.db import GUID
from forge.models.base import Base, TimestampMixin, UUIDMixin, VersionedMixin

if TYPE_CHECKING:
    from forge.models.task import Task


class RunStatus(enum.StrEnum):
    """Lifecycle state of a run."""

    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"

    def is_terminal(self) -> bool:
        return self in (RunStatus.succeeded, RunStatus.failed, RunStatus.cancelled)


class Run(Base, UUIDMixin, TimestampMixin, VersionedMixin):
    __tablename__ = "runs"

    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus, native_enum=False, length=32),
        default=RunStatus.pending,
        nullable=False,
        index=True,
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    tasks: Mapped[list[Task]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
