"""Workspace and workspace-membership (RBAC) models.

A workspace is the top-level tenancy boundary. Users gain access to a workspace's
projects only through a :class:`WorkspaceMembership`, which carries a role. This is the
enforcement point for the least-privilege and project-isolation invariants.
"""

from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from forge.db import GUID
from forge.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from forge.models.project import Project
    from forge.models.user import User


class WorkspaceRole(enum.StrEnum):
    """Roles within a workspace, ordered from most to least privileged."""

    owner = "owner"
    admin = "admin"
    member = "member"
    viewer = "viewer"

    def can_write(self) -> bool:
        """Whether this role may create or mutate resources in the workspace."""
        return self in (WorkspaceRole.owner, WorkspaceRole.admin, WorkspaceRole.member)

    def can_administer(self) -> bool:
        """Whether this role may manage members and workspace settings."""
        return self in (WorkspaceRole.owner, WorkspaceRole.admin)


class Workspace(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "workspaces"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)

    memberships: Mapped[list[WorkspaceMembership]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    projects: Mapped[list[Project]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
    )


class WorkspaceMembership(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "workspace_memberships"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_membership_workspace_user"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[WorkspaceRole] = mapped_column(
        Enum(WorkspaceRole, native_enum=False, length=32), nullable=False
    )

    workspace: Mapped[Workspace] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")
