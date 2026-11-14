"""The local, path-jailed sandbox backend.

`LocalSandbox` is the default development sandbox: a per-project workspace directory under
the configured workspaces root, wrapped by a Phase 4 :class:`LocalWorkspaceEnvironment`
(filesystem jail + egress policy). It implements snapshot/reset by tar-archiving the
workspace, so a run can checkpoint state and roll back after a bad step.

It does **not** isolate spawned subprocesses at the OS level — that is the container
sandbox's job. Command execution therefore follows the same ``local``/``development`` gate
as the tool runtime.
"""

from __future__ import annotations

import platform
import shutil
import sys
import tarfile
import uuid
from collections.abc import Sequence
from pathlib import Path

from forge.sandbox.base import Sandbox
from forge.sandbox.contract import (
    ReproducibilityInfo,
    ResourceLimits,
    SandboxError,
    SandboxStatus,
)
from forge.tools.sandbox import CommandResult, EgressPolicy, LocalWorkspaceEnvironment


class LocalSandbox(Sandbox):
    def __init__(
        self,
        project_id: str,
        root: Path,
        *,
        egress: EgressPolicy | None = None,
        commands_enabled: bool = False,
        limits: ResourceLimits | None = None,
        snapshots_root: Path | None = None,
    ) -> None:
        self.project_id = str(project_id)
        self._root = Path(root)
        self._egress = egress or EgressPolicy()
        self._commands_enabled = commands_enabled
        self.limits = limits or ResourceLimits()
        self._snapshots_root = snapshots_root or (
            self._root.parent / ".snapshots" / self.project_id
        )
        self.status = SandboxStatus.created
        self._env: LocalWorkspaceEnvironment | None = None
        self._setup_commands: list[str] = []

    # -- lifecycle ---------------------------------------------------------
    def provision(self) -> None:
        self.status = SandboxStatus.provisioning
        self._env = LocalWorkspaceEnvironment(
            self._root, egress=self._egress, commands_enabled=self._commands_enabled
        )
        self.status = SandboxStatus.ready

    @property
    def environment(self) -> LocalWorkspaceEnvironment:
        if self._env is None:
            self.provision()
        assert self._env is not None
        return self._env

    def initialize(self, setup_commands: Sequence[str] = ()) -> list[CommandResult]:
        self._setup_commands = list(setup_commands)
        results: list[CommandResult] = []
        for command in setup_commands:
            # Setup commands are recorded for reproducibility; they run only if the backend
            # permits command execution (the container sandbox always will).
            results.append(self.environment.run(command.split(), timeout=self.limits.wall_seconds))
        return results

    def snapshot(self, label: str = "") -> str:
        snapshot_id = uuid.uuid4().hex
        self._snapshots_root.mkdir(parents=True, exist_ok=True)
        archive = self._snapshots_root / f"{snapshot_id}.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            if self._root.exists():
                tar.add(self._root, arcname=".")
        return snapshot_id

    def reset(self, snapshot_id: str | None = None) -> None:
        # Clear the workspace back to empty.
        if self._root.exists():
            shutil.rmtree(self._root)
        self._root.mkdir(parents=True, exist_ok=True)
        if snapshot_id is not None:
            archive = self._snapshots_root / f"{snapshot_id}.tar.gz"
            if not archive.exists():
                raise SandboxError(f"unknown snapshot '{snapshot_id}'")
            with tarfile.open(archive, "r:gz") as tar:
                # filter="data" refuses absolute paths / traversal in the archive members.
                tar.extractall(self._root, filter="data")
        # Rebuild the environment against the fresh directory.
        self._env = LocalWorkspaceEnvironment(
            self._root, egress=self._egress, commands_enabled=self._commands_enabled
        )
        self.status = SandboxStatus.ready

    def destroy(self) -> None:
        if self._root.exists():
            shutil.rmtree(self._root)
        if self._snapshots_root.exists():
            shutil.rmtree(self._snapshots_root)
        self._env = None
        self.status = SandboxStatus.destroyed

    def reproducibility(self) -> ReproducibilityInfo:
        return ReproducibilityInfo(
            runtime="local",
            runtime_versions={"python": sys.version.split()[0], "platform": platform.platform()},
            setup_commands=list(self._setup_commands),
        )
