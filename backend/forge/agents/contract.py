"""The agent contract.

Per spec 04_AGENT_SYSTEM, every agent declares a fixed set of properties. Encoding the
contract as a frozen dataclass (rather than hard-coding one-off workflows) makes agents a
*reusable framework*: new agents — including dynamically instantiated ones — are just new
:class:`Agent` values that inherit the same validation, permission, budget, and
verification machinery.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from forge.agents.context import AgentContext


class BudgetExceeded(Exception):
    """Raised when an agent's resource budget is exceeded mid-execution."""


class VerificationError(Exception):
    """Raised when an agent's output fails its verification contract."""


class AgentNotRunnable(Exception):
    """Raised when a spec-only agent (no executor yet) is invoked."""


@dataclass(frozen=True)
class AgentBudget:
    """Resource ceiling for a single agent execution. ``None`` means unlimited."""

    max_usd: float | None = None
    max_tokens: int | None = None
    max_seconds: float | None = None


@dataclass(frozen=True)
class VerificationCheck:
    """One named check in a verification contract."""

    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


# An executor turns an assembled context into an outputs dict (or raises to fail).
Executor = Callable[["AgentContext"], "dict | None"]
# A verifier returns extra checks beyond the automatic output-schema check.
Verifier = Callable[["AgentContext", dict], "list[VerificationCheck]"]


@dataclass(frozen=True)
class Agent:
    """A specialized agent definition (identity + contract + optional executor)."""

    key: str
    role: str
    objective: str
    input_schema: dict = field(default_factory=lambda: {"type": "object"})
    output_schema: dict = field(default_factory=lambda: {"type": "object"})
    # Least-privilege: the set of tool names this agent may use (enforced once tools exist).
    allowed_tools: frozenset[str] = frozenset()
    # Which class of model the router should pick (populated by the model runtime later).
    model_policy: dict = field(default_factory=dict)
    budget: AgentBudget = field(default_factory=AgentBudget)
    timeout_seconds: float | None = None
    max_attempts: int = 3
    escalation_target: str | None = None
    # A spec-only agent has execute=None: its contract is declared but it cannot run yet.
    execute: Executor | None = None
    verify: Verifier | None = None

    @property
    def runnable(self) -> bool:
        return self.execute is not None
