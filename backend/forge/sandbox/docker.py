"""The container sandbox backend (requires Docker).

Full process/network/resource isolation needs a container runtime. `DockerSandbox` targets
a Docker daemon; when none is reachable it raises :class:`SandboxUnavailable` rather than
pretending to isolate anything — the same honest posture as the declared-only tools.

The intended lifecycle maps directly onto the Docker CLI:

- **provision** → ``docker run -d`` a long-lived container from the project's image with
  ``--cpus``/``--memory``/``--pids-limit`` from :class:`ResourceLimits`, ``--network`` bound
  to the project's egress policy, and the workspace bind-mounted.
- **initialize** → ``docker exec`` the setup commands.
- **snapshot** → ``docker commit`` (or an archive of the workspace volume).
- **reset** → recreate the container from a snapshot image / re-extract the volume.
- **destroy** → ``docker rm -f`` the container.

Wiring these commands is deferred until a Docker daemon is available in the build/runtime
environment; this class is the seam they slot into.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Sequence

from forge.sandbox.base import Sandbox
from forge.sandbox.contract import (
    ReproducibilityInfo,
    ResourceLimits,
    SandboxStatus,
    SandboxUnavailable,
)
from forge.tools.sandbox import CommandResult, ExecutionEnvironment


class DockerSandbox(Sandbox):
    def __init__(self, project_id: str, *, limits: ResourceLimits | None = None) -> None:
        self.project_id = str(project_id)
        self.limits = limits or ResourceLimits()
        self.status = SandboxStatus.created
        if not self.available():
            raise SandboxUnavailable(
                "Docker daemon is not available; the container sandbox cannot be "
                "provisioned in this environment"
            )

    @staticmethod
    def available() -> bool:
        """Return True only if a Docker daemon is reachable."""
        if shutil.which("docker") is None:
            return False
        try:
            proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
                ["docker", "info"],
                capture_output=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return proc.returncode == 0

    @property
    def environment(self) -> ExecutionEnvironment:  # pragma: no cover - unreachable w/o daemon
        raise SandboxUnavailable("container sandbox is not provisioned")

    def provision(self) -> None:  # pragma: no cover - requires a daemon
        raise SandboxUnavailable("Docker daemon is not available")

    def initialize(  # pragma: no cover - requires a daemon
        self, setup_commands: Sequence[str] = ()
    ) -> list[CommandResult]:
        raise SandboxUnavailable("Docker daemon is not available")

    def snapshot(self, label: str = "") -> str:  # pragma: no cover - requires a daemon
        raise SandboxUnavailable("Docker daemon is not available")

    def reset(self, snapshot_id: str | None = None) -> None:  # pragma: no cover
        raise SandboxUnavailable("Docker daemon is not available")

    def destroy(self) -> None:  # pragma: no cover - requires a daemon
        raise SandboxUnavailable("Docker daemon is not available")

    def reproducibility(self) -> ReproducibilityInfo:  # pragma: no cover - requires a daemon
        raise SandboxUnavailable("Docker daemon is not available")
