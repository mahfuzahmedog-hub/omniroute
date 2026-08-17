"""Validated state machines for runs and tasks.

The master spec requires that "state transitions must be validated". Rather than
scattering `if status == ...` checks across the codebase, we centralize the legal
transitions here. Any attempt to move a run or task along an illegal edge raises
:class:`InvalidTransition`, which the orchestration layer surfaces as a conflict.
"""

from __future__ import annotations

from forge.models.run import RunStatus
from forge.models.task import TaskStatus


class InvalidTransition(Exception):
    """Raised when a requested state transition is not permitted."""

    def __init__(self, entity: str, current: str, target: str) -> None:
        super().__init__(f"Illegal {entity} transition: {current} -> {target}")
        self.entity = entity
        self.current = current
        self.target = target


# Allowed task transitions. Terminal states have no outgoing edges.
_TASK_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.pending: {TaskStatus.ready, TaskStatus.cancelled},
    TaskStatus.ready: {TaskStatus.running, TaskStatus.cancelled},
    TaskStatus.running: {
        TaskStatus.succeeded,
        TaskStatus.failed,
        TaskStatus.ready,  # retry (with backoff) or lease reclamation after a crash
        TaskStatus.cancelled,
        TaskStatus.dead_letter,
    },
    TaskStatus.succeeded: set(),
    TaskStatus.failed: set(),
    TaskStatus.cancelled: set(),
    TaskStatus.dead_letter: set(),
}

# Allowed run transitions.
_RUN_TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.pending: {RunStatus.running, RunStatus.cancelled},
    RunStatus.running: {RunStatus.succeeded, RunStatus.failed, RunStatus.cancelled},
    RunStatus.succeeded: set(),
    RunStatus.failed: set(),
    RunStatus.cancelled: set(),
}


def can_transition_task(current: TaskStatus, target: TaskStatus) -> bool:
    return target in _TASK_TRANSITIONS[current]


def assert_task_transition(current: TaskStatus, target: TaskStatus) -> None:
    if not can_transition_task(current, target):
        raise InvalidTransition("task", current, target)


def can_transition_run(current: RunStatus, target: RunStatus) -> bool:
    return target in _RUN_TRANSITIONS[current]


def assert_run_transition(current: RunStatus, target: RunStatus) -> None:
    if not can_transition_run(current, target):
        raise InvalidTransition("run", current, target)
