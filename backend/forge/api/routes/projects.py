"""Project routes: workspace-scoped CRUD with RBAC, pagination, and audit.

Every route resolves the caller's workspace membership first, so a user can never read
or mutate a project in a workspace they don't belong to. Updates support optimistic
concurrency via ``expected_version``.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.orm.exc import StaleDataError

from forge.core.deps import (
    CurrentUser,
    DbSession,
    require_workspace_membership,
    require_workspace_write,
)
from forge.core.errors import ApiError
from forge.core.pagination import Page, PageParams, page_params
from forge.models.project import Project
from forge.schemas.project import ProjectCreate, ProjectOut, ProjectUpdate
from forge.services.audit import record_event

router = APIRouter(prefix="/workspaces/{workspace_id}/projects", tags=["projects"])


def _get_owned_project(db: DbSession, workspace_id: uuid.UUID, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.workspace_id != workspace_id:
        raise ApiError.not_found("Project not found")
    return project


@router.get("", response_model=Page[ProjectOut])
def list_projects(
    workspace_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    params: Annotated[PageParams, Depends(page_params)],
) -> Page[ProjectOut]:
    """List projects in a workspace the caller belongs to (paginated)."""
    require_workspace_membership(workspace_id, db, user)

    total = db.scalar(
        select(func.count(Project.id)).where(Project.workspace_id == workspace_id)
    )
    projects = db.scalars(
        select(Project)
        .where(Project.workspace_id == workspace_id)
        .order_by(Project.created_at.desc())
        .limit(params.limit)
        .offset(params.offset)
    ).all()
    return Page[ProjectOut](
        items=[ProjectOut.model_validate(p) for p in projects],
        total=total or 0,
        limit=params.limit,
        offset=params.offset,
    )


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    workspace_id: uuid.UUID, payload: ProjectCreate, user: CurrentUser, db: DbSession
) -> ProjectOut:
    """Create a project. Requires a writer role in the workspace."""
    membership = require_workspace_membership(workspace_id, db, user)
    require_workspace_write(membership)

    exists = db.scalar(
        select(Project.id).where(
            Project.workspace_id == workspace_id, Project.slug == payload.slug
        )
    )
    if exists is not None:
        raise ApiError.conflict("A project with this slug already exists in the workspace")

    project = Project(
        workspace_id=workspace_id,
        name=payload.name,
        slug=payload.slug,
        specification=payload.specification,
    )
    db.add(project)
    db.flush()
    record_event(
        db,
        action="project.created",
        actor_user_id=user.id,
        resource_type="project",
        resource_id=project.id,
        workspace_id=workspace_id,
    )
    db.commit()
    db.refresh(project)
    return ProjectOut.model_validate(project)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    workspace_id: uuid.UUID, project_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> ProjectOut:
    require_workspace_membership(workspace_id, db, user)
    project = _get_owned_project(db, workspace_id, project_id)
    return ProjectOut.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    user: CurrentUser,
    db: DbSession,
) -> ProjectOut:
    """Update a project. Optional ``expected_version`` guards against lost updates."""
    membership = require_workspace_membership(workspace_id, db, user)
    require_workspace_write(membership)
    project = _get_owned_project(db, workspace_id, project_id)

    if payload.expected_version is not None and payload.expected_version != project.version:
        raise ApiError.conflict(
            "Project was modified by someone else",
            details={
                "expected_version": payload.expected_version,
                "actual_version": project.version,
            },
        )

    changed: dict[str, object] = {}
    if payload.name is not None:
        project.name = payload.name
        changed["name"] = payload.name
    if payload.specification is not None:
        project.specification = payload.specification
        changed["specification"] = "updated"
    if payload.status is not None:
        project.status = payload.status
        changed["status"] = payload.status.value

    record_event(
        db,
        action="project.updated",
        actor_user_id=user.id,
        resource_type="project",
        resource_id=project.id,
        workspace_id=workspace_id,
        metadata={"changed": list(changed.keys())},
    )
    try:
        db.commit()
    except StaleDataError:
        # A concurrent writer advanced the version between our read and write.
        db.rollback()
        raise ApiError.conflict("Project was modified concurrently; retry") from None
    db.refresh(project)
    return ProjectOut.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    workspace_id: uuid.UUID, project_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> None:
    """Delete a project. Requires a writer role in the workspace."""
    membership = require_workspace_membership(workspace_id, db, user)
    require_workspace_write(membership)
    project = _get_owned_project(db, workspace_id, project_id)
    db.delete(project)
    record_event(
        db,
        action="project.deleted",
        actor_user_id=user.id,
        resource_type="project",
        resource_id=project_id,
        workspace_id=workspace_id,
    )
    db.commit()
