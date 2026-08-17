"""Orchestration service — the durable execution engine.

This module is the control-plane logic for Phase 2. It deliberately uses the database
as the durable queue (there is no in-memory work list), so runs survive API restarts and
worker crashes and can be resumed. Concurrency safety comes from the task ``version``
counter: two workers racing to claim the same task cannot both win, because the second
UPDATE matches zero rows and raises ``StaleDataError``.

All functions accept an injectable ``now`` for deterministic testing of time-based
behavior (retry backoff, lease expiry).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from forge.models.base import utcnow
from forge.models.run import Run, RunStatus
from forge.models.task import Task, TaskDependency, TaskStatus
from forge.orchestration.state import assert_run_transition, assert_task_transition
from forge.services.audit import record_event

DEFAULT_LEASE_SECONDS = 60
DEFAULT_MAX_ATTEMPTS = 3
_BACKOFF_BASE_SECONDS = 2
_BACKOFF_CAP_SECONDS = 300


def retry_backoff_seconds(attempts: int, *, base: int = _BACKOFF_BASE_SECONDS) -> int:
    """Exponential backoff (capped) for the ``attempts``-th failed try."""
    if attempts <= 0:
        return 0
    return min(base * (2 ** (attempts - 1)), _BACKOFF_CAP_SECONDS)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _set_task_status(task: Task, target: TaskStatus) -> None:
    assert_task_transition(task.status, target)
    task.status = target


def _set_run_status(run: Run, target: RunStatus) -> None:
    assert_run_transition(run.status, target)
    run.status = target


def _dependency_statuses(db: Session, task: Task) -> list[TaskStatus]:
    rows = db.scalars(
        select(Task.status)
        .join(TaskDependency, TaskDependency.depends_on_id == Task.id)
        .where(TaskDependency.task_id == task.id)
    ).all()
    return list(rows)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------
def create_run(
    db: Session,
    *,
    project_id: uuid.UUID,
    name: str,
    actor_user_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
) -> Run:
    run = Run(project_id=project_id, name=name, status=RunStatus.pending)
    db.add(run)
    db.flush()
    record_event(
        db,
        action="run.created",
        actor_user_id=actor_user_id,
        actor_type="user" if actor_user_id else "system",
        resource_type="run",
        resource_id=run.id,
        workspace_id=workspace_id,
    )
    db.commit()
    db.refresh(run)
    return run


def add_task(
    db: Session,
    *,
    run: Run,
    name: str,
    kind: str,
    inputs: dict | None = None,
    priority: int = 100,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    depends_on: Sequence[uuid.UUID] = (),
    actor_user_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
) -> Task:
    """Add a task to a *pending* run, optionally depending on sibling tasks."""
    if run.status != RunStatus.pending:
        raise ValueError("Tasks can only be added while the run is pending")

    task = Task(
        run_id=run.id,
        project_id=run.project_id,
        name=name,
        kind=kind,
        inputs=inputs,
        priority=priority,
        max_attempts=max_attempts,
        status=TaskStatus.pending,
    )
    db.add(task)
    db.flush()

    for dep_id in depends_on:
        dep = db.get(Task, dep_id)
        if dep is None or dep.run_id != run.id:
            raise ValueError(f"Dependency {dep_id} is not a task in this run")
        db.add(TaskDependency(task_id=task.id, depends_on_id=dep_id))

    record_event(
        db,
        action="task.created",
        actor_user_id=actor_user_id,
        actor_type="user" if actor_user_id else "system",
        resource_type="task",
        resource_id=task.id,
        workspace_id=workspace_id,
        metadata={"kind": kind},
    )
    db.commit()
    db.refresh(task)
    return task


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------
def promote_ready(db: Session, run: Run) -> int:
    """Advance the run's task graph: gate pending tasks on their dependencies.

    A pending task whose dependencies all succeeded becomes ``ready``. A pending task
    with any dependency that failed/dead-lettered/cancelled is itself ``cancelled``
    (it can never run). Runs until stable so cancellations cascade. Returns the number
    of tasks changed.
    """
    if run.status != RunStatus.running:
        return 0

    failed_states = {TaskStatus.failed, TaskStatus.dead_letter, TaskStatus.cancelled}
    total_changed = 0
    changed = True
    while changed:
        changed = False
        pending = db.scalars(
            select(Task).where(Task.run_id == run.id, Task.status == TaskStatus.pending)
        ).all()
        for task in pending:
            dep_statuses = _dependency_statuses(db, task)
            if any(s in failed_states for s in dep_statuses):
                _set_task_status(task, TaskStatus.cancelled)
                task.error = "A dependency did not succeed"
                task.finished_at = utcnow()
                changed = True
                total_changed += 1
            elif all(s == TaskStatus.succeeded for s in dep_statuses):
                _set_task_status(task, TaskStatus.ready)
                changed = True
                total_changed += 1
    if total_changed:
        db.flush()
    return total_changed


def start_run(
    db: Session,
    run: Run,
    *,
    actor_user_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
) -> Run:
    """Move a pending run to running and promote its dependency-free tasks to ready."""
    _set_run_status(run, RunStatus.running)
    run.started_at = utcnow()
    record_event(
        db,
        action="run.started",
        actor_user_id=actor_user_id,
        actor_type="user" if actor_user_id else "system",
        resource_type="run",
        resource_id=run.id,
        workspace_id=workspace_id,
    )
    promote_ready(db, run)
    db.commit()
    db.refresh(run)
    return run


def _finalize_run_if_done(db: Session, run: Run) -> None:
    """If every task is terminal, settle the run's final status."""
    if run.status != RunStatus.running:
        return
    statuses = db.scalars(select(Task.status).where(Task.run_id == run.id)).all()
    if not statuses or any(not s.is_terminal() for s in statuses):
        return
    if any(s in (TaskStatus.failed, TaskStatus.dead_letter) for s in statuses):
        target = RunStatus.failed
    elif any(s == TaskStatus.cancelled for s in statuses):
        target = RunStatus.cancelled
    else:
        target = RunStatus.succeeded
    _set_run_status(run, target)
    run.finished_at = utcnow()
    record_event(
        db,
        action="run.finished",
        actor_type="system",
        resource_type="run",
        resource_id=run.id,
        metadata={"status": target.value},
    )


# ---------------------------------------------------------------------------
# The durable queue: claim / heartbeat / complete / reap
# ---------------------------------------------------------------------------
def claim_next_task(
    db: Session,
    *,
    worker_id: str,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    kinds: Sequence[str] | None = None,
    now: datetime | None = None,
) -> Task | None:
    """Atomically lease the highest-priority runnable task, or return ``None``.

    Exclusivity relies on optimistic concurrency: if another worker claims a candidate
    first, our conditional UPDATE matches zero rows (``StaleDataError``) and we try the
    next candidate.
    """
    now = now or utcnow()
    stmt = (
        select(Task.id)
        .where(Task.status == TaskStatus.ready, Task.available_at <= now)
        .order_by(Task.priority.asc(), Task.created_at.asc())
        .limit(20)
    )
    if kinds is not None:
        stmt = stmt.where(Task.kind.in_(list(kinds)))
    candidate_ids = db.scalars(stmt).all()

    for task_id in candidate_ids:
        task = db.get(Task, task_id)
        if task is None or task.status != TaskStatus.ready or task.available_at > now:
            continue
        _set_task_status(task, TaskStatus.running)
        task.attempts += 1
        task.lease_owner = worker_id
        task.lease_expires_at = now + timedelta(seconds=lease_seconds)
        if task.started_at is None:
            task.started_at = now
        try:
            db.commit()
        except StaleDataError:
            db.rollback()
            continue
        db.refresh(task)
        return task
    return None


def heartbeat(
    db: Session,
    task: Task,
    *,
    worker_id: str,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    now: datetime | None = None,
) -> bool:
    """Extend the lease on a running task the worker still owns."""
    now = now or utcnow()
    if task.status != TaskStatus.running or task.lease_owner != worker_id:
        return False
    task.lease_expires_at = now + timedelta(seconds=lease_seconds)
    db.commit()
    return True


def set_checkpoint(db: Session, task: Task, checkpoint: dict) -> None:
    """Durably persist partial progress so a resumed task need not start over."""
    task.checkpoint = checkpoint
    db.commit()


def complete_task(
    db: Session,
    task: Task,
    *,
    success: bool,
    outputs: dict | None = None,
    error: str | None = None,
    now: datetime | None = None,
) -> Task:
    """Settle a running task: succeed, retry with backoff, dead-letter, or cancel.

    Honors a pending cancellation request before recording success/failure.
    """
    now = now or utcnow()
    if task.status != TaskStatus.running:
        raise ValueError("Only a running task can be completed")

    run = db.get(Run, task.run_id)

    if task.cancel_requested:
        _set_task_status(task, TaskStatus.cancelled)
        task.finished_at = now
        task.lease_owner = None
        task.lease_expires_at = None
        _record_task_event(db, task, "task.cancelled")
    elif success:
        _set_task_status(task, TaskStatus.succeeded)
        task.outputs = outputs
        task.error = None
        task.finished_at = now
        task.lease_owner = None
        task.lease_expires_at = None
        _record_task_event(db, task, "task.succeeded")
    elif task.attempts < task.max_attempts:
        # Retry: return to the queue after a backoff so we don't hot-loop a flaky task.
        _set_task_status(task, TaskStatus.ready)
        task.error = error
        task.lease_owner = None
        task.lease_expires_at = None
        task.available_at = now + timedelta(seconds=retry_backoff_seconds(task.attempts))
        _record_task_event(db, task, "task.retry", {"attempt": task.attempts})
    else:
        # Retries exhausted: send to the dead-letter state for human/escalation review.
        _set_task_status(task, TaskStatus.dead_letter)
        task.error = error
        task.finished_at = now
        task.lease_owner = None
        task.lease_expires_at = None
        _record_task_event(db, task, "task.dead_letter", {"attempts": task.attempts})

    if run is not None:
        promote_ready(db, run)
        _finalize_run_if_done(db, run)
    db.commit()
    db.refresh(task)
    return task


def reap_expired_leases(db: Session, *, now: datetime | None = None) -> int:
    """Return crashed workers' tasks to the queue.

    A ``running`` task whose lease has expired is assumed abandoned (the worker died or
    hung) and is moved back to ``ready`` so another worker can pick it up. This is the
    core of resume-after-crash. Returns the number of tasks reclaimed.
    """
    now = now or utcnow()
    stale = db.scalars(
        select(Task).where(
            Task.status == TaskStatus.running,
            Task.lease_expires_at.is_not(None),
            Task.lease_expires_at < now,
        )
    ).all()
    for task in stale:
        _set_task_status(task, TaskStatus.ready)
        task.lease_owner = None
        task.lease_expires_at = None
        task.available_at = now
        _record_task_event(db, task, "task.reclaimed", {"attempts": task.attempts})
    if stale:
        db.commit()
    return len(stale)


def cancel_run(
    db: Session,
    run: Run,
    *,
    actor_user_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
) -> Run:
    """Cancel a run and propagate cancellation to its non-terminal tasks.

    Pending/ready tasks are cancelled immediately; running tasks are flagged so the
    owning worker cancels them cooperatively at its next completion boundary.
    """
    if run.status.is_terminal():
        return run

    tasks = db.scalars(select(Task).where(Task.run_id == run.id)).all()
    for task in tasks:
        if task.status in (TaskStatus.pending, TaskStatus.ready):
            _set_task_status(task, TaskStatus.cancelled)
            task.finished_at = utcnow()
            task.lease_owner = None
            task.lease_expires_at = None
        elif task.status == TaskStatus.running:
            task.cancel_requested = True

    _set_run_status(run, RunStatus.cancelled)
    run.finished_at = utcnow()
    record_event(
        db,
        action="run.cancelled",
        actor_user_id=actor_user_id,
        actor_type="user" if actor_user_id else "system",
        resource_type="run",
        resource_id=run.id,
        workspace_id=workspace_id,
    )
    db.commit()
    db.refresh(run)
    return run


def _record_task_event(db: Session, task: Task, action: str, metadata: dict | None = None) -> None:
    record_event(
        db,
        action=action,
        actor_type="system",
        resource_type="task",
        resource_id=task.id,
        metadata=metadata,
    )
