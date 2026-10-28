import contextlib
from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from redis.asyncio import Redis

from labtrack.config import get_settings
from labtrack.db.session import anonymous_transaction
from labtrack.db.sql import bound_text

router = APIRouter(tags=["health"])


@lru_cache
def _redis() -> Redis:
    # One pooled client per process; readiness probes must not open a connection per call.
    client: Redis = Redis.from_url(str(get_settings().redis_url), socket_connect_timeout=2)
    return client


class Health(BaseModel):
    status: Literal["ok"]


class Readiness(BaseModel):
    status: Literal["ok", "degraded"]
    database: bool
    queue: bool


@router.get("/healthz", response_model=Health)
async def healthz() -> Health:
    """Liveness: the process is up. No dependencies checked."""
    return Health(status="ok")


@router.get("/readyz", response_model=Readiness)
async def readyz(response: Response) -> Readiness:
    """Readiness: database and queue reachable. Error details are never returned."""
    database = queue = False
    # Readiness reports booleans only; the failure reason is never returned.
    with contextlib.suppress(Exception):
        async with anonymous_transaction() as session:
            await session.execute(bound_text("select 1"))
        database = True
    with contextlib.suppress(Exception):
        queue = bool(await _redis().ping())
    ok = database and queue
    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return Readiness(status="ok" if ok else "degraded", database=database, queue=queue)
