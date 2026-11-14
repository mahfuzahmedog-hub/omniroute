"""Versioned API router aggregator.

All Phase 1 domains mount under a single versioned prefix so the surface can evolve
without breaking existing clients (spec ``22_API``: "Version APIs").
"""

from __future__ import annotations

from fastapi import APIRouter

from forge.api.routes import agents, auth, health, projects, runs, tools, workspaces

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(workspaces.router)
api_router.include_router(projects.router)
api_router.include_router(runs.router)
api_router.include_router(agents.catalog_router)
api_router.include_router(agents.executions_router)
api_router.include_router(tools.catalog_router)
api_router.include_router(tools.project_router)
