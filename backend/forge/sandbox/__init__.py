"""Forge sandbox (Phase 5).

The sandbox is the isolated, reproducible environment where agents build and test software
(spec 07_SANDBOX). It owns the lifecycle — provision → initialize → execute → checkpoint →
reset/destroy — and wraps a Phase 4 :class:`~forge.tools.sandbox.ExecutionEnvironment`,
which provides the actual jailed execution primitive.

Two backends implement the same :class:`Sandbox` interface:

- :class:`~forge.sandbox.local.LocalSandbox` — a path-jailed local workspace with
  snapshot/reset. This is the default in development and the environment tools run in today.
- :class:`~forge.sandbox.docker.DockerSandbox` — a container-backed sandbox for full
  process/network/resource isolation. It requires a running Docker daemon and fails loudly
  when one is not available (nothing fake is presented as isolated).
"""

from forge.sandbox.contract import (
    ReproducibilityInfo,
    ResourceLimits,
    SandboxError,
    SandboxStatus,
    SandboxUnavailable,
)
from forge.sandbox.local import LocalSandbox
from forge.sandbox.provider import SandboxProvider

__all__ = [
    "SandboxStatus",
    "ResourceLimits",
    "ReproducibilityInfo",
    "SandboxError",
    "SandboxUnavailable",
    "LocalSandbox",
    "SandboxProvider",
]
