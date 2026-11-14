"""The sandbox interface.

A :class:`Sandbox` owns an isolated environment's lifecycle. Concrete backends implement
provisioning, snapshotting, reset, and teardown; they all expose the same
:class:`~forge.tools.sandbox.ExecutionEnvironment` so the tool runtime (Phase 4) is
oblivious to which backend it is running in.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from forge.sandbox.contract import ReproducibilityInfo, ResourceLimits, SandboxStatus
from forge.tools.sandbox import CommandResult, ExecutionEnvironment


class Sandbox(ABC):
    """Lifecycle owner for one project's isolated environment."""

    project_id: str
    limits: ResourceLimits
    status: SandboxStatus

    @property
    @abstractmethod
    def environment(self) -> ExecutionEnvironment:
        """The jailed execution environment tools run inside. Valid once ``ready``."""

    @abstractmethod
    def provision(self) -> None:
        """Create the environment. Idempotent; leaves the sandbox ``ready``."""

    @abstractmethod
    def initialize(self, setup_commands: Sequence[str] = ()) -> list[CommandResult]:
        """Run one-time setup, recording the commands for reproducibility."""

    @abstractmethod
    def snapshot(self, label: str = "") -> str:
        """Capture the current state and return a snapshot id for later ``reset``."""

    @abstractmethod
    def reset(self, snapshot_id: str | None = None) -> None:
        """Restore a snapshot, or clear back to an empty workspace when ``None``."""

    @abstractmethod
    def destroy(self) -> None:
        """Tear down the environment and release its resources."""

    @abstractmethod
    def reproducibility(self) -> ReproducibilityInfo:
        """Return the information needed to reproduce this sandbox."""
