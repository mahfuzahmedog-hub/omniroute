"""Sandbox lifecycle contracts: provision, snapshot/reset, destroy, backend selection."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from forge.config import Settings
from forge.sandbox.contract import ResourceLimits, SandboxError, SandboxStatus, SandboxUnavailable
from forge.sandbox.docker import DockerSandbox
from forge.sandbox.local import LocalSandbox
from forge.sandbox.provider import SandboxProvider
from forge.tools.contract import PathEscapesWorkspace
from forge.tools.sandbox import EgressPolicy

_daemon_available = DockerSandbox.available()
requires_daemon = pytest.mark.skipif(
    not _daemon_available, reason="requires a reachable Docker daemon"
)
requires_no_daemon = pytest.mark.skipif(
    _daemon_available, reason="requires no Docker daemon (host has one)"
)


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
# Selection depends on (a) the configured backend and (b) whether a Docker daemon is
# reachable. We pin the backend with an explicit ``Settings`` so the config-driven paths
# are deterministic on any host, and gate the daemon-dependent branches on a real probe
# (``DockerSandbox.available()``) so they are skipped — not failed — where the daemon is
# absent. This keeps coverage of both the "daemon present" and "daemon absent" paths
# without either branch silently depending on the CI host.
@requires_no_daemon
def test_docker_backend_unavailable_without_daemon() -> None:
    # No Docker daemon: the backend reports unavailable and refuses to construct.
    assert DockerSandbox.available() is False
    with pytest.raises(SandboxUnavailable):
        DockerSandbox(str(uuid.uuid4()))


@requires_daemon
def test_docker_backend_available_but_lifecycle_not_wired() -> None:
    # With a daemon present, ``available()`` is honest and the backend constructs, but the
    # container lifecycle is still an unimplemented seam: using it fails loudly rather than
    # faking isolation.
    assert DockerSandbox.available() is True
    sandbox = DockerSandbox(str(uuid.uuid4()))
    assert sandbox.status == SandboxStatus.created
    with pytest.raises(SandboxUnavailable):
        sandbox.provision()
    with pytest.raises(SandboxUnavailable):
        _ = sandbox.environment


def test_provider_auto_selects_local_without_daemon() -> None:
    # Explicit config pins the backend so this is deterministic regardless of host Docker.
    provider = SandboxProvider(Settings(sandbox_backend="local"))
    assert provider.use_container() is False
    sandbox = provider.get(uuid.uuid4())
    assert isinstance(sandbox, LocalSandbox)
    assert sandbox.status == SandboxStatus.ready


def test_provider_docker_backend_opts_in() -> None:
    # ``docker`` forces the container backend regardless of daemon reachability.
    provider = SandboxProvider(Settings(sandbox_backend="docker"))
    assert provider.use_container() is True


@requires_no_daemon
def test_provider_auto_falls_back_without_daemon() -> None:
    # "auto" with no daemon reachable -> the local workspace sandbox.
    provider = SandboxProvider(Settings(sandbox_backend="auto"))
    assert provider.use_container() is False
    sandbox = provider.get(uuid.uuid4())
    assert isinstance(sandbox, LocalSandbox)
    assert sandbox.status == SandboxStatus.ready


@requires_daemon
def test_provider_auto_prefers_container_with_daemon() -> None:
    # "auto" with a reachable daemon -> the container backend is selected.
    provider = SandboxProvider(Settings(sandbox_backend="auto"))
    assert provider.use_container() is True
