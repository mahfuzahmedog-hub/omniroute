"""Workspace routes: list the caller's workspaces and create new ones."""

from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from forge.core.deps import CurrentUser, DbSession
from forge.core.errors import ApiError
from forge.models.workspace import Workspace, WorkspaceMembership, WorkspaceRole
from forge.schemas.workspace import WorkspaceCreate, WorkspaceOut
from forge.services.audit import record_event

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.get("", response_model=list[WorkspaceOut])
def list_workspaces(user: CurrentUser, db: DbSession) -> list[WorkspaceOut]:
    """List every workspace the caller belongs to, with their role in each."""
    memberships = db.scalars(
        select(WorkspaceMembership)
        .where(WorkspaceMembership.user_id == user.id)
        .options(joinedload(WorkspaceMembership.workspace))
        .order_by(WorkspaceMembership.created_at)
    ).all()
    return [
        WorkspaceOut(
            id=m.workspace.id, name=m.workspace.name, slug=m.workspace.slug, role=m.role
        )
        for m in memberships
    ]


@router.post("", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
def create_workspace(
    payload: WorkspaceCreate, user: CurrentUser, db: DbSession
) -> WorkspaceOut:
    """Create a workspace; the caller becomes its owner."""
    if db.scalar(select(Workspace.id).where(Workspace.slug == payload.slug)) is not None:
        raise ApiError.conflict("Workspace slug is already taken")

    workspace = Workspace(name=payload.name, slug=payload.slug)
    db.add(workspace)
    db.flush()
    db.add(
        WorkspaceMembership(
            workspace_id=workspace.id, user_id=user.id, role=WorkspaceRole.owner
        )
    )
    record_event(
        db,
        action="workspace.created",
        actor_user_id=user.id,
        resource_type="workspace",
        resource_id=workspace.id,
        workspace_id=workspace.id,
    )
    db.commit()
    db.refresh(workspace)
    return WorkspaceOut(
        id=workspace.id, name=workspace.name, slug=workspace.slug, role=WorkspaceRole.owner
    )
