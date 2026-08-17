"""Structured JSON logging with correlation IDs.

Observability (spec ``18_OBSERVABILITY``) requires that every event be traceable
through a correlation chain. We keep the current request's correlation ID in a
:class:`contextvars.ContextVar` so any log record emitted while handling a request is
automatically stamped with it, without threading the ID through every function call.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar

# The correlation ID for the in-flight request/task. Empty string when outside a request.
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


class JsonFormatter(logging.Formatter):
    """Render log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        correlation_id = correlation_id_var.get()
        if correlation_id:
            payload["correlation_id"] = correlation_id
        # Attach any structured extras passed via logger.info(..., extra={"extra": {...}}).
        extra = getattr(record, "extra", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Install the JSON formatter on the root logger (idempotent)."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())

    # Uvicorn's access log is noisy and duplicates our request logging middleware.
    logging.getLogger("uvicorn.access").disabled = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
