"""Tool registry and the built-in tool catalog.

The registry is the queryable catalog of tool contracts. The built-ins below cover the
Phase 4 build-order items. Tools that require infrastructure not yet built — a real
headless browser (Phase 15) — are registered as **declared contracts** with
``handler=None`` so their contract is real and discoverable but invoking them fails
loudly, mirroring the honest Phase 3 agent roster.
"""

from __future__ import annotations

from forge.tools import builtins
from forge.tools.contract import CostClass, SideEffect, ToolSpec
from forge.tools.permissions import Capability


class ToolRegistry:
    """A catalog of tools keyed by unique ``name``."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> ToolSpec:
        if spec.name in self._tools:
            raise ValueError(f"Tool '{spec.name}' is already registered")
        self._tools[spec.name] = spec
        return spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def all(self) -> list[ToolSpec]:
        return [self._tools[k] for k in sorted(self._tools)]

    def names(self) -> list[str]:
        return sorted(self._tools)


# Reusable JSON-schema fragments.
_STR = {"type": "string"}
_STR_ARRAY = {"type": "array", "items": {"type": "string"}}


_BUILTINS: list[ToolSpec] = [
    # -- Filesystem --------------------------------------------------------
    ToolSpec(
        name="fs.read",
        description="Read a UTF-8 text file within the project workspace.",
        permission=Capability.filesystem,
        input_schema={
            "type": "object",
            "properties": {"path": _STR},
            "required": ["path"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "path": _STR,
                "content": _STR,
                "bytes": {"type": "integer"},
                "truncated": {"type": "boolean"},
            },
            "required": ["path", "content"],
        },
        cost_class=CostClass.free,
        side_effect=SideEffect.read,
        handler=builtins.fs_read,
    ),
    ToolSpec(
        name="fs.write",
        description="Create or overwrite a text file within the project workspace.",
        permission=Capability.filesystem,
        input_schema={
            "type": "object",
            "properties": {"path": _STR, "content": _STR},
            "required": ["path", "content"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"path": _STR, "bytes": {"type": "integer"}},
            "required": ["path", "bytes"],
        },
        cost_class=CostClass.free,
        side_effect=SideEffect.write,
        handler=builtins.fs_write,
    ),
    ToolSpec(
        name="fs.list",
        description="List the entries of a directory within the project workspace.",
        permission=Capability.filesystem,
        input_schema={
            "type": "object",
            "properties": {"path": _STR},
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"path": _STR, "entries": {"type": "array"}},
            "required": ["entries"],
        },
        cost_class=CostClass.free,
        side_effect=SideEffect.read,
        handler=builtins.fs_list,
    ),
    ToolSpec(
        name="fs.delete",
        description="Delete a file or directory within the project workspace.",
        permission=Capability.filesystem,
        input_schema={
            "type": "object",
            "properties": {"path": _STR},
            "required": ["path"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"path": _STR, "deleted": {"type": "boolean"}},
            "required": ["deleted"],
        },
        cost_class=CostClass.free,
        side_effect=SideEffect.destructive,  # approval-gated
        retryable=False,
        handler=builtins.fs_delete,
    ),
    # -- Terminal ----------------------------------------------------------
    ToolSpec(
        name="terminal.run",
        description="Run an allow-listed command inside the controlled workspace.",
        permission=Capability.terminal,
        input_schema={
            "type": "object",
            "properties": {"argv": _STR_ARRAY},
            "required": ["argv"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "exit_code": {"type": "integer"},
                "stdout": _STR,
                "stderr": _STR,
            },
            "required": ["exit_code"],
        },
        timeout_seconds=120.0,
        cost_class=CostClass.low,
        side_effect=SideEffect.write,
        handler=builtins.terminal_run,
    ),
    # -- Git ---------------------------------------------------------------
    ToolSpec(
        name="git",
        description="Run an offline git subcommand inside the project workspace.",
        permission=Capability.git,
        input_schema={
            "type": "object",
            "properties": {"args": _STR_ARRAY},
            "required": ["args"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "exit_code": {"type": "integer"},
                "stdout": _STR,
                "stderr": _STR,
            },
            "required": ["exit_code"],
        },
        timeout_seconds=60.0,
        cost_class=CostClass.low,
        side_effect=SideEffect.write,
        handler=builtins.git_run,
    ),
    # -- Package manager ---------------------------------------------------
    ToolSpec(
        name="package.install",
        description="Install dependencies with pip or npm (requires network egress).",
        permission=Capability.package,
        input_schema={
            "type": "object",
            "properties": {
                "manager": {"type": "string", "enum": ["pip", "npm"]},
                "packages": _STR_ARRAY,
            },
            "required": ["manager", "packages"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"exit_code": {"type": "integer"}},
            "required": ["exit_code"],
        },
        timeout_seconds=300.0,
        cost_class=CostClass.medium,
        side_effect=SideEffect.write,
        requires_network=True,
        handler=builtins.package_install,
    ),
    # -- HTTP --------------------------------------------------------------
    ToolSpec(
        name="http.request",
        description="Make an HTTP request to an allow-listed host (egress-controlled).",
        permission=Capability.http,
        input_schema={
            "type": "object",
            "properties": {
                "method": {"type": "string"},
                "url": _STR,
                "headers": {"type": "object"},
                "body": _STR,
            },
            "required": ["url"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "integer"},
                "content_type": _STR,
                "body": _STR,
                "bytes": {"type": "integer"},
                "truncated": {"type": "boolean"},
            },
            "required": ["status"],
        },
        cost_class=CostClass.low,
        side_effect=SideEffect.read,
        requires_network=True,
        redact_keys=frozenset({"headers", "body"}),
        handler=builtins.http_request,
    ),
    # -- Search ------------------------------------------------------------
    ToolSpec(
        name="search.web",
        description="Search the web for a query (provider configured in Phase 6/9).",
        permission=Capability.search,
        input_schema={
            "type": "object",
            "properties": {"query": _STR, "limit": {"type": "integer"}},
            "required": ["query"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"results": {"type": "array"}},
            "required": ["results"],
        },
        cost_class=CostClass.medium,
        side_effect=SideEffect.read,
        requires_network=True,
        handler=builtins.search_web,
    ),
    # -- Database ----------------------------------------------------------
    ToolSpec(
        name="db.query",
        description="Run a read-only SQL query against a project-local SQLite database.",
        permission=Capability.database,
        input_schema={
            "type": "object",
            "properties": {"path": _STR, "sql": _STR, "params": {"type": "array"}},
            "required": ["path", "sql"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "columns": _STR_ARRAY,
                "rows": {"type": "array"},
                "rowcount": {"type": "integer"},
            },
            "required": ["rows", "rowcount"],
        },
        cost_class=CostClass.low,
        side_effect=SideEffect.read,
        handler=builtins.db_query,
    ),
    ToolSpec(
        name="db.execute",
        description="Run a writing/DDL SQL statement against a project-local SQLite database.",
        permission=Capability.database,
        input_schema={
            "type": "object",
            "properties": {"path": _STR, "sql": _STR, "params": {"type": "array"}},
            "required": ["path", "sql"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"rowcount": {"type": "integer"}},
            "required": ["rowcount"],
        },
        cost_class=CostClass.low,
        side_effect=SideEffect.destructive,  # approval-gated (may drop/overwrite data)
        retryable=False,
        handler=builtins.db_execute,
    ),
    # -- Browser (declared; not runnable until Phase 15) -------------------
    ToolSpec(
        name="browser.navigate",
        description="Navigate a controlled browser to a URL and capture page state.",
        permission=Capability.browser,
        input_schema={
            "type": "object",
            "properties": {"url": _STR},
            "required": ["url"],
            "additionalProperties": False,
        },
        output_schema={"type": "object"},
        cost_class=CostClass.high,
        side_effect=SideEffect.read,
        requires_network=True,
        handler=None,  # the browser engine arrives in Phase 15
    ),
]


def build_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for spec in _BUILTINS:
        registry.register(spec)
    return registry


registry = build_default_registry()
