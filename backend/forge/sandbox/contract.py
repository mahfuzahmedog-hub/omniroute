"""Sandbox contract: lifecycle status, resource limits, reproducibility, errors."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


class SandboxError(Exception):
    """Base class for sandbox failures."""


class SandboxUnavailable(SandboxError):
    """Raised when a requested sandbox backend cannot be provisioned (e.g. no daemon)."""


class SandboxStatus(enum.StrEnum):
    """Lifecycle state of a sandbox (spec 07_SANDBOX: provision → … → reset/destroy)."""

    created = "created"
    provisioning = "provisioning"
    ready = "ready"
    executing = "executing"
    error = "error"
    destroyed = "destroyed"


@dataclass(frozen=True)
class ResourceLimits:
    """Bounds on a sandbox's resource usage.

    The container backend enforces these at the OS level. The local backend can only
    enforce wall-clock time (via per-command timeouts); the rest are *declared* and recorded
    for reproducibility until a container sandbox runs the workload.
    """

    cpus: float = 1.0
    memory_mb: int = 2048
    disk_mb: int = 4096
    max_pids: int = 256
    wall_seconds: int = 1800
    network_kbps: int | None = None
    max_browser_sessions: int = 1

    def to_dict(self) -> dict:
        return {
            "cpus": self.cpus,
            "memory_mb": self.memory_mb,
            "disk_mb": self.disk_mb,
            "max_pids": self.max_pids,
            "wall_seconds": self.wall_seconds,
            "network_kbps": self.network_kbps,
            "max_browser_sessions": self.max_browser_sessions,
        }


@dataclass
class ReproducibilityInfo:
    """What is needed to reproduce a sandbox (spec 07_SANDBOX: Reproducibility).

    Environment variables are recorded *by reference* (their names), never their values, so
    secrets are never captured in reproducibility metadata.
    """

    runtime: str
    runtime_versions: dict[str, str] = field(default_factory=dict)
    setup_commands: list[str] = field(default_factory=list)
    env_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "runtime": self.runtime,
            "runtime_versions": self.runtime_versions,
            "setup_commands": list(self.setup_commands),
            "env_refs": list(self.env_refs),
        }
