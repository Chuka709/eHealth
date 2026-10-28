from collections.abc import Iterator

import pytest
from httpx import ASGITransport, AsyncClient

from labtrack.api import health
from labtrack.config import get_settings
from labtrack.db.session import get_engine, get_sessionmaker
from labtrack.main import create_app


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
    assert r.json() == {"status": "degraded", "database": False, "queue": False}


def test_openapi_has_versioned_paths() -> None:
    paths = create_app().openapi()["paths"]
    assert "/api/v1/healthz" in paths
    assert "/api/v1/readyz" in paths
