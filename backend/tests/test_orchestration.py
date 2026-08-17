"""Orchestration engine contracts: scheduling, leases, retries, cancellation, recovery.

These exercise the durable execution core directly against the database, using an
injectable clock to make time-based behavior (retry backoff, lease expiry) deterministic.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from forge.db import SessionLocal
from forge.models.base import utcnow
from forge.models.run import Run, RunStatus
from forge.models.task import Task, TaskStatus
from forge.orchestration import service
from forge.orchestration.worker import HandlerRegistry, TaskContext, Worker
from tests.conftest import seed_project


def _project_id(client: TestClient) -> uuid.UUID:
    return uuid.UUID(seed_project(client)["project_id"])


def select_task(run_id: uuid.UUID, name: str):
    return select(Task).where(Task.run_id == run_id, Task.name == name)


def test_dependency_gating(client: TestClient) -> None:
    pid = _project_id(client)
    with SessionLocal() as db:
        run = service.create_run(db, project_id=pid, name="pipeline")
        a = service.add_task(db, run=run, name="A", kind="noop")
        b = service.add_task(db, run=run, name="B", kind="noop", depends_on=[a.id])
        service.start_run(db, run)

        # A has no deps → ready; B depends on A → still pending.
        db.refresh(a)
        db.refresh(b)
        assert a.status == TaskStatus.ready
        assert b.status == TaskStatus.pending

        # Claim + succeed A; now B should be promoted to ready.
        claimed = service.claim_next_task(db, worker_id="w1")
        assert claimed is not None and claimed.id == a.id
        service.complete_task(db, claimed, success=True, outputs={})
        db.refresh(b)
        assert b.status == TaskStatus.ready


def test_worker_runs_linear_pipeline(client: TestClient) -> None:
    pid = _project_id(client)
    reg = HandlerRegistry()

    @reg.register("double")
    def _double(ctx: TaskContext) -> dict:
        return {"value": ctx.inputs.get("value", 0) * 2}

    reg.register("noop", lambda _ctx: {})

    with SessionLocal() as db:
        run = service.create_run(db, project_id=pid, name="pipeline")
        a = service.add_task(db, run=run, name="A", kind="double", inputs={"value": 21})
        service.add_task(db, run=run, name="B", kind="noop", depends_on=[a.id])
        service.start_run(db, run)
        run_id = run.id

    executed = Worker(SessionLocal, registry=reg).run()
    assert executed == 2

    with SessionLocal() as db:
        run = db.get(Run, run_id)
        assert run.status == RunStatus.succeeded
        task_a = db.scalars(select_task(run_id, "A")).one()
        assert task_a.outputs == {"value": 42}


def test_retry_then_dead_letter(client: TestClient) -> None:
    pid = _project_id(client)
    with SessionLocal() as db:
        run = service.create_run(db, project_id=pid, name="flaky")
        task = service.add_task(db, run=run, name="always-fails", kind="boom", max_attempts=3)
        service.start_run(db, run)
        task_id = task.id
        t0 = utcnow()  # after tasks exist, so their available_at <= t0

        # Attempt 1
        claimed = service.claim_next_task(db, worker_id="w1", now=t0)
        assert claimed.id == task_id
        service.complete_task(db, claimed, success=False, error="boom", now=t0)
        db.refresh(claimed)
        assert claimed.status == TaskStatus.ready
        assert claimed.attempts == 1
        assert claimed.available_at > t0  # backoff applied

        # Too early to reclaim
        assert service.claim_next_task(db, worker_id="w1", now=t0) is None

        # Attempt 2
        t2 = t0 + timedelta(seconds=5)
        claimed = service.claim_next_task(db, worker_id="w1", now=t2)
        assert claimed is not None and claimed.attempts == 2
        service.complete_task(db, claimed, success=False, error="boom", now=t2)

        # Attempt 3 (final) → dead_letter, run → failed
        t3 = t0 + timedelta(seconds=60)
        claimed = service.claim_next_task(db, worker_id="w1", now=t3)
        assert claimed is not None and claimed.attempts == 3
        service.complete_task(db, claimed, success=False, error="boom", now=t3)
        db.refresh(claimed)
        assert claimed.status == TaskStatus.dead_letter

        run = db.get(Run, run.id)
        assert run.status == RunStatus.failed


def test_retry_then_success(client: TestClient) -> None:
    pid = _project_id(client)
    with SessionLocal() as db:
        run = service.create_run(db, project_id=pid, name="recoverable")
        task = service.add_task(db, run=run, name="flaky", kind="x", max_attempts=3)
        service.start_run(db, run)
        t0 = utcnow()

        c1 = service.claim_next_task(db, worker_id="w1", now=t0)
        service.complete_task(db, c1, success=False, error="transient", now=t0)

        t2 = t0 + timedelta(seconds=5)
        c2 = service.claim_next_task(db, worker_id="w1", now=t2)
        service.complete_task(db, c2, success=True, outputs={"ok": True}, now=t2)

        db.refresh(task)
        assert task.status == TaskStatus.succeeded
        run = db.get(Run, run.id)
        assert run.status == RunStatus.succeeded


def test_lease_reclaimed_after_crash(client: TestClient) -> None:
    pid = _project_id(client)
    with SessionLocal() as db:
        run = service.create_run(db, project_id=pid, name="crashy")
        task = service.add_task(db, run=run, name="t", kind="noop")
        service.start_run(db, run)
        t0 = utcnow()

        # Worker A claims with a short lease, then "crashes" (never completes).
        claimed = service.claim_next_task(db, worker_id="A", lease_seconds=30, now=t0)
        assert claimed.status == TaskStatus.running

        # Before expiry: nothing to reap.
        assert service.reap_expired_leases(db, now=t0 + timedelta(seconds=10)) == 0

        # After expiry: the task is reclaimed to ready and claimable again.
        assert service.reap_expired_leases(db, now=t0 + timedelta(seconds=31)) == 1
        db.refresh(task)
        assert task.status == TaskStatus.ready
        again = service.claim_next_task(db, worker_id="B", now=t0 + timedelta(seconds=31))
        assert again is not None and again.lease_owner == "B"


def test_heartbeat_extends_lease(client: TestClient) -> None:
    pid = _project_id(client)
    with SessionLocal() as db:
        run = service.create_run(db, project_id=pid, name="hb")
        service.add_task(db, run=run, name="t", kind="noop")
        service.start_run(db, run)
        t0 = utcnow()
        claimed = service.claim_next_task(db, worker_id="A", lease_seconds=30, now=t0)

        # Heartbeat at t+20 pushes the lease to t+20+30 = t+50.
        service.heartbeat(
            db, claimed, worker_id="A", lease_seconds=30, now=t0 + timedelta(seconds=20)
        )
        # So a reap at t+31 finds nothing to reclaim.
        assert service.reap_expired_leases(db, now=t0 + timedelta(seconds=31)) == 0


def test_claim_is_exclusive_under_contention(client: TestClient) -> None:
    pid = _project_id(client)
    with SessionLocal() as setup:
        run = service.create_run(setup, project_id=pid, name="race")
        service.add_task(setup, run=run, name="only", kind="noop")
        service.start_run(setup, run)

    # Two workers with independent sessions race for the single ready task.
    s1, s2 = SessionLocal(), SessionLocal()
    try:
        claimed = [
            service.claim_next_task(s1, worker_id="w1"),
            service.claim_next_task(s2, worker_id="w2"),
        ]
    finally:
        s1.close()
        s2.close()
    winners = [c for c in claimed if c is not None]
    assert len(winners) == 1  # exactly one worker won the task


def test_cancel_run_propagates(client: TestClient) -> None:
    pid = _project_id(client)
    with SessionLocal() as db:
        run = service.create_run(db, project_id=pid, name="cancelme")
        a = service.add_task(db, run=run, name="A", kind="noop")
        service.add_task(db, run=run, name="B", kind="noop", depends_on=[a.id])
        service.start_run(db, run)

        service.cancel_run(db, run)
        db.refresh(run)
        assert run.status == RunStatus.cancelled
        statuses = {t.name: t.status for t in run.tasks}
        assert statuses["A"] == TaskStatus.cancelled
        assert statuses["B"] == TaskStatus.cancelled


def test_cancel_honored_for_running_task(client: TestClient) -> None:
    pid = _project_id(client)
    with SessionLocal() as db:
        run = service.create_run(db, project_id=pid, name="cancel-running")
        service.add_task(db, run=run, name="t", kind="noop")
        service.start_run(db, run)
        claimed = service.claim_next_task(db, worker_id="A")

        service.cancel_run(db, run)  # run cancelled; running task flagged
        db.refresh(claimed)
        assert claimed.cancel_requested is True

        # Even though the handler "succeeded", the pending cancel wins.
        service.complete_task(db, claimed, success=True, outputs={})
        db.refresh(claimed)
        assert claimed.status == TaskStatus.cancelled


def test_unknown_kind_dead_letters(client: TestClient) -> None:
    pid = _project_id(client)
    with SessionLocal() as db:
        run = service.create_run(db, project_id=pid, name="mystery")
        service.add_task(db, run=run, name="t", kind="does-not-exist", max_attempts=1)
        service.start_run(db, run)
        run_id = run.id

    Worker(SessionLocal, registry=HandlerRegistry()).run()

    with SessionLocal() as db:
        run = db.get(Run, run_id)
        assert run.status == RunStatus.failed
        task = run.tasks[0]
        assert task.status == TaskStatus.dead_letter
        assert "No handler" in (task.error or "")


def test_state_survives_fresh_session(client: TestClient) -> None:
    """Durability: run state persists and a new session/worker resumes it."""
    pid = _project_id(client)
    with SessionLocal() as db:
        run = service.create_run(db, project_id=pid, name="durable")
        a = service.add_task(db, run=run, name="A", kind="noop")
        service.add_task(db, run=run, name="B", kind="noop", depends_on=[a.id])
        service.start_run(db, run)
        run_id = run.id

    # Simulate a restart: brand-new session + worker, nothing in memory.
    Worker(SessionLocal).run()

    with SessionLocal() as db:
        run = db.get(Run, run_id)
        assert run.status == RunStatus.succeeded
        assert all(t.status == TaskStatus.succeeded for t in run.tasks)
