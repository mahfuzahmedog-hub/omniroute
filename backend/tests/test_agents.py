"""Agent runtime contracts: catalog, context, budgets, verification, execution."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from forge.agents.context import assemble_context
from forge.agents.contract import Agent, AgentBudget, BudgetExceeded, VerificationCheck
from forge.agents.registry import AgentRegistry, registry
from forge.agents.runner import build_agent_handler, register_agents
from forge.agents.verification import SchemaValidationError, run_verification, validate_schema
from forge.db import SessionLocal
from forge.models.agent_execution import AgentExecution, AgentStatus
from forge.models.run import Run, RunStatus
from forge.models.task import TaskStatus
from forge.orchestration import service
from forge.orchestration.worker import HandlerRegistry, Worker
from tests.conftest import seed_project


def _pid(client: TestClient) -> uuid.UUID:
    return uuid.UUID(seed_project(client)["project_id"])


def _fresh_worker() -> Worker:
    reg = HandlerRegistry()
    register_agents(worker_registry=reg)
    return Worker(SessionLocal, registry=reg)


def select_execution(run_id: uuid.UUID):
    return select(AgentExecution).where(AgentExecution.run_id == run_id)


# --- registry / catalog -----------------------------------------------------
def test_roster_registered_as_specs() -> None:
    commander = registry.get("commander")
    assert commander is not None
    assert commander.runnable is False  # declared contract, no executor yet
    assert commander.role == "Commander"


def test_examples_are_runnable() -> None:
    assert "example.sum" in registry.runnable_keys()
    assert "example.wordcount" in registry.runnable_keys()


def test_duplicate_registration_rejected() -> None:
    reg = AgentRegistry()
    agent = Agent(key="dup", role="R", objective="O")
    reg.register(agent)
    with pytest.raises(ValueError):
        reg.register(agent)


# --- schema + verification --------------------------------------------------
def test_validate_schema_pass_and_fail() -> None:
    schema = {"type": "object", "properties": {"x": {"type": "integer"}}, "required": ["x"]}
    validate_schema({"x": 1}, schema)
    with pytest.raises(SchemaValidationError):
        validate_schema({"x": "not-int"}, schema)


def test_verification_uses_output_schema_and_custom_checks() -> None:
    agent = Agent(
        key="v",
        role="R",
        objective="O",
        output_schema={"type": "object", "required": ["ok"]},
        verify=lambda _ctx, out: [VerificationCheck("truthy", bool(out.get("ok")))],
    )
    good = run_verification(agent, ctx=None, outputs={"ok": True})  # type: ignore[arg-type]
    assert good.passed
    bad = run_verification(agent, ctx=None, outputs={"ok": False})  # type: ignore[arg-type]
    assert not bad.passed


# --- budget -----------------------------------------------------------------
def test_budget_enforced(client: TestClient) -> None:
    pid = _pid(client)
    with SessionLocal() as db:
        run = service.create_run(db, project_id=pid, name="b")
        service.add_task(db, run=run, name="t", kind="noop")
        service.start_run(db, run)
        task = run.tasks[0]
        agent = Agent(key="tiny", role="R", objective="O", budget=AgentBudget(max_tokens=5))
        ctx = assemble_context(db, agent, task)
        ctx.record_usage(tokens=3)  # under budget
        with pytest.raises(BudgetExceeded):
            ctx.record_usage(tokens=10)  # now over


# --- context assembly -------------------------------------------------------
def test_context_assembles_upstream_outputs(client: TestClient) -> None:
    pid = _pid(client)
    with SessionLocal() as db:
        run = service.create_run(db, project_id=pid, name="ctx")
        a = service.add_task(db, run=run, name="upstream", kind="example.sum")
        b = service.add_task(db, run=run, name="downstream", kind="noop", depends_on=[a.id])
        service.start_run(db, run)
        # Manually complete A with outputs so B can see them.
        claimed = service.claim_next_task(db, worker_id="w")  # will be A (only ready)
        service.complete_task(db, claimed, success=True, outputs={"sum": 6})

        agent = registry.get("example.sum")
        ctx = assemble_context(db, agent, b)
        assert ctx.upstream_outputs == {"upstream": {"sum": 6}}
        assert ctx.assembled["project"]["name"]


# --- end to end via the worker ---------------------------------------------
def test_agent_task_runs_and_records_execution(client: TestClient) -> None:
    pid = _pid(client)
    with SessionLocal() as db:
        run = service.create_run(db, project_id=pid, name="wc")
        service.add_task(
            db, run=run, name="count", kind="example.wordcount", inputs={"text": "hello world foo"}
        )
        service.start_run(db, run)
        run_id = run.id

    _fresh_worker().run()

    with SessionLocal() as db:
        run = db.get(Run, run_id)
        assert run.status == RunStatus.succeeded
        task = run.tasks[0]
        assert task.status == TaskStatus.succeeded
        assert task.outputs == {"words": 3, "chars": 15}

        execution = db.scalar(select_execution(run_id))
        assert execution is not None
        assert execution.status == AgentStatus.succeeded
        assert execution.verification["passed"] is True
        assert execution.input == {"text": "hello world foo"}



def test_spec_only_agent_fails_clearly(client: TestClient) -> None:
    pid = _pid(client)
    # Wire a non-runnable roster agent as a task kind to prove it fails honestly.
    reg = HandlerRegistry()
    reg.register("commander", build_agent_handler(registry.get("commander")))

    with SessionLocal() as db:
        run = service.create_run(db, project_id=pid, name="spec-only")
        service.add_task(db, run=run, name="c", kind="commander", max_attempts=1)
        service.start_run(db, run)
        run_id = run.id

    Worker(SessionLocal, registry=reg).run()

    with SessionLocal() as db:
        run = db.get(Run, run_id)
        assert run.status == RunStatus.failed
        assert run.tasks[0].status == TaskStatus.dead_letter
        execution = db.scalar(select_execution(run_id))
        assert execution.status == AgentStatus.failed
        assert "no executor" in (execution.error or "")


def test_agent_input_validation_failure_recorded(client: TestClient) -> None:
    pid = _pid(client)
    with SessionLocal() as db:
        run = service.create_run(db, project_id=pid, name="bad-input")
        # wordcount requires {"text": string}; give it the wrong type.
        service.add_task(
            db, run=run, name="c", kind="example.wordcount", inputs={"text": 123}, max_attempts=1
        )
        service.start_run(db, run)
        run_id = run.id

    _fresh_worker().run()

    with SessionLocal() as db:
        run = db.get(Run, run_id)
        assert run.tasks[0].status == TaskStatus.dead_letter
        execution = db.scalar(select_execution(run_id))
        assert execution.status == AgentStatus.failed
        assert "input schema" in (execution.error or "")
