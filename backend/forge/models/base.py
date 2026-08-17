"""Declarative base and shared model mixins.

Every core entity carries a durable surrogate key, creation/update timestamps, and an
optimistic-concurrency ``version`` counter. The version column is wired into SQLAlchemy's
``version_id_col`` so a stale worker writing back an out-of-date row raises
``StaleDataError`` instead of silently clobbering newer state — directly enforcing the
spec's "version task transitions to prevent stale workers from overwriting newer state".
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

from forge.db import GUID


def utcnow() -> datetime:
    """Timezone-aware UTC now (portable default across SQLite/Postgres)."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Declarative base for all Forge models."""


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class VersionedMixin:
    """Adds an optimistic-concurrency version counter.

    SQLAlchemy increments ``version`` on every UPDATE and adds ``version`` to the
    WHERE clause. A write from a worker holding a stale row therefore matches zero
    rows and raises ``StaleDataError`` instead of silently overwriting newer state.
    """

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    @declared_attr.directive
    def __mapper_args__(cls) -> dict:  # noqa: N805
        return {"version_id_col": cls.__table__.c.version}
