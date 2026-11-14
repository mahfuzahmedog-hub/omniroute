"""Forge tool runtime (Phase 4).

Tools are the controlled capabilities an agent (Phase 3) is allowed to use. This package
provides the tool *contract*, a *registry* of tool specifications, a policy-controlled
*execution environment*, and a *runtime* that enforces least-privilege permissions,
argument/output validation, human-approval gates for destructive operations, and a durable
structured audit of every call.

See spec ``06_TOOL_SYSTEM`` and ADR-0006.
"""

from forge.tools.contract import (
    ApprovalRequired,
    CostClass,
    NetworkEgressDenied,
    PathEscapesWorkspace,
    PermissionDenied,
    SandboxUnavailable,
    SideEffect,
    ToolError,
    ToolNotRunnable,
    ToolSpec,
    ToolTimeout,
)
from forge.tools.registry import ToolRegistry, registry
from forge.tools.runtime import ToolInvocationContext, ToolRuntime

__all__ = [
    "ToolSpec",
    "CostClass",
    "SideEffect",
    "ToolError",
    "ToolNotRunnable",
    "PermissionDenied",
    "ApprovalRequired",
    "ToolTimeout",
    "NetworkEgressDenied",
    "PathEscapesWorkspace",
    "SandboxUnavailable",
    "ToolRegistry",
    "registry",
    "ToolRuntime",
    "ToolInvocationContext",
]
