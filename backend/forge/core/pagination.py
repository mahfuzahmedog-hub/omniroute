"""Cursor-free offset pagination helpers.

The API spec requires paginating large result sets with a stable shape. Phase 1 uses
simple, predictable ``limit``/``offset`` pagination with a bounded page size; a later
phase can add keyset pagination for very large tables without changing the envelope.
"""

from __future__ import annotations

from typing import Annotated, Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel

T = TypeVar("T")

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


class PageParams(BaseModel):
    """Validated pagination query parameters."""

    limit: int = DEFAULT_LIMIT
    offset: int = 0


def page_params(
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PageParams:
    """FastAPI dependency yielding bounded pagination parameters."""
    return PageParams(limit=limit, offset=offset)


class Page(BaseModel, Generic[T]):
    """A single page of results plus enough metadata to fetch the next."""

    items: list[T]
    total: int
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.items) < self.total
