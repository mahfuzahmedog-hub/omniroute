"""Correlation-ID and request-logging middleware.

Assigns a correlation ID to every request (honoring an inbound ``X-Request-ID`` when
present), binds it to the logging context, echoes it back in the response header, and
emits one structured access-log line per request. This is the spine of the observability
correlation chain: project → run → task → agent → tool/model call all reuse this ID.
"""

from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from forge.logging import correlation_id_var, get_logger

logger = get_logger("forge.request")

REQUEST_ID_HEADER = "X-Request-ID"


class CorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        correlation_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        token = correlation_id_var.set(correlation_id)
        request.state.correlation_id = correlation_id
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            correlation_id_var.reset(token)
        response.headers[REQUEST_ID_HEADER] = correlation_id
        logger.info(
            "request",
            extra={
                "extra": {
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                    "correlation_id": correlation_id,
                }
            },
        )
        return response
