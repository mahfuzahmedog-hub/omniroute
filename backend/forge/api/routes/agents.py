"""Agent catalog + agent-execution routes.

The catalog (``/agents``) is the read-only registry of known agent contracts. Execution
records are workspace-scoped, exposed under a run so a user can audit which agents ran,
with what inputs/outputs, and whether their verification contracts passed.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from sqlalchemy import select

from forge.agents.contract import Agent
from forge.agents.registry import registry as agent_registry
from forge.core.deps import CurrentUser, DbSession, require_workspace_membership
from forge.core.errors import ApiError
from forge.models.agent_execution import AgentExecution
from forge.models.project import Project
from forge.models.run import Run
from forge.schemas.agents import AgentExecutionOut, AgentOut, BudgetOut

catalog_router = APIRouter(prefix="/agents", tags=["agents"])
executions_router = APIRouter(
    prefix="/workspaces/{workspace_id}/projects/{project_id}", tags=["agents"]
)


def _to_out(agent: Agent) -> AgentOut:
    return AgentOut(
        key=agent.key,
        role=agent.role,
        objective=agent.objective,
        allowed_tools=sorted(agent.allowed_tools),
        model_policy=agent.model_policy,
        budget=BudgetOut(
            max_usd=agent.budget.max_usd,
            max_tokens=agent.budget.max_tokens,
            max_seconds=agent.budget.max_seconds,
        ),
        max_attempts=agent.max_attempts,
        escalation_target=agent.escalation_target,
        runnable=agent.runnable,
    )


@catalog_router.get("", response_model=list[AgentOut])
def list_agents(_user: CurrentUser) -> list[AgentOut]:
    """List every agent contract in the registry (the agent ecosystem)."""
    return [_to_out(a) for a in agent_registry.all()]


@catalog_router.get("/{key}", response_model=AgentOut)
def get_agent(key: str, _user: CurrentUser) -> AgentOut:
    agent = agent_registry.get(key)
    if agent is None:
        raise ApiError.not_found("Agent not found")
    return _to_out(agent)


@executions_router.get("/runs/{run_id}/agent-executions", response_model=list[AgentExecutionOut])
def list_agent_executions(
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
) -> list[AgentExecutionOut]:
    require_workspace_membership(workspace_id, db, user)
    project = db.get(Project, project_id)
    if project is None or project.workspace_id != workspace_id:
        raise ApiError.not_found("Project not found")
    run = db.get(Run, run_id)
    if run is None or run.project_id != project_id:
        raise ApiError.not_found("Run not found")
    executions = db.scalars(
        select(AgentExecution)
        .where(AgentExecution.run_id == run_id)
        .order_by(AgentExecution.created_at.asc())
    ).all()
    return [AgentExecutionOut.model_validate(e) for e in executions]
