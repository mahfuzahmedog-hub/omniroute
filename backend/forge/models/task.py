"""Task model and the task dependency graph.

A task is the atomic unit of durable, recoverable work. Its design encodes the Phase 2
reliability requirements directly as columns:

- ``status`` + ``version``: a validated state machine with optimistic-concurrency-safe
  transitions (no two workers can claim the same task).
- ``attempts`` / ``max_attempts`` / ``available_at``: bounded retries with backoff.
- ``lease_owner`` / ``lease_expires_at``: worker leases so an abandoned task (crashed
  worker) can be reclaimed and retried.
- ``cancel_requested``: cooperative cancellation honored at completion boundaries.
- ``checkpoint``: durable partial progress so a resumed task need not start over.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from forge.db import GUID
from forge.models.base import Base, TimestampMixin, UUIDMixin, VersionedMixin, utcnow

if TYPE_CHECKING:
    from forge.models.run import Run


class TaskStatus(enum.StrEnum):
    """Lifecycle state of a task.

    ``pending`` — created; dependencies may be unmet.
    ``ready``   — dependencies satisfied; waiting for a worker.
    ``running`` — leased and executing.
    ``succeeded``/``failed``/``cancelled``/``dead_letter`` — terminal.
    """

    pending = "pending"
    ready = "ready"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"
    dead_letter = "dead_letter"

    def is_terminal(self) -> bool:
        return self in (
            TaskStatus.succeeded,
            TaskStatus.failed,
            TaskStatus.cancelled,
            TaskStatus.dead_letter,
        )


class Task(Base, UUIDMixin, TimestampMixin, VersionedMixin):
    __tablename__ = "tasks"

    run_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Maps the task to a registered handler in the worker's handler registry.
    kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, native_enum=False, length=32),
        default=TaskStatus.pending,
        nullable=False,
        index=True,
    )
    # Lower number = higher priority.
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

    inputs: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    outputs: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    acceptance_criteria: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    # Earliest time the task may be claimed (used to implement retry backoff).
    available_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, index=True
    )

    lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, index=True
    )

    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    checkpoint: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    run: Mapped[Run] = relationship(back_populates="tasks")
    dependencies: Mapped[list[TaskDependency]] = relationship(
        back_populates="task",
        foreign_keys="TaskDependency.task_id",
        cascade="all, delete-orphan",
    )


class TaskDependency(Base, UUIDMixin, TimestampMixin):
    """A directed edge: ``task_id`` depends on ``depends_on_id`` succeeding first."""

    __tablename__ = "task_dependencies"
    __table_args__ = (
        UniqueConstraint("task_id", "depends_on_id", name="uq_task_dependency"),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    depends_on_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )

    task: Mapped[Task] = relationship(foreign_keys=[task_id], back_populates="dependencies")
    depends_on: Mapped[Task] = relationship(foreign_keys=[depends_on_id])
