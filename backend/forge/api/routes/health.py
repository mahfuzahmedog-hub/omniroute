"""Health and readiness probes."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from forge import __version__
from forge.config import get_settings
from forge.core.deps import DbSession
from forge.schemas.common import HealthStatus

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthStatus)
def health(db: DbSession) -> HealthStatus:
    """Liveness + readiness: confirms the process is up and the database is reachable."""
    settings = get_settings()
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except Exception:  # noqa: BLE001 - report degraded rather than crash the probe
        database = "unavailable"
    return HealthStatus(
        status="ok" if database == "ok" else "degraded",
        version=__version__,
        environment=settings.environment.value,
        database=database,
    )
