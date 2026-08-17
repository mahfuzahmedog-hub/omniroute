"""Bridge agents onto the durable task queue.

An agent runs as a task whose ``kind`` equals the agent's ``key``. This wrapper turns an
:class:`Agent` into a worker :data:`Handler` that: assembles a focused context, validates
inputs against the agent's schema, records a durable :class:`AgentExecution` for the
attempt, runs the executor under its budget, verifies the outputs, and only then reports
success. Any failure raises so the Phase 2 engine applies retries/dead-lettering.
"""

from __future__ import annotations

from forge.agents.context import assemble_context
from forge.agents.contract import Agent, AgentNotRunnable, VerificationError
from forge.agents.registry import AgentRegistry
from forge.agents.registry import registry as default_registry
from forge.agents.verification import SchemaValidationError, run_verification, validate_schema
from forge.models.agent_execution import AgentExecution, AgentStatus
from forge.models.base import utcnow
from forge.orchestration.worker import HandlerRegistry, TaskContext
from forge.orchestration.worker import registry as default_worker_registry


def build_agent_handler(agent: Agent):
    """Return a task handler that runs ``agent`` and records an AgentExecution."""

    def handler(task_ctx: TaskContext) -> dict:
        db = task_ctx.db
        task = task_ctx.task
        ctx = assemble_context(db, agent, task)

        execution = AgentExecution(
            task_id=task.id,
            run_id=task.run_id,
            project_id=task.project_id,
            agent_key=agent.key,
            role=agent.role,
            status=AgentStatus.running,
            input=ctx.inputs,
            model=agent.model_policy.get("class"),
            started_at=utcnow(),
        )
        db.add(execution)
        db.flush()

        def _fail(error: str) -> None:
            execution.status = AgentStatus.failed
            execution.error = error
            execution.finished_at = utcnow()
            db.commit()

        # Least-privilege + runnability + input validation, each recorded on the attempt.
        if not agent.runnable:
            _fail("Agent has no executor yet (model runtime pending)")
            raise AgentNotRunnable(agent.key)
        try:
            validate_schema(ctx.inputs, agent.input_schema)
        except SchemaValidationError as exc:
            _fail(f"input schema: {exc}")
            raise

        try:
            outputs = agent.execute(ctx) or {}
        except Exception as exc:  # noqa: BLE001 - recorded then re-raised for the engine
            _fail(str(exc))
            raise

        execution.status = AgentStatus.verifying
        result = run_verification(agent, ctx, outputs)
        execution.output = outputs
        execution.verification = result.to_dict()
        execution.tokens_used = ctx.tokens_used
        execution.cost_usd = ctx.cost_usd

        if not result.passed:
            failed = [c.name for c in result.checks if not c.passed]
            _fail(f"verification failed: {', '.join(failed)}")
            raise VerificationError(f"{agent.key}: {failed}")

        execution.status = AgentStatus.succeeded
        execution.finished_at = utcnow()
        db.commit()
        return outputs

    return handler


def register_agents(
    worker_registry: HandlerRegistry = default_worker_registry,
    agent_registry: AgentRegistry = default_registry,
) -> list[str]:
    """Wire every runnable agent into the worker registry as a task kind.

    Returns the list of agent keys that were registered as handlers.
    """
    registered: list[str] = []
    for key in agent_registry.runnable_keys():
        agent = agent_registry.get(key)
        if worker_registry.get(key) is None:
            worker_registry.register(key, build_agent_handler(agent))
            registered.append(key)
    return registered
