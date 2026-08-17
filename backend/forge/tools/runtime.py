"""The tool runtime — uniform enforcement for every tool call.

A single :meth:`ToolRuntime.invoke` path enforces the whole contract in order:

1. **Resolve** the tool from the registry.
2. **Authorize** — deny by default: the project must have granted the tool's capability,
   and if an agent is calling, the capability must also be in the agent's least-privilege
   ``allowed_tools`` set.
3. **Validate** arguments against the tool's input JSON schema.
4. **Approval gate** — destructive/flagged tools need either an auto-approving grant or an
   explicit per-call approval, else the call is refused (the human-approval subsystem
   arrives in Phase 12; this is the enforcement point it will drive).
5. **Execute** inside the controlled environment (filesystem jail + egress policy), timed.
6. **Validate** outputs against the tool's output JSON schema.

Every call — including denials — is recorded as a durable :class:`ToolInvocation` with
redacted argument metadata and a compact result summary, plus an :class:`AuditEvent`, so
autonomous tool use is fully auditable and secrets never land in the logs.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import jsonschema
from sqlalchemy import select
from sqlalchemy.orm import Session

from forge.agents.contract import Agent
from forge.config import Settings, get_settings
from forge.models.base import utcnow
from forge.models.project import Project
from forge.models.tool import ProjectToolGrant, ToolInvocation, ToolInvocationStatus
from forge.services.audit import record_event
from forge.tools.contract import (
    ApprovalRequired,
    PermissionDenied,
    SideEffect,
    ToolError,
    ToolNotFound,
    ToolNotRunnable,
    ToolSpec,
)
from forge.tools.registry import ToolRegistry
from forge.tools.registry import registry as default_registry
from forge.tools.sandbox import EgressPolicy, ExecutionEnvironment, LocalWorkspaceEnvironment

_MAX_STR = 200
_MAX_ITEMS = 20


@dataclass
class ToolInvocationContext:
    """What a tool handler receives: validated args + the controlled environment."""

    spec: ToolSpec
    args: dict
    env: ExecutionEnvironment
    timeout_seconds: float

    @property
    def egress(self) -> EgressPolicy:
        return self.env.egress


@dataclass
class ToolResult:
    """Return value of :meth:`ToolRuntime.invoke`: full outputs + the durable record."""

    outputs: dict
    invocation: ToolInvocation


class SchemaError(ToolError):
    """Raised when tool arguments or outputs violate their JSON schema."""


def _summarize(value: object, *, max_str: int = _MAX_STR) -> object:
    """Shrink a value for audit storage: truncate long strings, cap collections."""
    if isinstance(value, str):
        if len(value) > max_str:
            return value[:max_str] + f"...(+{len(value) - max_str} chars)"
        return value
    if isinstance(value, bool | int | float) or value is None:
        return value
    if isinstance(value, list):
        summarized = [_summarize(v, max_str=max_str) for v in value[:_MAX_ITEMS]]
        if len(value) > _MAX_ITEMS:
            summarized.append(f"...(+{len(value) - _MAX_ITEMS} items)")
        return summarized
    if isinstance(value, dict):
        return {k: _summarize(v, max_str=max_str) for k, v in list(value.items())[:50]}
    return str(value)[:max_str]


def _redact_args(spec: ToolSpec, args: dict) -> dict:
    """Produce argument *metadata*: redacted secrets, truncated values."""
    out: dict = {}
    for key, value in args.items():
        if key in spec.redact_keys:
            out[key] = "***"
        else:
            out[key] = _summarize(value)
    return out


class ToolRuntime:
    """Executes tools with permission, validation, approval, and audit enforcement."""

    def __init__(
        self,
        db: Session,
        *,
        registry: ToolRegistry = default_registry,
        settings: Settings | None = None,
    ) -> None:
        self._db = db
        self._registry = registry
        self._settings = settings or get_settings()

    # -- environment -------------------------------------------------------
    def _project_root(self, project_id: uuid.UUID) -> Path:
        return Path(self._settings.workspaces_root) / str(project_id)

    def environment_for(
        self, project_id: uuid.UUID, *, egress: EgressPolicy | None = None
    ) -> LocalWorkspaceEnvironment:
        return LocalWorkspaceEnvironment(
            self._project_root(project_id),
            egress=egress,
            commands_enabled=self._settings.local_command_execution_enabled,
        )

    # -- authorization -----------------------------------------------------
    def _grant(self, project_id: uuid.UUID, permission: str) -> ProjectToolGrant | None:
        return self._db.scalar(
            select(ProjectToolGrant).where(
                ProjectToolGrant.project_id == project_id,
                ProjectToolGrant.permission == permission,
            )
        )

    # -- recording ---------------------------------------------------------
    def _record(
        self,
        *,
        project: Project,
        spec: ToolSpec,
        args: dict,
        run_id: uuid.UUID | None,
        task_id: uuid.UUID | None,
        agent_key: str | None,
    ) -> ToolInvocation:
        invocation = ToolInvocation(
            project_id=project.id,
            run_id=run_id,
            task_id=task_id,
            agent_key=agent_key,
            tool_name=spec.name,
            tool_version=spec.version,
            permission=spec.permission,
            status=ToolInvocationStatus.running,
            side_effect=spec.side_effect.value,
            cost_class=spec.cost_class.value,
            args_metadata=_redact_args(spec, args),
            started_at=utcnow(),
        )
        self._db.add(invocation)
        self._db.flush()
        return invocation

    def _settle(
        self,
        invocation: ToolInvocation,
        *,
        project: Project,
        status: ToolInvocationStatus,
        outputs: dict | None = None,
        error: str | None = None,
        duration_ms: int | None = None,
    ) -> None:
        invocation.status = status
        invocation.error = error
        invocation.duration_ms = duration_ms
        if outputs is not None:
            invocation.result_summary = _summarize(outputs)
        if status is not ToolInvocationStatus.running:
            invocation.finished_at = utcnow()
        action = {
            ToolInvocationStatus.succeeded: "tool.succeeded",
            ToolInvocationStatus.failed: "tool.failed",
            ToolInvocationStatus.denied: "tool.denied",
            ToolInvocationStatus.approval_required: "tool.approval_required",
        }.get(status, "tool.invoked")
        record_event(
            self._db,
            action=action,
            actor_type="agent" if invocation.agent_key else "system",
            resource_type="tool_invocation",
            resource_id=invocation.id,
            workspace_id=project.workspace_id,
            metadata={
                "tool": invocation.tool_name,
                "permission": invocation.permission,
                "status": status.value,
            },
        )
        self._db.commit()

    # -- main entrypoint ---------------------------------------------------
    def invoke(
        self,
        name: str,
        args: dict | None = None,
        *,
        project: Project,
        run_id: uuid.UUID | None = None,
        task_id: uuid.UUID | None = None,
        agent: Agent | None = None,
        approved: bool = False,
    ) -> ToolResult:
        args = dict(args or {})
        spec = self._registry.get(name)
        if spec is None:
            raise ToolNotFound(f"unknown tool '{name}'")

        agent_key = agent.key if agent is not None else None
        invocation = self._record(
            project=project,
            spec=spec,
            args=args,
            run_id=run_id,
            task_id=task_id,
            agent_key=agent_key,
        )

        # 2. Authorize — deny by default (project grant + agent least-privilege).
        grant = self._grant(project.id, spec.permission)
        if grant is None:
            self._settle(
                invocation,
                project=project,
                status=ToolInvocationStatus.denied,
                error=f"capability '{spec.permission}' is not granted to this project",
            )
            raise PermissionDenied(invocation.error)
        if agent is not None and spec.permission not in agent.allowed_tools:
            self._settle(
                invocation,
                project=project,
                status=ToolInvocationStatus.denied,
                error=f"agent '{agent.key}' is not permitted to use '{spec.permission}'",
            )
            raise PermissionDenied(invocation.error)

        # 3. Validate arguments.
        try:
            jsonschema.validate(instance=args, schema=spec.input_schema)
        except jsonschema.ValidationError as exc:
            self._settle(
                invocation,
                project=project,
                status=ToolInvocationStatus.failed,
                error=f"input schema: {exc.message}",
            )
            raise SchemaError(exc.message) from None

        # 4. Approval gate for destructive/flagged tools.
        if spec.approval_gated and not approved and not grant.auto_approve:
            self._settle(
                invocation,
                project=project,
                status=ToolInvocationStatus.approval_required,
                error="this action requires human approval",
            )
            raise ApprovalRequired(f"tool '{spec.name}' requires approval")

        # 5. Runnability + execution inside the controlled environment.
        if not spec.runnable:
            self._settle(
                invocation,
                project=project,
                status=ToolInvocationStatus.failed,
                error="tool has no implementation yet (declared contract only)",
            )
            raise ToolNotRunnable(spec.name)

        egress = EgressPolicy(frozenset(grant.allowed_hosts or []))
        env = self.environment_for(project.id, egress=egress)
        ctx = ToolInvocationContext(
            spec=spec, args=args, env=env, timeout_seconds=spec.timeout_seconds
        )

        started = time.perf_counter()
        try:
            outputs = spec.handler(ctx) or {}  # type: ignore[misc]
        except ToolError as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            self._settle(
                invocation,
                project=project,
                status=ToolInvocationStatus.failed,
                error=str(exc),
                duration_ms=duration_ms,
            )
            raise
        except Exception as exc:  # noqa: BLE001 - recorded, then wrapped for the caller
            duration_ms = int((time.perf_counter() - started) * 1000)
            self._settle(
                invocation,
                project=project,
                status=ToolInvocationStatus.failed,
                error=str(exc),
                duration_ms=duration_ms,
            )
            raise ToolError(f"{spec.name} failed: {exc}") from exc

        duration_ms = int((time.perf_counter() - started) * 1000)

        # 6. Validate outputs.
        try:
            jsonschema.validate(instance=outputs, schema=spec.output_schema)
        except jsonschema.ValidationError as exc:
            self._settle(
                invocation,
                project=project,
                status=ToolInvocationStatus.failed,
                error=f"output schema: {exc.message}",
                duration_ms=duration_ms,
            )
            raise SchemaError(exc.message) from None

        self._settle(
            invocation,
            project=project,
            status=ToolInvocationStatus.succeeded,
            outputs=outputs,
            duration_ms=duration_ms,
        )
        return ToolResult(outputs=outputs, invocation=invocation)


__all__ = [
    "ToolRuntime",
    "ToolInvocationContext",
    "ToolResult",
    "SchemaError",
    "SideEffect",
]
