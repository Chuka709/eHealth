"""The per-address limiter itself (the API tests raise the limits so they can log in freely)."""

from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from labtrack.api.errors import install_error_handlers
from labtrack.api.ratelimit import per_ip

pytestmark = pytest.mark.db  # needs Valkey from the compose test service


def _app(limit: int) -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)
    name = f"t{uuid4().hex[:8]}"

    @app.post("/x", dependencies=[Depends(per_ip(name, lambda: limit))])
    async def x() -> dict[str, bool]:
        return {"ok": True}

    return app


async def test_requests_over_the_limit_get_429_with_retry_after() -> None:
    app = _app(3)
    async with AsyncClient(
        transport=ASGITransport(app=app, client=("203.0.113.99", 1)), base_url="http://t"
    ) as c:
        codes = [(await c.post("/x")).status_code for _ in range(5)]
        last = await c.post("/x")
    assert codes == [200, 200, 200, 429, 429]
    assert last.json()["code"] == "auth.rate_limited"
    assert 1 <= int(last.headers["Retry-After"]) <= 60


async def test_limits_are_per_address() -> None:
    app = _app(1)
    for ip in ("203.0.113.1", "203.0.113.2"):
        async with AsyncClient(
            transport=ASGITransport(app=app, client=(ip, 1)), base_url="http://t"
        ) as c:
            assert (await c.post("/x")).status_code == 200


async def test_ipv6_clients_share_a_limit_per_64_prefix() -> None:
    app = _app(1)
    for ip in ("2001:db8:1:2::1", "2001:db8:1:2:ffff::9"):
        async with AsyncClient(
            transport=ASGITransport(app=app, client=(ip, 1)), base_url="http://t"
        ) as c:
            status = (await c.post("/x")).status_code
    assert status == 429
