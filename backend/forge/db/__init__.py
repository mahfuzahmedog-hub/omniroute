"""Database engine, session factory, and portable column types.

The control plane stores core transactional state relationally (spec ``23_DATABASE``).
To keep the models portable between the production database (PostgreSQL) and the
zero-config test/local database (SQLite), we define a :class:`GUID` type that maps to
native ``uuid`` on PostgreSQL and ``CHAR(36)`` elsewhere.
"""

from __future__ import annotations

import uuid

from sqlalchemy import CHAR, create_engine, event
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.types import TypeDecorator

from forge.config import get_settings


class GUID(TypeDecorator):
    """Platform-independent UUID type.

    Uses PostgreSQL's native ``UUID`` type when available, otherwise stores the
    value as a 36-character canonical string. Values round-trip as :class:`uuid.UUID`.
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, uuid.UUID):
            value = uuid.UUID(str(value))
        if dialect.name == "postgresql":
            return value
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


def _make_engine(database_url: str) -> Engine:
    connect_args: dict[str, object] = {}
    if database_url.startswith("sqlite"):
        # Allow the connection to be shared across threads (TestClient/uvicorn workers).
        connect_args["check_same_thread"] = False
    engine = create_engine(
        database_url,
        connect_args=connect_args,
        pool_pre_ping=True,
        future=True,
    )
    if database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _enable_sqlite_fks(dbapi_connection, _record):  # pragma: no cover - trivial
            # SQLite does not enforce foreign keys unless explicitly enabled.
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


engine = _make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
