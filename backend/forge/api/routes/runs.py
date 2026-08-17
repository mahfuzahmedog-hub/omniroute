"""Run + task control routes (workspace/project scoped).

These endpoints let a client build and control the durable task graph: create a run,
add tasks with dependencies, start it, inspect progress, and cancel it. Actual execution
is performed out of band by workers (``forge.orchestration.worker``) draining the queue.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select

from forge.core.deps import (
    CurrentUser,
    DbSession,
    require_workspace_membership,
    require_workspace_write,
)
from forge.core.errors import ApiError
from forge.core.pagination import Page, PageParams, page_params
from forge.models.project import Project
from forge.models.run import Run, RunStatus
from forge.models.task import Task
from forge.orchestration import service
from forge.orchestration.state import InvalidTransition
from forge.schemas.orchestration import RunCreate, RunOut, TaskCreate, TaskOut

router = APIRouter(prefix="/workspaces/{workspace_id}/projects/{project_id}", tags=["runs"])


def _get_project(db: DbSession, workspace_id: uuid.UUID, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.workspace_id != workspace_id:
        raise ApiError.not_found("Project not found")
    return project


def _get_run(db: DbSession, project_id: uuid.UUID, run_id: uuid.UUID) -> Run:
    run = db.get(Run, run_id)
    if run is None or run.project_id != project_id:
        raise ApiError.not_found("Run not found")
    return run


@router.post("/runs", response_model=RunOut, status_code=status.HTTP_201_CREATED)
def create_run(
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    payload: RunCreate,
    user: CurrentUser,
    db: DbSession,
) -> RunOut:
    membership = require_workspace_membership(workspace_id, db, user)
    require_workspace_write(membership)
    _get_project(db, workspace_id, project_id)
    run = service.create_run(
        db,
        project_id=project_id,
        name=payload.name,
        actor_user_id=user.id,
        workspace_id=workspace_id,
    )
    return RunOut.model_validate(run)


@router.get("/runs", response_model=Page[RunOut])
def list_runs(
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    params: Annotated[PageParams, Depends(page_params)],
) -> Page[RunOut]:
    require_workspace_membership(workspace_id, db, user)
    _get_project(db, workspace_id, project_id)

    total = db.scalar(select(func.count(Run.id)).where(Run.project_id == project_id))
    runs = db.scalars(
        select(Run)
        .where(Run.project_id == project_id)
        .order_by(Run.created_at.desc())
        .limit(params.limit)
        .offset(params.offset)
    ).all()
    return Page[RunOut](
        items=[RunOut.model_validate(r) for r in runs],
        total=total or 0,
        limit=params.limit,
        offset=params.offset,
    )


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
) -> RunOut:
    require_workspace_membership(workspace_id, db, user)
    _get_project(db, workspace_id, project_id)
    return RunOut.model_validate(_get_run(db, project_id, run_id))


@router.post("/runs/{run_id}/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def add_task(
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    payload: TaskCreate,
    user: CurrentUser,
    db: DbSession,
) -> TaskOut:
    membership = require_workspace_membership(workspace_id, db, user)
    require_workspace_write(membership)
    _get_project(db, workspace_id, project_id)
    run = _get_run(db, project_id, run_id)
    try:
        task = service.add_task(
            db,
            run=run,
            name=payload.name,
            kind=payload.kind,
            inputs=payload.inputs,
            priority=payload.priority,
            max_attempts=payload.max_attempts,
            depends_on=payload.depends_on,
            actor_user_id=user.id,
            workspace_id=workspace_id,
        )
    except ValueError as exc:
        raise ApiError.conflict(str(exc)) from None
    return TaskOut.model_validate(task)


@router.get("/runs/{run_id}/tasks", response_model=list[TaskOut])
def list_tasks(
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
) -> list[TaskOut]:
    require_workspace_membership(workspace_id, db, user)
    _get_project(db, workspace_id, project_id)
    _get_run(db, project_id, run_id)
    tasks = db.scalars(
        select(Task).where(Task.run_id == run_id).order_by(Task.created_at.asc())
    ).all()
    return [TaskOut.model_validate(t) for t in tasks]


@router.post("/runs/{run_id}/start", response_model=RunOut)
def start_run(
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
) -> RunOut:
    membership = require_workspace_membership(workspace_id, db, user)
    require_workspace_write(membership)
    _get_project(db, workspace_id, project_id)
    run = _get_run(db, project_id, run_id)
    if run.status != RunStatus.pending:
        raise ApiError.conflict("Run has already started")
    try:
        service.start_run(db, run, actor_user_id=user.id, workspace_id=workspace_id)
    except InvalidTransition as exc:
        raise ApiError.conflict(str(exc)) from None
    return RunOut.model_validate(run)


@router.post("/runs/{run_id}/cancel", response_model=RunOut)
def cancel_run(
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
) -> RunOut:
    membership = require_workspace_membership(workspace_id, db, user)
    require_workspace_write(membership)
    _get_project(db, workspace_id, project_id)
    run = _get_run(db, project_id, run_id)
    service.cancel_run(db, run, actor_user_id=user.id, workspace_id=workspace_id)
    return RunOut.model_validate(run)
