"""Request-scoped dependencies: database session, authenticated user, workspace access.

These functions are the single choke point where authentication and workspace-scoped
authorization are enforced, upholding the invariant that "every request is evaluated
against workspace/project/resource permissions".
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from forge.config import get_settings
from forge.core.errors import ApiError
from forge.core.security import decode_access_token
from forge.db import SessionLocal
from forge.models.user import User
from forge.models.workspace import WorkspaceMembership, WorkspaceRole

_oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{get_settings().api_v1_prefix}/auth/login",
    auto_error=False,
)


def get_db() -> Generator[Session, None, None]:
    """Yield a database session, guaranteeing it is closed after the request."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbSession,
    token: Annotated[str | None, Depends(_oauth2_scheme)],
) -> User:
    """Resolve the authenticated, active user from the bearer token."""
    if not token:
        raise ApiError.unauthorized()
    subject = decode_access_token(token)
    if not subject:
        raise ApiError.unauthorized("Invalid or expired token")
    try:
        user_id = uuid.UUID(subject)
    except ValueError:
        raise ApiError.unauthorized("Invalid token subject") from None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise ApiError.unauthorized("User no longer active")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_workspace_membership(
    workspace_id: uuid.UUID,
    db: Session,
    user: User,
) -> WorkspaceMembership:
    """Return the caller's membership in ``workspace_id`` or raise 404/403.

    A missing membership is reported as 404 (not 403) so callers cannot probe which
    workspace IDs exist — a deliberate project-isolation choice.
    """
    membership = db.scalar(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == user.id,
        )
    )
    if membership is None:
        raise ApiError.not_found("Workspace not found")
    return membership


def require_workspace_write(membership: WorkspaceMembership) -> None:
    if not membership.role.can_write():
        raise ApiError.forbidden("This role cannot modify workspace resources")


def require_workspace_admin(membership: WorkspaceMembership) -> None:
    if not membership.role.can_administer():
        raise ApiError.forbidden("This role cannot administer the workspace")


__all__ = [
    "get_db",
    "DbSession",
    "get_current_user",
    "CurrentUser",
    "require_workspace_membership",
    "require_workspace_write",
    "require_workspace_admin",
    "WorkspaceRole",
]
