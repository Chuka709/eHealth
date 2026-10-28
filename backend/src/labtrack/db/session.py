"""Database sessions with the RLS user context (docs/03_DATA_MODEL.md, RLS).

Every transaction that touches PHI runs as `labtrack_app` and starts with
`set_config('app.user_id', :uid, true)`. `is_local = true` scopes the setting to the transaction,
so a pooled connection never carries another user's identity into the next request.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from functools import lru_cache
from uuid import UUID

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from labtrack.config import get_settings
from labtrack.db.sql import bound_text

_SET_USER = bound_text("select set_config('app.user_id', :uid, true)")


@lru_cache
def get_engine() -> AsyncEngine:
    return create_async_engine(
        str(get_settings().database_url),
        pool_pre_ping=True,
        pool_reset_on_return="rollback",
    )


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


@asynccontextmanager
async def user_transaction(user_id: UUID) -> AsyncGenerator[AsyncSession]:
    """One transaction acting as `user_id`; commits on success, rolls back on error."""
    async with get_sessionmaker()() as session, session.begin():
        await session.execute(_SET_USER, {"uid": str(user_id)})
        yield session


@asynccontextmanager
async def anonymous_transaction() -> AsyncGenerator[AsyncSession]:
    """A transaction with no user: RLS-protected tables return no rows."""
    async with get_sessionmaker()() as session, session.begin():
        yield session
