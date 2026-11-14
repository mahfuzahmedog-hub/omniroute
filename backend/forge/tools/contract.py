"""The tool contract (spec 06_TOOL_SYSTEM).

A tool is a controlled capability. Encoding the contract as a frozen dataclass mirrors the
agent framework (ADR-0005): every tool declares its name/description/version, input and
output JSON schemas, the *permission* (capability) a project must grant, a timeout, a cost
class, its side-effect class, whether it needs network egress, whether it is gated behind a
human approval, which argument keys must be redacted from audit logs, and whether it is
safe to retry. Tools are **denied by default**; the runtime enforces the contract
uniformly so new tools inherit the same permission, validation, approval, and audit
machinery for free.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from forge.tools.runtime import ToolInvocationContext


class ToolError(Exception):
    """Base class for tool-runtime failures."""


class ToolNotFound(ToolError):
    """Raised when a tool name is not registered."""


class ToolNotRunnable(ToolError):
    """Raised when a declared-but-not-yet-implemented tool (no handler) is invoked."""


class PermissionDenied(ToolError):
    """Raised when the project (or agent) has not been granted the tool's capability."""


class ApprovalRequired(ToolError):
    """Raised when a destructive/production tool call lacks a human approval gate."""


class ToolTimeout(ToolError):
    """Raised when a tool exceeds its declared timeout."""


class NetworkEgressDenied(ToolError):
    """Raised when a tool attempts network egress to a non-allow-listed host."""


class PathEscapesWorkspace(ToolError):
    """Raised when a filesystem path resolves outside the project's workspace jail."""


class SandboxUnavailable(ToolError):
    """Raised when command execution is requested but no controlled sandbox is available."""


class CostClass(StrEnum):
    """Relative cost of a tool call, used later by the cost engine (Phase 15/20)."""

    free = "free"
    low = "low"
    medium = "medium"
    high = "high"


class SideEffect(StrEnum):
    """How a tool affects state. Destructive tools are approval-gated by default."""

    none = "none"  # no observable state change (e.g. a pure computation)
    read = "read"  # reads state (filesystem/network/db) but does not mutate it
    write = "write"  # creates or modifies state
    destructive = "destructive"  # deletes/overwrites or acts on production


# A handler receives a validated invocation context and returns an outputs dict, or raises.
ToolHandler = Callable[["ToolInvocationContext"], dict]


@dataclass(frozen=True)
class ToolSpec:
    """A tool definition: identity + contract + optional handler.

    A spec with ``handler=None`` is *declared but not runnable* — its contract, permission,
    and metadata are real and queryable, but invoking it fails loudly. This mirrors the
    Phase 3 roster: nothing fake is presented as working.
    """

    name: str
    description: str
    # The capability a project must grant for this tool to run (see permissions.Capability).
    permission: str
    version: str = "1.0.0"
    input_schema: dict = field(default_factory=lambda: {"type": "object"})
    output_schema: dict = field(default_factory=lambda: {"type": "object"})
    timeout_seconds: float = 30.0
    cost_class: CostClass = CostClass.low
    side_effect: SideEffect = SideEffect.read
    requires_network: bool = False
    # Explicit approval requirement, independent of side effect (e.g. production actions).
    requires_approval: bool = False
    # Argument keys whose values must never be written to the audit trail verbatim.
    redact_keys: frozenset[str] = frozenset()
    retryable: bool = True
    handler: ToolHandler | None = None

    @property
    def runnable(self) -> bool:
        return self.handler is not None

    @property
    def approval_gated(self) -> bool:
        """A tool needs a human approval gate if it is destructive or explicitly flagged."""
        return self.requires_approval or self.side_effect is SideEffect.destructive
