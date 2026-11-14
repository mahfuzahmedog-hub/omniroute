"""Model registry.

Importing this package imports every model so that ``Base.metadata`` is complete for
migrations and test schema creation.
"""

from forge.models.agent_execution import AgentExecution, AgentStatus
from forge.models.audit import AuditEvent
from forge.models.base import Base
from forge.models.project import Project, ProjectStatus
from forge.models.run import Run, RunStatus
from forge.models.task import Task, TaskDependency, TaskStatus
from forge.models.tool import ProjectToolGrant, ToolInvocation, ToolInvocationStatus
from forge.models.user import User
from forge.models.workspace import Workspace, WorkspaceMembership, WorkspaceRole

__all__ = [
    "Base",
    "User",
    "Workspace",
    "WorkspaceMembership",
    "WorkspaceRole",
    "Project",
    "ProjectStatus",
    "AuditEvent",
    "Run",
    "RunStatus",
    "Task",
    "TaskDependency",
    "TaskStatus",
    "AgentExecution",
    "AgentStatus",
    "ProjectToolGrant",
    "ToolInvocation",
    "ToolInvocationStatus",
]
