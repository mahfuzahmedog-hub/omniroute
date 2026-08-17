"""Audit-trail service.

A tiny, deliberate seam so subsystems record important state changes uniformly. The
event is added to the caller's session and flushed, but committed with the surrounding
transaction so the audit record and the state change it describes commit atomically.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from forge.logging import correlation_id_var
from forge.models.audit import AuditEvent


def record_event(
    db: Session,
    *,
    action: str,
    actor_user_id: uuid.UUID | None = None,
    actor_type: str = "user",
    resource_type: str | None = None,
    resource_id: str | uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    metadata: dict | None = None,
) -> AuditEvent:
    """Append an :class:`AuditEvent` to the current unit of work.

    The caller owns the transaction: this flushes so the event gets an ID but does not
    commit, ensuring the audit row and the change it records share one atomic commit.
    """
    event = AuditEvent(
        correlation_id=correlation_id_var.get() or None,
        actor_user_id=actor_user_id,
        actor_type=actor_type,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        workspace_id=workspace_id,
        event_metadata=metadata,
    )
    db.add(event)
    db.flush()
    return event
