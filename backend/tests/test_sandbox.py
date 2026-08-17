"""Sandbox lifecycle contracts: provision, snapshot/reset, destroy, backend selection."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from forge.sandbox.contract import ResourceLimits, SandboxError, SandboxStatus, SandboxUnavailable
from forge.sandbox.docker import DockerSandbox
from forge.sandbox.local import LocalSandbox
from forge.sandbox.provider import SandboxProvider
from forge.tools.contract import PathEscapesWorkspace
from forge.tools.sandbox import EgressPolicy


def _sandbox(tmp_path: Path) -> LocalSandbox:
    sandbox = LocalSandbox(
        str(uuid.uuid4()),
        tmp_path / "ws",
        egress=EgressPolicy(),
        commands_enabled=True,
        snapshots_root=tmp_path / "snaps",
    )
    sandbox.provision()
    return sandbox


# --- lifecycle --------------------------------------------------------------
def test_provision_creates_ready_environment(tmp_path: Path) -> None:
    sandbox = _sandbox(tmp_path)
    assert sandbox.status == SandboxStatus.ready
    env = sandbox.environment
    env.resolve("a.txt").write_text("hi")
    assert (sandbox.environment.root / "a.txt").read_text() == "hi"
    # The jail is inherited from the execution environment.
    with pytest.raises(PathEscapesWorkspace):
        env.resolve("../escape.txt")


def test_snapshot_and_reset_restores_state(tmp_path: Path) -> None:
    sandbox = _sandbox(tmp_path)
    sandbox.environment.resolve("keep.txt").write_text("v1")
    snap = sandbox.snapshot("before-change")

    # Mutate after the snapshot.
    sandbox.environment.resolve("keep.txt").write_text("v2")
    sandbox.environment.resolve("extra.txt").write_text("junk")

    sandbox.reset(snap)
    assert sandbox.environment.resolve("keep.txt").read_text() == "v1"
    assert not sandbox.environment.resolve("extra.txt").exists()


def test_reset_clean_empties_workspace(tmp_path: Path) -> None:
    sandbox = _sandbox(tmp_path)
    sandbox.environment.resolve("a.txt").write_text("x")
    sandbox.reset()  # no snapshot -> clean slate
    assert list(sandbox.environment.root.iterdir()) == []


def test_unknown_snapshot_raises(tmp_path: Path) -> None:
    sandbox = _sandbox(tmp_path)
    with pytest.raises(SandboxError):
        sandbox.reset("nonexistent")


def test_destroy_removes_workspace(tmp_path: Path) -> None:
    sandbox = _sandbox(tmp_path)
    root = sandbox.environment.root
    sandbox.destroy()
    assert sandbox.status == SandboxStatus.destroyed
    assert not root.exists()


def test_reproducibility_records_runtime(tmp_path: Path) -> None:
    sandbox = _sandbox(tmp_path)
    sandbox.initialize(["echo hello"])
    info = sandbox.reproducibility().to_dict()
    assert info["runtime"] == "local"
    assert "python" in info["runtime_versions"]
    assert info["setup_commands"] == ["echo hello"]


# --- resource limits --------------------------------------------------------
def test_resource_limits_defaults() -> None:
    limits = ResourceLimits()
    assert limits.cpus > 0 and limits.memory_mb > 0
    assert "memory_mb" in limits.to_dict()


# --- backend selection ------------------------------------------------------
def test_docker_backend_unavailable_here() -> None:
    # No Docker daemon in this environment: the backend reports unavailable and refuses.
    assert DockerSandbox.available() is False
    with pytest.raises(SandboxUnavailable):
        DockerSandbox(str(uuid.uuid4()))


def test_provider_falls_back_to_local() -> None:
    provider = SandboxProvider()
    assert provider.use_container() is False  # auto + no daemon -> local
    sandbox = provider.get(uuid.uuid4())
    assert isinstance(sandbox, LocalSandbox)
    assert sandbox.status == SandboxStatus.ready
