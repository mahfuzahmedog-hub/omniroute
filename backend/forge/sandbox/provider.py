"""Sandbox provider: selects a backend and hands out sandboxes per project.

The provider is the single place that decides *which* isolation backend a project gets. It
prefers the container sandbox when the operator asks for it and a Docker daemon is
available, and otherwise falls back to the local workspace sandbox. The tool runtime uses
:meth:`environment_for` so it never has to know which backend it is talking to.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from forge.config import Settings, get_settings
from forge.sandbox.contract import ResourceLimits
from forge.sandbox.docker import DockerSandbox
from forge.sandbox.local import LocalSandbox
from forge.tools.sandbox import EgressPolicy, ExecutionEnvironment


class SandboxProvider:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def _project_root(self, project_id: uuid.UUID | str) -> Path:
        return Path(self._settings.workspaces_root) / str(project_id)

    def use_container(self) -> bool:
        """Whether the container backend should be used, honoring config + availability."""
        backend = self._settings.sandbox_backend
        if backend == "docker":
            return True
        if backend == "local":
            return False
        # "auto": use the container sandbox only if a daemon is actually reachable.
        return DockerSandbox.available()

    def get(
        self,
        project_id: uuid.UUID | str,
        *,
        egress: EgressPolicy | None = None,
        limits: ResourceLimits | None = None,
    ) -> LocalSandbox | DockerSandbox:
        if self.use_container():
            return DockerSandbox(str(project_id), limits=limits)
        sandbox = LocalSandbox(
            str(project_id),
            self._project_root(project_id),
            egress=egress,
            commands_enabled=self._settings.local_command_execution_enabled,
            limits=limits,
        )
        sandbox.provision()
        return sandbox

    def environment_for(
        self, project_id: uuid.UUID | str, *, egress: EgressPolicy | None = None
    ) -> ExecutionEnvironment:
        """Return a ready execution environment for ``project_id`` (used by the tool runtime)."""
        return self.get(project_id, egress=egress).environment
