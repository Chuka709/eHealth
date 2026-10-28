"""Fixtures for RLS tests: one engine per database role, and helpers to act as a user.

Rows are committed (several roles must see them) and isolated by random usernames; the test
database is rebuilt by `alembic downgrade base && upgrade head` before every run.
"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from labtrack.db.sql import bound_text
from tests.admin_support import open_admin_session, set_admin_context

pytestmark = pytest.mark.db

_REQUIRED = (
    "TEST_DATABASE_URL",
    "TEST_ADMIN_DATABASE_URL",
    "TEST_ADMIN_LOGIN_DATABASE_URL",
    "TEST_MAINT_DATABASE_URL",
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if all(k in os.environ for k in _REQUIRED):
        return
    skip = pytest.mark.skip(reason="needs the compose test database (just test-rls)")
    for item in items:
        if "tests/rls" in str(item.fspath).replace("\\", "/"):
            item.add_marker(skip)


@pytest.fixture(scope="session")
async def app_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session")
async def owner_engine() -> AsyncIterator[AsyncEngine]:
    """Schema owner: used only to arrange fixtures, never as the role under test."""
    engine = create_async_engine(os.environ["MIGRATION_DATABASE_URL"])
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session")
async def admin_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(os.environ["TEST_ADMIN_DATABASE_URL"])
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session")
async def admin_login_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(os.environ["TEST_ADMIN_LOGIN_DATABASE_URL"])
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session")
async def maint_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(os.environ["TEST_MAINT_DATABASE_URL"])
    yield engine
    await engine.dispose()


# Admins made by make_user() get a live admin session (0006); as_user() on the labtrack_admin
# engine begins it, so admin_* functions see the acting admin's session.
_ADMIN_SESSIONS: dict[UUID, str] = {}


@asynccontextmanager
async def as_user(engine: AsyncEngine, user_id: UUID | None) -> AsyncIterator[AsyncConnection]:
    """One committed transaction as `user_id` (None = no user context)."""
    async with engine.connect() as conn, conn.begin():
        if user_id in _ADMIN_SESSIONS and engine.url.username == "labtrack_admin":
            await set_admin_context(conn, _ADMIN_SESSIONS[user_id])
        elif user_id is not None:
            await conn.execute(
                bound_text("select set_config('app.user_id', :uid, true)"), {"uid": str(user_id)}
            )
        yield conn


async def scalar(conn: AsyncConnection, sql: Any, params: dict[str, Any] | None = None) -> Any:
    return (await conn.execute(sql, params or {})).scalar_one()


async def make_user(owner_engine: AsyncEngine, role: str = "user") -> UUID:
    """Arrange an active account directly as the schema owner.

    Real accounts are created by admin_create_user + activation_consume (tested separately);
    this shortcut exists only so other tests can start from an active user.
    """
    async with owner_engine.connect() as conn, conn.begin():
        uid: UUID = await scalar(
            conn,
            bound_text(
                "insert into users (username, display_name, role, account_status)"
                " values (:u, 'Test', cast(:r as user_role), 'active') returning id"
            ),
            {"u": f"t{uuid4().hex[:12]}", "r": role},
        )
    if role in {"super_admin", "support"}:
        _ADMIN_SESSIONS[uid] = await open_admin_session(owner_engine, uid)
    return uid


async def make_patient(app_engine: AsyncEngine, owner: UUID, *, minor: bool = False) -> UUID:
    async with as_user(app_engine, owner) as conn:
        pid: UUID = await scalar(
            conn,
            bound_text("select create_patient('Test Patient', :rel, :born, 'unknown'::sex)"),
            {"rel": "child" if minor else "self", "born": date(2015, 1, 1) if minor else None},
        )
    return pid


async def grant(
    app_engine: AsyncEngine,
    owner: UUID,
    patient: UUID,
    grantee: UUID,
    level: str,
    *,
    expires: datetime | None = None,
    revoked: bool = False,
) -> None:
    async with as_user(app_engine, owner) as conn:
        await conn.execute(
            bound_text(
                "insert into patient_access (patient_id, user_id, level, granted_by, expires_at,"
                " revoked_at) values (:p, :g, cast(:lvl as access_level), :o,"
                " :exp, case when :rev then now() end)"
            ),
            {"p": patient, "g": grantee, "lvl": level, "o": owner, "exp": expires, "rev": revoked},
        )
