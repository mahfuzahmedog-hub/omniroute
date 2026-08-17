"""Project model.

A project is the unit of autonomous work. In Phase 1 it holds identity, its
natural-language specification, and lifecycle status. Runs, tasks, agents, and
sandboxes attach to a project in later phases. The ``version`` counter (from
``VersionedMixin``) guards against concurrent stale writes.
"""

from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from forge.db import GUID
from forge.models.base import Base, TimestampMixin, UUIDMixin, VersionedMixin

if TYPE_CHECKING:
    from forge.models.workspace import Workspace


class ProjectStatus(enum.StrEnum):
    """High-level project lifecycle state (control-plane view)."""

    draft = "draft"
    active = "active"
    paused = "paused"
    archived = "archived"


class Project(Base, UUIDMixin, TimestampMixin, VersionedMixin):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("workspace_id", "slug", name="uq_project_workspace_slug"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # The natural-language goal/specification the user gave Forge.
    specification: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, native_enum=False, length=32),
        default=ProjectStatus.draft,
        nullable=False,
    )

    workspace: Mapped[Workspace] = relationship(back_populates="projects")
