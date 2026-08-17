"""Worker runtime and handler registry.

A worker is the data-plane executor that drains the durable queue: it claims a task,
runs the handler registered for the task's ``kind``, and settles the result (success,
or failure which triggers retry/dead-letter). Workers are stateless and horizontally
scalable — all durable state lives in the database, so any number of workers (across
processes or machines) can share the load, and a crashed worker's in-flight task is
reclaimed by the lease reaper.

Handlers are plain callables registered by kind. They receive a :class:`TaskContext`
exposing the task inputs, a durable checkpoint, and lease/heartbeat helpers, and they
signal failure simply by raising.
"""

from __future__ import annotations

import logging
import socket
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from forge.models.task import Task
from forge.orchestration import service

logger = logging.getLogger("forge.worker")


@dataclass
class TaskContext:
    """What a handler is given to do its work."""

    db: Session
    task: Task
    worker_id: str

    @property
    def inputs(self) -> dict:
        return self.task.inputs or {}

    @property
    def checkpoint(self) -> dict | None:
        return self.task.checkpoint

    def set_checkpoint(self, checkpoint: dict) -> None:
        service.set_checkpoint(self.db, self.task, checkpoint)

    def heartbeat(self, lease_seconds: int = service.DEFAULT_LEASE_SECONDS) -> bool:
        return service.heartbeat(
            self.db, self.task, worker_id=self.worker_id, lease_seconds=lease_seconds
        )


Handler = Callable[[TaskContext], "dict | None"]


class HandlerRegistry:
    """Maps a task ``kind`` to the callable that executes it."""

    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}

    def register(self, kind: str, handler: Handler | None = None):
        """Register a handler. Usable directly or as a decorator."""

        def _register(func: Handler) -> Handler:
            self._handlers[kind] = func
            return func

        return _register if handler is None else _register(handler)

    def get(self, kind: str) -> Handler | None:
        return self._handlers.get(kind)

    def kinds(self) -> list[str]:
        return sorted(self._handlers)


# A process-wide default registry with a couple of built-in handlers.
registry = HandlerRegistry()


@registry.register("noop")
def _noop_handler(_ctx: TaskContext) -> dict:
    """A task that does nothing successfully — useful as a graph join point."""
    return {}


@registry.register("echo")
def _echo_handler(ctx: TaskContext) -> dict:
    """Return the task inputs as outputs."""
    return {"echo": ctx.inputs}


class Worker:
    """Drains the durable task queue using a handler registry."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        registry: HandlerRegistry = registry,
        worker_id: str | None = None,
        lease_seconds: int = service.DEFAULT_LEASE_SECONDS,
    ) -> None:
        self._session_factory = session_factory
        self._registry = registry
        self.worker_id = worker_id or f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
        self._lease_seconds = lease_seconds

    def run_once(self, db: Session) -> bool:
        """Claim and execute a single task. Returns False if the queue was empty."""
        task = service.claim_next_task(
            db, worker_id=self.worker_id, lease_seconds=self._lease_seconds
        )
        if task is None:
            return False

        handler = self._registry.get(task.kind)
        if handler is None:
            service.complete_task(
                db, task, success=False, error=f"No handler registered for kind '{task.kind}'"
            )
            logger.warning("no_handler", extra={"extra": {"kind": task.kind}})
            return True

        ctx = TaskContext(db=db, task=task, worker_id=self.worker_id)
        try:
            outputs = handler(ctx) or {}
            service.complete_task(db, task, success=True, outputs=outputs)
        except Exception as exc:  # noqa: BLE001 - failures are expected and recorded
            db.rollback()
            service.complete_task(db, task, success=False, error=str(exc))
            logger.info(
                "task_failed",
                extra={"extra": {"task_id": str(task.id), "error": str(exc)}},
            )
        return True

    def run(self, *, max_iterations: int = 1000, reap: bool = True) -> int:
        """Drain the queue until empty (or ``max_iterations`` reached).

        Returns the number of tasks executed. Reaps expired leases each pass so this
        single call also recovers work abandoned by crashed workers.
        """
        executed = 0
        db = self._session_factory()
        try:
            for _ in range(max_iterations):
                if reap:
                    service.reap_expired_leases(db)
                if not self.run_once(db):
                    break
                executed += 1
        finally:
            db.close()
        return executed


def run_forever(session_factory: Callable[[], Session]) -> None:  # pragma: no cover - CLI loop
    """Entrypoint for a standalone worker process."""
    import time

    # Wire runnable agents (Phase 3) in as task kinds on the default registry.
    from forge.agents.runner import register_agents

    register_agents()

    worker = Worker(session_factory)
    logger.info("worker_start", extra={"extra": {"worker_id": worker.worker_id}})
    db = session_factory()
    try:
        while True:
            service.reap_expired_leases(db)
            if not worker.run_once(db):
                time.sleep(1.0)
    finally:
        db.close()


if __name__ == "__main__":  # pragma: no cover
    # Import from the canonical module path (not the __main__ copy created by `-m`) so the
    # worker and register_agents() share the same handler registry object.
    from forge.db import SessionLocal
    from forge.logging import configure_logging
    from forge.orchestration.worker import run_forever as _run_forever

    configure_logging()
    _run_forever(SessionLocal)
