"""Tool catalog, capability grants, and invocation routes.

The catalog (``/tools``) is the read-only registry of tool contracts. Grants and
invocations are workspace/project scoped: a project explicitly grants capabilities
(denied by default), and every tool call — from the API or from an agent — leaves a
durable, auditable :class:`ToolInvocation`.
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
from forge.core.errors import ApiError, ErrorCode
from forge.core.pagination import Page, PageParams, page_params
from forge.models.project import Project
from forge.models.tool import ProjectToolGrant, ToolInvocation
from forge.schemas.tools import (
    ToolGrantIn,
    ToolGrantOut,
    ToolInvocationOut,
    ToolInvokeIn,
    ToolInvokeOut,
    ToolOut,
)
from forge.services.audit import record_event
from forge.tools.contract import (
    ApprovalRequired,
    PermissionDenied,
    ToolNotFound,
    ToolNotRunnable,
    ToolSpec,
)
from forge.tools.permissions import is_valid_capability
from forge.tools.registry import registry as tool_registry
from forge.tools.runtime import SchemaError, ToolError, ToolRuntime

catalog_router = APIRouter(prefix="/tools", tags=["tools"])
project_router = APIRouter(
    prefix="/workspaces/{workspace_id}/projects/{project_id}", tags=["tools"]
)


def _to_out(spec: ToolSpec) -> ToolOut:
    return ToolOut(
        name=spec.name,
        description=spec.description,
        permission=spec.permission,
        version=spec.version,
        cost_class=spec.cost_class.value,
        side_effect=spec.side_effect.value,
        requires_network=spec.requires_network,
        approval_gated=spec.approval_gated,
        runnable=spec.runnable,
        timeout_seconds=spec.timeout_seconds,
        input_schema=spec.input_schema,
        output_schema=spec.output_schema,
    )


@catalog_router.get("", response_model=list[ToolOut])
def list_tools(_user: CurrentUser) -> list[ToolOut]:
    """List every tool contract in the registry."""
    return [_to_out(s) for s in tool_registry.all()]


@catalog_router.get("/{name}", response_model=ToolOut)
def get_tool(name: str, _user: CurrentUser) -> ToolOut:
    spec = tool_registry.get(name)
    if spec is None:
        raise ApiError.not_found("Tool not found")
    return _to_out(spec)


def _get_project(db: DbSession, workspace_id: uuid.UUID, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.workspace_id != workspace_id:
        raise ApiError.not_found("Project not found")
    return project


@project_router.get("/tool-grants", response_model=list[ToolGrantOut])
def list_tool_grants(
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
) -> list[ToolGrantOut]:
    require_workspace_membership(workspace_id, db, user)
    _get_project(db, workspace_id, project_id)
    grants = db.scalars(
        select(ProjectToolGrant)
        .where(ProjectToolGrant.project_id == project_id)
        .order_by(ProjectToolGrant.permission.asc())
    ).all()
    return [ToolGrantOut.model_validate(g) for g in grants]


@project_router.put("/tool-grants/{permission}", response_model=ToolGrantOut)
def grant_capability(
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    permission: str,
    payload: ToolGrantIn,
    user: CurrentUser,
    db: DbSession,
) -> ToolGrantOut:
    membership = require_workspace_membership(workspace_id, db, user)
    require_workspace_write(membership)
    _get_project(db, workspace_id, project_id)
    if not is_valid_capability(permission):
        raise ApiError(
            ErrorCode.validation_error,
            f"Unknown capability '{permission}'",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    grant = db.scalar(
        select(ProjectToolGrant).where(
            ProjectToolGrant.project_id == project_id,
            ProjectToolGrant.permission == permission,
        )
    )
    created = grant is None
    if grant is None:
        grant = ProjectToolGrant(project_id=project_id, permission=permission)
        db.add(grant)
    grant.auto_approve = payload.auto_approve
    grant.allowed_hosts = payload.allowed_hosts
    record_event(
        db,
        action="tool_grant.created" if created else "tool_grant.updated",
        actor_user_id=user.id,
        resource_type="project",
        resource_id=project_id,
        workspace_id=workspace_id,
        metadata={"permission": permission, "auto_approve": payload.auto_approve},
    )
    db.commit()
    db.refresh(grant)
    return ToolGrantOut.model_validate(grant)


@project_router.delete("/tool-grants/{permission}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_capability(
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    permission: str,
    user: CurrentUser,
    db: DbSession,
) -> None:
    membership = require_workspace_membership(workspace_id, db, user)
    require_workspace_write(membership)
    _get_project(db, workspace_id, project_id)
    grant = db.scalar(
        select(ProjectToolGrant).where(
            ProjectToolGrant.project_id == project_id,
            ProjectToolGrant.permission == permission,
        )
    )
    if grant is None:
        raise ApiError.not_found("Grant not found")
    db.delete(grant)
    record_event(
        db,
        action="tool_grant.revoked",
        actor_user_id=user.id,
        resource_type="project",
        resource_id=project_id,
        workspace_id=workspace_id,
        metadata={"permission": permission},
    )
    db.commit()


@project_router.get("/tool-invocations", response_model=Page[ToolInvocationOut])
def list_tool_invocations(
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    params: Annotated[PageParams, Depends(page_params)],
) -> Page[ToolInvocationOut]:
    require_workspace_membership(workspace_id, db, user)
    _get_project(db, workspace_id, project_id)
    total = db.scalar(
        select(func.count(ToolInvocation.id)).where(ToolInvocation.project_id == project_id)
    )
    invocations = db.scalars(
        select(ToolInvocation)
        .where(ToolInvocation.project_id == project_id)
        .order_by(ToolInvocation.created_at.desc())
        .limit(params.limit)
        .offset(params.offset)
    ).all()
    return Page[ToolInvocationOut](
        items=[ToolInvocationOut.model_validate(i) for i in invocations],
        total=total or 0,
        limit=params.limit,
        offset=params.offset,
    )


# Maps tool-runtime exceptions to stable API errors.
def _raise_api_error(exc: ToolError) -> None:
    if isinstance(exc, ToolNotFound):
        raise ApiError.not_found(str(exc)) from None
    if isinstance(exc, PermissionDenied):
        raise ApiError.forbidden(str(exc)) from None
    if isinstance(exc, SchemaError):
        raise ApiError(
            ErrorCode.validation_error,
            str(exc),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        ) from None
    if isinstance(exc, ApprovalRequired | ToolNotRunnable):
        raise ApiError.conflict(str(exc)) from None
    # Egress denied, sandbox unavailable, timeout, or a handler failure.
    raise ApiError.conflict(str(exc)) from None


@project_router.post("/tools/{name}/invoke", response_model=ToolInvokeOut)
def invoke_tool(
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    name: str,
    payload: ToolInvokeIn,
    user: CurrentUser,
    db: DbSession,
) -> ToolInvokeOut:
    membership = require_workspace_membership(workspace_id, db, user)
    require_workspace_write(membership)
    project = _get_project(db, workspace_id, project_id)
    runtime = ToolRuntime(db)
    try:
        result = runtime.invoke(name, payload.args, project=project, approved=payload.approved)
    except ToolError as exc:
        _raise_api_error(exc)
    return ToolInvokeOut(
        invocation_id=result.invocation.id,
        tool=name,
        status=str(result.invocation.status),
        outputs=result.outputs,
        duration_ms=result.invocation.duration_ms,
    )
