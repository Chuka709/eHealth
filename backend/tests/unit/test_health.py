from collections.abc import Iterator

import pytest
from httpx import ASGITransport, AsyncClient

from labtrack.api import health
from labtrack.config import get_settings
from labtrack.db.session import get_engine, get_sessionmaker
from labtrack.main import create_app
from labtrack.openbao import KeyServiceError


def _clear_caches() -> None:
    get_settings.cache_clear()
    health._redis.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()


@pytest.fixture
def unreachable_deps(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://unit@127.0.0.1:1/unit")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    _clear_caches()
    yield
    _clear_caches()


async def test_healthz_is_ok_without_dependencies(unreachable_deps: None) -> None:
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t") as c:
        r = await c.get("/api/v1/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_readyz_reports_degraded_without_leaking_errors(unreachable_deps: None) -> None:
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t") as c:
        r = await c.get("/api/v1/readyz")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "degraded"
    assert body["database"] is False
    assert body["queue"] is False
    assert set(body) == {"status", "database", "queue", "keys"}  # booleans only, no reasons


async def test_readyz_is_not_ready_without_the_key_service(
    unreachable_deps: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Down:
        current_kek_id = "bao:labtrack-kek"

        async def wrap(self, dek: bytes, aad: bytes) -> bytes:
            raise KeyServiceError("openbao unreachable")

        async def unwrap(self, kek_id: str, wrapped: bytes, aad: bytes) -> bytes:
            raise KeyServiceError("openbao unreachable")

    monkeypatch.setattr(health, "get_key_provider", Down)
    monkeypatch.setattr(health, "_keys_ok_until", 0.0)
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://t") as c:
        r = await c.get("/api/v1/readyz")
    assert r.status_code == 503
    assert r.json()["keys"] is False
    assert "openbao" not in r.text


def test_openapi_has_versioned_paths() -> None:
    paths = create_app().openapi()["paths"]
    assert "/api/v1/healthz" in paths
    assert "/api/v1/readyz" in paths


def test_openapi_schema_names_are_unique() -> None:
    """Two response models of one name get module-prefixed names (`labtrack__api__...`) in the
    schema, which renames the client's existing types and breaks the apps (6.4)."""
    schemas = create_app().openapi()["components"]["schemas"]
    assert [name for name in schemas if name.startswith("labtrack__")] == []
