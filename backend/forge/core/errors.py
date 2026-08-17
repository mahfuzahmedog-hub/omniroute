"""Standardized error model.

The API spec requires "stable error codes" and a consistent shape. We define a single
:class:`ApiError` exception carrying a machine-readable code, HTTP status, and human
message, plus FastAPI handlers that render every error — including validation and
unexpected errors — into one envelope:

    {"error": {"code": "not_found", "message": "...", "details": {...},
               "correlation_id": "..."}}
"""

from __future__ import annotations

from enum import StrEnum

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from forge.logging import correlation_id_var, get_logger

logger = get_logger("forge.errors")


class ErrorCode(StrEnum):
    """Stable, machine-readable error codes returned to clients."""

    validation_error = "validation_error"
    unauthorized = "unauthorized"
    forbidden = "forbidden"
    not_found = "not_found"
    conflict = "conflict"
    rate_limited = "rate_limited"
    internal_error = "internal_error"


class ApiError(Exception):
    """Application error mapped deterministically to an HTTP response."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        status_code: int,
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details

    # Convenience constructors for the common cases keep call sites terse and consistent.
    @classmethod
    def not_found(cls, message: str = "Resource not found", **kw) -> ApiError:
        return cls(ErrorCode.not_found, message, status_code=status.HTTP_404_NOT_FOUND, **kw)

    @classmethod
    def unauthorized(cls, message: str = "Not authenticated", **kw) -> ApiError:
        return cls(ErrorCode.unauthorized, message, status_code=status.HTTP_401_UNAUTHORIZED, **kw)

    @classmethod
    def forbidden(cls, message: str = "Not permitted", **kw) -> ApiError:
        return cls(ErrorCode.forbidden, message, status_code=status.HTTP_403_FORBIDDEN, **kw)

    @classmethod
    def conflict(cls, message: str = "Conflict", **kw) -> ApiError:
        return cls(ErrorCode.conflict, message, status_code=status.HTTP_409_CONFLICT, **kw)


def _envelope(code: str, message: str, details: dict | None = None) -> dict:
    body: dict = {"code": code, "message": message}
    if details:
        body["details"] = details
    correlation_id = correlation_id_var.get()
    if correlation_id:
        body["correlation_id"] = correlation_id
    return {"error": body}


def register_exception_handlers(app: FastAPI) -> None:
    """Install handlers that render every error into the standard envelope."""

    @app.exception_handler(ApiError)
    async def _handle_api_error(_request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code.value, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_envelope(
                ErrorCode.validation_error.value,
                "Request validation failed",
                {"errors": exc.errors()},
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {
            status.HTTP_401_UNAUTHORIZED: ErrorCode.unauthorized,
            status.HTTP_403_FORBIDDEN: ErrorCode.forbidden,
            status.HTTP_404_NOT_FOUND: ErrorCode.not_found,
            status.HTTP_409_CONFLICT: ErrorCode.conflict,
        }.get(exc.status_code, ErrorCode.internal_error)
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(code.value, str(exc.detail)),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(_request: Request, exc: Exception) -> JSONResponse:
        # Never leak internal details to the client; log the full error server-side.
        logger.error("unhandled_exception", exc_info=exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope(ErrorCode.internal_error.value, "Internal server error"),
        )
