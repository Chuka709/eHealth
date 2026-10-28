"""API tests: the FastAPI app over ASGI against the compose test database."""

import os
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from labtrack.core.security import hash_password
from labtrack.db.sql import bound_text
from labtrack.main import create_app

PASSWORD = "Хөвсгөл нуур зун 2026 гэрэлтэй"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if "TEST_DATABASE_URL" in os.environ:
        return
    skip = pytest.mark.skip(reason="needs the compose test database (just test-api)")
    for item in items:
        if "tests/api" in str(item.fspath).replace("\\", "/"):
            item.add_marker(skip)


@pytest.fixture(scope="session")
async def owner_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(os.environ["MIGRATION_DATABASE_URL"])
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session")
async def admin_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(os.environ["TEST_ADMIN_DATABASE_URL"])
    yield engine
    await engine.dispose()


ClientFactory = Callable[..., AbstractAsyncContextManager[AsyncClient]]


@pytest.fixture
def client_from() -> ClientFactory:
    """`async with client_from("10.0.0.7") as c:` - a client seen from a given IP."""

    def make(ip: str = "203.0.113.10") -> AbstractAsyncContextManager[AsyncClient]:
        transport = ASGITransport(app=create_app(), client=(ip, 40000))
        return AsyncClient(transport=transport, base_url="http://test")

    return make


async def make_active_user(
    owner_engine: AsyncEngine, password: str = PASSWORD, role: str = "user"
) -> tuple[UUID, str]:
    """Arrange an active account with a password (fixture shortcut, as the schema owner)."""
    username = f"u{uuid4().hex[:12]}"
    async with owner_engine.connect() as conn, conn.begin():
        uid: UUID = (
            await conn.execute(
                bound_text(
                    "insert into users (username, display_name, role, account_status,"
                    " password_hash) values (:u, 'Тест', cast(:r as user_role), 'active', :h)"
                    " returning id"
                ),
                {"u": username, "r": role, "h": hash_password(password)},
            )
        ).scalar_one()
    return uid, username


def login_body(
    username: str, password: str = PASSWORD, device_token: str | None = None
) -> dict[str, object]:
    body: dict[str, object] = {"username": username, "password": password, "platform": "android"}
    if device_token:
        body["device_token"] = device_token
    return body
