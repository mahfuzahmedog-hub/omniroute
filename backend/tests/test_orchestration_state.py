"""State-machine contracts for runs and tasks."""

from __future__ import annotations

import pytest

from forge.models.run import RunStatus
from forge.models.task import TaskStatus
from forge.orchestration.state import (
    InvalidTransition,
    assert_run_transition,
    assert_task_transition,
    can_transition_task,
)


def test_valid_task_transitions() -> None:
    assert can_transition_task(TaskStatus.pending, TaskStatus.ready)
    assert can_transition_task(TaskStatus.ready, TaskStatus.running)
    assert can_transition_task(TaskStatus.running, TaskStatus.succeeded)
    assert can_transition_task(TaskStatus.running, TaskStatus.ready)  # retry
    assert can_transition_task(TaskStatus.running, TaskStatus.dead_letter)


def test_terminal_task_states_have_no_exits() -> None:
    for terminal in (
        TaskStatus.succeeded,
        TaskStatus.failed,
        TaskStatus.cancelled,
        TaskStatus.dead_letter,
    ):
        assert not can_transition_task(terminal, TaskStatus.ready)


def test_illegal_task_transition_raises() -> None:
    with pytest.raises(InvalidTransition):
        assert_task_transition(TaskStatus.pending, TaskStatus.running)  # must go via ready
    with pytest.raises(InvalidTransition):
        assert_task_transition(TaskStatus.succeeded, TaskStatus.running)


def test_run_transitions() -> None:
    assert_run_transition(RunStatus.pending, RunStatus.running)
    assert_run_transition(RunStatus.running, RunStatus.succeeded)
    with pytest.raises(InvalidTransition):
        assert_run_transition(RunStatus.succeeded, RunStatus.running)
