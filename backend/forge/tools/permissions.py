"""Tool capabilities (permissions).

Spec 06_TOOL_SYSTEM: "Tools are denied by default. Projects grant scoped permissions."
A *capability* is the unit a project grants; many tools can share one capability (e.g.
``fs.read``/``fs.write``/``fs.list``/``fs.delete`` all require ``filesystem``). Agents
declare a least-privilege subset of these same capability names in ``allowed_tools``, so
a tool call must satisfy **both** the project's grant and the calling agent's declared
capabilities.
"""

from __future__ import annotations

from enum import StrEnum


class Capability(StrEnum):
    """The set of grantable tool capabilities."""

    filesystem = "filesystem"
    terminal = "terminal"
    git = "git"
    package = "package"
    http = "http"
    search = "search"
    database = "database"
    browser = "browser"
    docker = "docker"
    deployment = "deployment"


ALL_CAPABILITIES: frozenset[str] = frozenset(c.value for c in Capability)


def is_valid_capability(name: str) -> bool:
    return name in ALL_CAPABILITIES
