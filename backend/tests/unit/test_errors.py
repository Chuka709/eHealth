"""Framework errors outside the mapped statuses keep the `{code, message_key}` shape."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.exceptions import HTTPException

from labtrack.api.errors import install_error_handlers


@pytest.mark.parametrize(("status", "code"), [(413, "validation"), (415, "validation"),
                                              (503, "internal")])  # fmt: skip
async def test_unmapped_framework_status(status: int, code: str) -> None:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/x")
    async def _x() -> None:
        raise HTTPException(status_code=status)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/x")
    assert r.status_code == status
    assert r.json() == {"code": code, "message_key": f"error.{code}"}
