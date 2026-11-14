"""Built-in tool handlers.

These are the concrete implementations behind the Phase 4 tool specs. They operate through
the controlled :class:`~forge.tools.sandbox.ExecutionEnvironment` so the filesystem jail and
egress policy are always in force. Tools that need infrastructure not yet built (a real
browser, an external search provider) are declared in the registry with ``handler=None``
rather than faked here.
"""

from __future__ import annotations

import shutil
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from typing import TYPE_CHECKING

from forge.tools.contract import ToolError

if TYPE_CHECKING:
    from forge.tools.runtime import ToolInvocationContext

# ---------------------------------------------------------------------------
# Filesystem (capability: filesystem)
# ---------------------------------------------------------------------------
_MAX_READ_BYTES = 1_000_000


def fs_read(ctx: ToolInvocationContext) -> dict:
    path = ctx.args["path"]
    target = ctx.env.resolve(path)
    if not target.is_file():
        raise ToolError(f"not a file: {path}")
    raw = target.read_bytes()
    truncated = len(raw) > _MAX_READ_BYTES
    text = raw[:_MAX_READ_BYTES].decode("utf-8", errors="replace")
    return {"path": path, "content": text, "bytes": len(raw), "truncated": truncated}


def fs_write(ctx: ToolInvocationContext) -> dict:
    path = ctx.args["path"]
    content = ctx.args["content"]
    target = ctx.env.resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = content.encode("utf-8")
    target.write_bytes(data)
    return {"path": path, "bytes": len(data)}


def fs_list(ctx: ToolInvocationContext) -> dict:
    path = ctx.args.get("path", ".")
    target = ctx.env.resolve(path)
    if not target.exists():
        raise ToolError(f"no such path: {path}")
    if not target.is_dir():
        raise ToolError(f"not a directory: {path}")
    entries = []
    for child in sorted(target.iterdir(), key=lambda p: p.name):
        entries.append(
            {
                "name": child.name,
                "type": "dir" if child.is_dir() else "file",
                "bytes": child.stat().st_size if child.is_file() else None,
            }
        )
    return {"path": path, "entries": entries}


def fs_delete(ctx: ToolInvocationContext) -> dict:
    path = ctx.args["path"]
    target = ctx.env.resolve(path)
    if target.is_dir():
        shutil.rmtree(target)
    elif target.exists():
        target.unlink()
    else:
        raise ToolError(f"no such path: {path}")
    return {"path": path, "deleted": True}


# ---------------------------------------------------------------------------
# Terminal (capability: terminal)
# ---------------------------------------------------------------------------
# A conservative allow-list. Network-capable installers (pip/npm) go through the package
# tool so their egress is policy-controlled; a general shell is deliberately excluded.
_TERMINAL_ALLOWED = frozenset(
    {
        "ls", "cat", "echo", "pwd", "head", "tail", "wc", "grep", "find", "sort",
        "uniq", "true", "false", "python", "python3", "pytest", "node", "make",
        "go", "cargo", "ruff", "mypy",
    }
)


def terminal_run(ctx: ToolInvocationContext) -> dict:
    argv = ctx.args["argv"]
    if not argv:
        raise ToolError("argv must be a non-empty list")
    program = argv[0].rsplit("/", 1)[-1]
    if program not in _TERMINAL_ALLOWED:
        raise ToolError(
            f"command '{program}' is not allow-listed for the terminal tool"
        )
    result = ctx.env.run(argv, timeout=ctx.timeout_seconds)
    return {
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


# ---------------------------------------------------------------------------
# Git (capability: git)
# ---------------------------------------------------------------------------
# Offline git subcommands only; network subcommands (clone/fetch/pull/push) need egress
# and arrive with the Phase 5 network policy.
_GIT_ALLOWED = frozenset(
    {"init", "add", "commit", "status", "log", "diff", "show", "branch", "checkout",
     "rm", "mv", "restore", "config", "tag"}
)
_GIT_IDENTITY = [
    "-c", "user.name=Forge",
    "-c", "user.email=forge@localhost",
    "-c", "commit.gpgsign=false",
]


def git_run(ctx: ToolInvocationContext) -> dict:
    args = ctx.args["args"]
    if not args:
        raise ToolError("args must be a non-empty list")
    subcommand = args[0]
    if subcommand not in _GIT_ALLOWED:
        raise ToolError(f"git subcommand '{subcommand}' is not allowed (offline subset)")
    argv = ["git", *_GIT_IDENTITY, *args]
    result = ctx.env.run(argv, timeout=ctx.timeout_seconds)
    return {
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


# ---------------------------------------------------------------------------
# Package manager (capability: package) — requires network egress
# ---------------------------------------------------------------------------
_PACKAGE_REGISTRIES = {"pip": "pypi.org", "npm": "registry.npmjs.org"}


def package_install(ctx: ToolInvocationContext) -> dict:
    manager = ctx.args["manager"]
    packages = ctx.args["packages"]
    if manager not in _PACKAGE_REGISTRIES:
        raise ToolError(f"unsupported package manager: {manager}")
    # Egress is deny-by-default: without an allow-list grant, installation is refused.
    ctx.egress.check(_PACKAGE_REGISTRIES[manager])
    if manager == "pip":
        argv = ["python", "-m", "pip", "install", *packages]
    else:
        argv = ["npm", "install", *packages]
    result = ctx.env.run(argv, timeout=ctx.timeout_seconds)
    return {
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


# ---------------------------------------------------------------------------
# HTTP (capability: http) — egress-controlled
# ---------------------------------------------------------------------------
_HTTP_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"})
_MAX_BODY_BYTES = 1_000_000


def http_request(ctx: ToolInvocationContext) -> dict:
    method = ctx.args.get("method", "GET").upper()
    url = ctx.args["url"]
    if method not in _HTTP_METHODS:
        raise ToolError(f"unsupported HTTP method: {method}")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ToolError("only http/https URLs are permitted")
    if not parsed.hostname:
        raise ToolError("URL has no host")
    # Deny-by-default egress: only allow-listed hosts are reachable.
    ctx.egress.check(parsed.hostname)

    data = None
    body = ctx.args.get("body")
    if body is not None:
        data = body.encode("utf-8") if isinstance(body, str) else body
    request = urllib.request.Request(url, method=method, data=data)
    for key, value in (ctx.args.get("headers") or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=ctx.timeout_seconds) as response:  # noqa: S310
            raw = response.read(_MAX_BODY_BYTES + 1)
            status = response.status
            content_type = response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        raw = exc.read(_MAX_BODY_BYTES + 1)
        status = exc.code
        content_type = exc.headers.get("Content-Type", "") if exc.headers else ""
    except urllib.error.URLError as exc:
        raise ToolError(f"request failed: {exc.reason}") from exc
    truncated = len(raw) > _MAX_BODY_BYTES
    text = raw[:_MAX_BODY_BYTES].decode("utf-8", errors="replace")
    return {
        "status": status,
        "content_type": content_type,
        "body": text,
        "bytes": len(raw),
        "truncated": truncated,
    }


# ---------------------------------------------------------------------------
# Database (capability: database) — project-local SQLite target
# ---------------------------------------------------------------------------
_READ_ONLY_PREFIXES = ("select", "pragma", "explain", "with")


def _open_sqlite(ctx: ToolInvocationContext) -> sqlite3.Connection:
    path = ctx.args["path"]
    target = ctx.env.resolve(path)  # jailed to the project workspace
    return sqlite3.connect(str(target), timeout=ctx.timeout_seconds)


def db_query(ctx: ToolInvocationContext) -> dict:
    sql = ctx.args["sql"]
    params = ctx.args.get("params") or []
    if not sql.lstrip().lower().startswith(_READ_ONLY_PREFIXES):
        raise ToolError("db.query only permits read-only statements; use db.execute")
    conn = _open_sqlite(ctx)
    try:
        cursor = conn.execute(sql, params)
        columns = [c[0] for c in cursor.description] if cursor.description else []
        rows = [dict(zip(columns, row, strict=False)) for row in cursor.fetchall()]
    finally:
        conn.close()
    return {"columns": columns, "rows": rows, "rowcount": len(rows)}


def db_execute(ctx: ToolInvocationContext) -> dict:
    sql = ctx.args["sql"]
    params = ctx.args.get("params") or []
    conn = _open_sqlite(ctx)
    try:
        cursor = conn.execute(sql, params)
        conn.commit()
        rowcount = cursor.rowcount
    finally:
        conn.close()
    return {"rowcount": rowcount}


# ---------------------------------------------------------------------------
# Search (capability: search) — provider seam
# ---------------------------------------------------------------------------
def search_web(ctx: ToolInvocationContext) -> dict:
    # No search provider is configured yet; a real provider (with credentials) is wired in
    # alongside the research engine (Phase 6/9). Fail loudly rather than fabricate results.
    raise ToolError(
        "no search provider is configured; web search is enabled with the research "
        "engine (Phase 6/9)"
    )
