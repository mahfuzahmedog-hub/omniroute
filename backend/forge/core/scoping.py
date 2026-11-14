"""Workspace-scoped ownership lookups.

A resource is reachable only through the workspace that owns it. A project that does not
belong to the given workspace, or a run that does not belong to the given project, is
reported as 404 (not 403) so a caller cannot probe which IDs exist. Every route that takes
a resource in a workspace path goes through these two functions, so this is the one place
the isolation rule is written.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from forge.core.errors import ApiError
from forge.models.project import Project
from forge.models.run import Run


def get_workspace_project(db: Session, workspace_id: uuid.UUID, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.workspace_id != workspace_id:
        raise ApiError.not_found("Project not found")
    return project


def get_project_run(db: Session, project_id: uuid.UUID, run_id: uuid.UUID) -> Run:
    run = db.get(Run, run_id)
    if run is None or run.project_id != project_id:
        raise ApiError.not_found("Run not found")
    return run
