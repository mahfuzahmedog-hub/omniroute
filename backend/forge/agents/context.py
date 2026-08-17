"""Agent context assembly.

Spec 04_AGENT_SYSTEM requires agent isolation: "Agents must receive only the context and
tools required for the current task." Rather than dumping the whole project into the
agent, :func:`assemble_context` gathers a focused bundle — the project goal, the run, the
task inputs, the outputs of the task's direct dependencies, and recent failure signals —
and the :class:`AgentContext` enforces the agent's resource budget as it runs.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from forge.agents.contract import Agent, AgentBudget, BudgetExceeded
from forge.models.audit import AuditEvent
from forge.models.project import Project
from forge.models.run import Run
from forge.models.task import Task, TaskDependency

_FAILURE_ACTIONS = ("task.retry", "task.dead_letter")


@dataclass
class AgentContext:
    """What an agent executor receives. Tracks and enforces the agent's budget."""

    db: Session
    agent: Agent
    project: Project
    run: Run
    task: Task
    inputs: dict
    # Outputs of the task's direct dependencies, keyed by the dependency task name.
    upstream_outputs: dict[str, dict]
    assembled: dict = field(default_factory=dict)
    tokens_used: int = 0
    cost_usd: float = 0.0
    _started_at: float = field(default_factory=time.perf_counter)

    def record_usage(self, *, tokens: int = 0, cost_usd: float = 0.0) -> None:
        """Account for model/tool usage and enforce the agent's budget."""
        self.tokens_used += tokens
        self.cost_usd += cost_usd
        budget: AgentBudget = self.agent.budget
        if budget.max_tokens is not None and self.tokens_used > budget.max_tokens:
            raise BudgetExceeded(
                f"token budget exceeded: {self.tokens_used} > {budget.max_tokens}"
            )
        if budget.max_usd is not None and self.cost_usd > budget.max_usd:
            raise BudgetExceeded(f"cost budget exceeded: ${self.cost_usd} > ${budget.max_usd}")

    @property
    def elapsed_seconds(self) -> float:
        return time.perf_counter() - self._started_at


def _upstream_outputs(db: Session, task: Task) -> dict[str, dict]:
    deps = db.scalars(
        select(Task)
        .join(TaskDependency, TaskDependency.depends_on_id == Task.id)
        .where(TaskDependency.task_id == task.id)
    ).all()
    return {dep.name: (dep.outputs or {}) for dep in deps}


def assemble_context(db: Session, agent: Agent, task: Task) -> AgentContext:
    """Build a focused :class:`AgentContext` for ``agent`` executing ``task``."""
    project = db.get(Project, task.project_id)
    run = db.get(Run, task.run_id)
    upstream = _upstream_outputs(db, task)

    recent_failures = db.scalars(
        select(AuditEvent.action)
        .where(
            AuditEvent.resource_type == "task",
            AuditEvent.action.in_(_FAILURE_ACTIONS),
        )
        .order_by(AuditEvent.created_at.desc())
        .limit(5)
    ).all()

    assembled = {
        "project": {"name": project.name, "specification": project.specification},
        "run": {"name": run.name},
        "task": {"name": task.name, "kind": task.kind},
        "dependencies": upstream,
        "recent_failure_signals": list(recent_failures),
    }
    return AgentContext(
        db=db,
        agent=agent,
        project=project,
        run=run,
        task=task,
        inputs=task.inputs or {},
        upstream_outputs=upstream,
        assembled=assembled,
    )
