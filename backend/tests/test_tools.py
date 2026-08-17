"""Tool runtime contracts: permissions, jail, egress, approval, audit, agent use."""

from __future__ import annotations

import http.server
import socketserver
import threading
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from forge.agents.registry import registry as agent_registry
from forge.agents.runner import register_agents
from forge.db import SessionLocal
from forge.models.agent_execution import AgentExecution, AgentStatus
from forge.models.audit import AuditEvent
from forge.models.project import Project
from forge.models.run import Run, RunStatus
from forge.models.task import TaskStatus
from forge.models.tool import ProjectToolGrant, ToolInvocation, ToolInvocationStatus
from forge.orchestration import service
from forge.orchestration.worker import HandlerRegistry, Worker
from forge.tools.contract import (
    ApprovalRequired,
    NetworkEgressDenied,
    PathEscapesWorkspace,
    PermissionDenied,
    ToolError,
    ToolNotRunnable,
)
from forge.tools.runtime import SchemaError, ToolRuntime
from tests.conftest import seed_project


def _project(db, client: TestClient, email: str = "eng@example.com") -> Project:
    ctx = seed_project(client, email=email)
    return db.get(Project, uuid.UUID(ctx["project_id"]))


def _grant(
    db,
    project: Project,
    permission: str,
    *,
    auto_approve: bool = False,
    allowed_hosts: list[str] | None = None,
) -> None:
    db.add(
        ProjectToolGrant(
            project_id=project.id,
            permission=permission,
            auto_approve=auto_approve,
            allowed_hosts=allowed_hosts,
        )
    )
    db.commit()


# --- permission model -------------------------------------------------------
def test_denied_by_default(client: TestClient) -> None:
    with SessionLocal() as db:
        project = _project(db, client)
        rt = ToolRuntime(db)
        with pytest.raises(PermissionDenied):
            rt.invoke("fs.read", {"path": "a.txt"}, project=project)
        # The denial is recorded durably.
        inv = db.scalars(select(ToolInvocation)).all()
        assert len(inv) == 1
        assert inv[0].status == ToolInvocationStatus.denied


def test_unknown_capability_and_tool(client: TestClient) -> None:
    from forge.tools.contract import ToolNotFound

    with SessionLocal() as db:
        project = _project(db, client)
        rt = ToolRuntime(db)
        with pytest.raises(ToolNotFound):
            rt.invoke("does.not.exist", {}, project=project)


# --- filesystem jail --------------------------------------------------------
def test_fs_write_read_roundtrip(client: TestClient) -> None:
    with SessionLocal() as db:
        project = _project(db, client)
        _grant(db, project, "filesystem")
        rt = ToolRuntime(db)
        rt.invoke("fs.write", {"path": "notes/hello.txt", "content": "hi"}, project=project)
        result = rt.invoke("fs.read", {"path": "notes/hello.txt"}, project=project)
        assert result.outputs["content"] == "hi"
        listing = rt.invoke("fs.list", {"path": "notes"}, project=project)
        names = [e["name"] for e in listing.outputs["entries"]]
        assert "hello.txt" in names


def test_path_escape_is_refused(client: TestClient) -> None:
    with SessionLocal() as db:
        project = _project(db, client)
        _grant(db, project, "filesystem")
        rt = ToolRuntime(db)
        with pytest.raises(PathEscapesWorkspace):
            rt.invoke("fs.read", {"path": "../../etc/passwd"}, project=project)
        with pytest.raises(PathEscapesWorkspace):
            rt.invoke("fs.read", {"path": "/etc/passwd"}, project=project)


def test_input_schema_validation(client: TestClient) -> None:
    with SessionLocal() as db:
        project = _project(db, client)
        _grant(db, project, "filesystem")
        rt = ToolRuntime(db)
        with pytest.raises(SchemaError):
            rt.invoke("fs.write", {"path": "x"}, project=project)  # missing 'content'


# --- approval gate ----------------------------------------------------------
def test_destructive_tool_requires_approval(client: TestClient) -> None:
    with SessionLocal() as db:
        project = _project(db, client)
        _grant(db, project, "filesystem")
        rt = ToolRuntime(db)
        rt.invoke("fs.write", {"path": "doomed.txt", "content": "x"}, project=project)
        with pytest.raises(ApprovalRequired):
            rt.invoke("fs.delete", {"path": "doomed.txt"}, project=project)
        # With an explicit approval the delete proceeds.
        out = rt.invoke("fs.delete", {"path": "doomed.txt"}, project=project, approved=True)
        assert out.outputs["deleted"] is True


def test_auto_approve_grant_allows_destructive(client: TestClient) -> None:
    with SessionLocal() as db:
        project = _project(db, client)
        _grant(db, project, "filesystem", auto_approve=True)
        rt = ToolRuntime(db)
        rt.invoke("fs.write", {"path": "d.txt", "content": "x"}, project=project)
        out = rt.invoke("fs.delete", {"path": "d.txt"}, project=project)  # no explicit approval
        assert out.outputs["deleted"] is True


# --- database tool ----------------------------------------------------------
def test_database_execute_and_query(client: TestClient) -> None:
    with SessionLocal() as db:
        project = _project(db, client)
        _grant(db, project, "database", auto_approve=True)  # db.execute is destructive
        rt = ToolRuntime(db)
        rt.invoke(
            "db.execute",
            {"path": "app.db", "sql": "CREATE TABLE t (id INTEGER, name TEXT)"},
            project=project,
        )
        rt.invoke(
            "db.execute",
            {"path": "app.db", "sql": "INSERT INTO t VALUES (?, ?)", "params": [1, "alice"]},
            project=project,
        )
        result = rt.invoke(
            "db.query", {"path": "app.db", "sql": "SELECT name FROM t WHERE id = ?", "params": [1]},
            project=project,
        )
        assert result.outputs["rows"] == [{"name": "alice"}]


def test_db_query_rejects_writes(client: TestClient) -> None:
    with SessionLocal() as db:
        project = _project(db, client)
        _grant(db, project, "database")
        rt = ToolRuntime(db)
        with pytest.raises(ToolError):
            rt.invoke("db.query", {"path": "x.db", "sql": "DROP TABLE t"}, project=project)


# --- http egress control ----------------------------------------------------
@pytest.fixture
def local_server() -> Iterator[str]:
    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"pong")

        def log_message(self, *_args):  # silence
            return

    with socketserver.TCPServer(("127.0.0.1", 0), _Handler) as httpd:
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{port}/"
        finally:
            httpd.shutdown()


def test_http_egress_denied_by_default(client: TestClient, local_server: str) -> None:
    with SessionLocal() as db:
        project = _project(db, client)
        _grant(db, project, "http")  # granted capability, but no host allow-list
        rt = ToolRuntime(db)
        with pytest.raises(NetworkEgressDenied):
            rt.invoke("http.request", {"url": local_server}, project=project)


def test_http_allowed_host(client: TestClient, local_server: str) -> None:
    with SessionLocal() as db:
        project = _project(db, client)
        _grant(db, project, "http", allowed_hosts=["127.0.0.1"])
        rt = ToolRuntime(db)
        result = rt.invoke("http.request", {"url": local_server}, project=project)
        assert result.outputs["status"] == 200
        assert result.outputs["body"] == "pong"


# --- terminal + git ---------------------------------------------------------
def test_terminal_allowlist(client: TestClient) -> None:
    with SessionLocal() as db:
        project = _project(db, client)
        _grant(db, project, "terminal")
        rt = ToolRuntime(db)
        out = rt.invoke("terminal.run", {"argv": ["echo", "hi"]}, project=project)
        assert out.outputs["exit_code"] == 0
        assert out.outputs["stdout"].strip() == "hi"
        with pytest.raises(ToolError):
            rt.invoke("terminal.run", {"argv": ["rm", "-rf", "/"]}, project=project)


def test_git_init(client: TestClient) -> None:
    with SessionLocal() as db:
        project = _project(db, client)
        _grant(db, project, "git")
        rt = ToolRuntime(db)
        out = rt.invoke("git", {"args": ["init"]}, project=project)
        assert out.outputs["exit_code"] == 0
        with pytest.raises(ToolError):
            rt.invoke("git", {"args": ["push"]}, project=project)  # network subcommand blocked


# --- package / search / browser (network / infra pending) -------------------
def test_package_install_egress_denied(client: TestClient) -> None:
    with SessionLocal() as db:
        project = _project(db, client)
        _grant(db, project, "package")
        rt = ToolRuntime(db)
        with pytest.raises(NetworkEgressDenied):
            rt.invoke(
                "package.install", {"manager": "pip", "packages": ["requests"]}, project=project
            )


def test_search_not_configured(client: TestClient) -> None:
    with SessionLocal() as db:
        project = _project(db, client)
        _grant(db, project, "search")
        rt = ToolRuntime(db)
        with pytest.raises(ToolError):
            rt.invoke("search.web", {"query": "forge"}, project=project)


def test_browser_declared_not_runnable(client: TestClient) -> None:
    with SessionLocal() as db:
        project = _project(db, client)
        _grant(db, project, "browser")
        rt = ToolRuntime(db)
        with pytest.raises(ToolNotRunnable):
            rt.invoke("browser.navigate", {"url": "https://example.com"}, project=project)


# --- audit + redaction ------------------------------------------------------
def test_invocation_recorded_and_redacted(client: TestClient, local_server: str) -> None:
    with SessionLocal() as db:
        project = _project(db, client)
        _grant(db, project, "http", allowed_hosts=["127.0.0.1"])
        rt = ToolRuntime(db)
        rt.invoke(
            "http.request",
            {"url": local_server, "headers": {"Authorization": "Bearer secret"}},
            project=project,
        )
        inv = db.scalars(select(ToolInvocation)).all()[-1]
        assert inv.status == ToolInvocationStatus.succeeded
        assert inv.args_metadata["headers"] == "***"  # secret redacted
        assert inv.duration_ms is not None
        actions = {e.action for e in db.scalars(select(AuditEvent)).all()}
        assert "tool.succeeded" in actions


# --- agent integration (Phase 3 <-> Phase 4) --------------------------------
def _fresh_worker() -> Worker:
    reg = HandlerRegistry()
    register_agents(worker_registry=reg)
    return Worker(SessionLocal, registry=reg)


def test_agent_uses_tools_under_least_privilege(client: TestClient) -> None:
    with SessionLocal() as db:
        project = _project(db, client)
        _grant(db, project, "filesystem")
        run = service.create_run(db, project_id=project.id, name="scribe")
        service.add_task(
            db,
            run=run,
            name="write-and-read",
            kind="example.fs_roundtrip",
            inputs={"path": "agent/out.txt", "content": "written by an agent"},
        )
        service.start_run(db, run)
        run_id = run.id

    _fresh_worker().run()

    with SessionLocal() as db:
        run = db.get(Run, run_id)
        assert run.status == RunStatus.succeeded
        assert run.tasks[0].status == TaskStatus.succeeded
        execution = db.scalar(select(AgentExecution).where(AgentExecution.run_id == run_id))
        assert execution.status == AgentStatus.succeeded
        # Both tool calls were recorded, tied to the agent/run/task.
        invs = db.scalars(
            select(ToolInvocation).where(ToolInvocation.run_id == run_id)
        ).all()
        assert {i.tool_name for i in invs} == {"fs.write", "fs.read"}
        assert all(i.agent_key == "example.fs_roundtrip" for i in invs)


def test_agent_least_privilege_blocks_ungranted_capability(client: TestClient) -> None:
    # The project grants filesystem, but example.sum declares no tools; it must be denied.
    with SessionLocal() as db:
        project = _project(db, client)
        _grant(db, project, "filesystem")
        run = service.create_run(db, project_id=project.id, name="lp")
        service.add_task(db, run=run, name="t", kind="noop")
        service.start_run(db, run)
        task = run.tasks[0]
        agent = agent_registry.get("example.sum")  # allowed_tools is empty
        rt = ToolRuntime(db)
        with pytest.raises(PermissionDenied):
            rt.invoke("fs.read", {"path": "x"}, project=project, agent=agent, task_id=task.id)
