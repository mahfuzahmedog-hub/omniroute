"""FastAPI application factory and ASGI entrypoint.

Wires together configuration, logging, correlation middleware, CORS, the standardized
error handlers, and the versioned API router. Import ``app`` (e.g.
``uvicorn forge.main:app``) to serve the control plane.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from forge import __version__
from forge.api import api_router
from forge.config import get_settings
from forge.core.correlation import CorrelationMiddleware
from forge.core.errors import register_exception_handlers
from forge.logging import configure_logging, get_logger


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = get_logger("forge.main")

    app = FastAPI(
        title="Forge Control Plane",
        version=__version__,
        description="Autonomous software engineering platform — control plane API.",
        openapi_url=f"{settings.api_v1_prefix}/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Middleware order: correlation runs outermost so every log line is stamped.
    app.add_middleware(CorrelationMiddleware)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-Request-ID"],
        )

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    logger.info(
        "app_started",
        extra={"extra": {"environment": settings.environment.value, "version": __version__}},
    )
    return app


app = create_app()
