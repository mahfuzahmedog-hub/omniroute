"""Controlled execution environments for tools.

Spec 06_TOOL_SYSTEM: *"Command execution must occur inside controlled environments.
Network egress and filesystem mounts are policy-controlled."* The full container sandbox
is Phase 5. Phase 4 introduces the **seam** plus a local implementation that already
enforces the two controls achievable without containers:

1. **Filesystem jail.** Every path a tool touches is resolved under the project's
   workspace root; a path that escapes the root (via ``..`` or an absolute path or a
   symlink) is refused. This confines ``fs.*`` tools to the project workspace.
2. **Deny-by-default egress.** A tool may only reach a network host that appears on the
   project's egress allow-list.

The local environment does **not** fully isolate spawned subprocesses (a ``python`` or
``git`` process can still read the host filesystem); that requires the Phase 5 container
sandbox. To avoid shipping unsafe host execution by default, command execution is disabled
outside ``local``/``development`` (see :class:`ExecutionEnvironment` construction in the
runtime), and command-spawning tools fail loudly when it is disabled.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from forge.tools.contract import (
    NetworkEgressDenied,
    PathEscapesWorkspace,
    SandboxUnavailable,
    ToolTimeout,
)


@dataclass(frozen=True)
class EgressPolicy:
    """A deny-by-default network egress allow-list of hostnames."""

    allowed_hosts: frozenset[str] = frozenset()

    def allows(self, host: str) -> bool:
        return host in self.allowed_hosts

    def check(self, host: str) -> None:
        if not self.allows(host):
            raise NetworkEgressDenied(
                f"egress to '{host}' is not allowed (deny-by-default egress policy)"
            )


@dataclass
class CommandResult:
    """The outcome of a command run inside a controlled environment."""

    exit_code: int
    stdout: str
    stderr: str


# A minimal environment for subprocesses. We never forward the parent process environment
# (which may hold secrets); only a small, explicit allow-list of locale/PATH variables is
# passed through, satisfying "secrets must never be stored in raw tool logs" and reducing
# ambient authority available to a spawned command.
_SAFE_ENV_KEYS = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TZ")


class ExecutionEnvironment:
    """Abstract controlled environment. The Phase 5 container sandbox implements this too."""

    @property
    def root(self) -> Path:  # pragma: no cover - interface
        raise NotImplementedError

    @property
    def egress(self) -> EgressPolicy:  # pragma: no cover - interface
        raise NotImplementedError

    def resolve(self, relpath: str) -> Path:  # pragma: no cover - interface
        raise NotImplementedError

    def run(
        self, argv: list[str], *, timeout: float, env: dict[str, str] | None = None
    ) -> CommandResult:  # pragma: no cover - interface
        raise NotImplementedError


class LocalWorkspaceEnvironment(ExecutionEnvironment):
    """A path-jailed local working directory. The Phase-4 controlled environment."""

    def __init__(
        self,
        root: Path,
        *,
        egress: EgressPolicy | None = None,
        commands_enabled: bool = False,
    ) -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        self._egress = egress or EgressPolicy()
        self._commands_enabled = commands_enabled

    @property
    def root(self) -> Path:
        return self._root

    @property
    def egress(self) -> EgressPolicy:
        return self._egress

    def resolve(self, relpath: str) -> Path:
        """Resolve ``relpath`` under the workspace root, refusing any escape.

        ``(root / relpath)`` collapses an absolute ``relpath`` to that absolute path, which
        then fails the ``relative_to`` jail check — so absolute paths, ``..`` traversal, and
        symlinks that point outside the root are all rejected.
        """
        candidate = (self._root / relpath).resolve()
        try:
            candidate.relative_to(self._root)
        except ValueError:
            raise PathEscapesWorkspace(
                f"path '{relpath}' escapes the project workspace"
            ) from None
        return candidate

    def run(
        self, argv: list[str], *, timeout: float, env: dict[str, str] | None = None
    ) -> CommandResult:
        if not self._commands_enabled:
            raise SandboxUnavailable(
                "command execution requires the container sandbox (Phase 5); it is "
                "disabled in this environment"
            )
        safe_env = {k: os.environ[k] for k in _SAFE_ENV_KEYS if k in os.environ}
        safe_env["HOME"] = str(self._root)
        if env:
            safe_env.update(env)
        try:
            proc = subprocess.run(  # noqa: S603 - argv is a list, shell=False, no injection
                list(argv),
                cwd=str(self._root),
                capture_output=True,
                text=True,
                timeout=timeout,
                env=safe_env,
                shell=False,
                check=False,
            )
        except FileNotFoundError as exc:
            raise SandboxUnavailable(f"command not found: {argv[0]}") from exc
        except subprocess.TimeoutExpired as exc:
            raise ToolTimeout(f"command exceeded {timeout}s") from exc
        return CommandResult(exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)
