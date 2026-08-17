"""Audit event model — the append-only audit trail.

The master spec makes auditability an invariant: "every autonomous action is auditable"
and "important state changes require timestamps, actor/source, and correlation IDs".
:class:`AuditEvent` is an append-only record satisfying that requirement. It is
deliberately generic (action string + JSON metadata) so every subsystem can write to
one durable, queryable trail rather than inventing bespoke logging.
"""

from __future__ import annotations

import uuid

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from forge.db import GUID
from forge.models.base import Base, TimestampMixin, UUIDMixin


class AuditEvent(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "audit_events"

    # Correlation ID linking this event to the originating request/run/task chain.
    correlation_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)

    # Who/what caused the change. Nullable for unauthenticated/system events.
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_type: Mapped[str] = mapped_column(String(32), default="user", nullable=False)

    # Dotted action verb, e.g. "project.created", "auth.login".
    action: Mapped[str] = mapped_column(String(128), index=True, nullable=False)

    # The affected resource, as a type + id pair for cheap filtering.
    resource_type: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)

    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Additional structured context. Must never contain secrets or raw credentials.
    event_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
