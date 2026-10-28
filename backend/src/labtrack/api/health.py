from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from redis.asyncio import Redis

from labtrack.config import get_settings
from labtrack.db.session import anonymous_transaction
from labtrack.db.sql import bound_text

router = APIRouter(tags=["health"])


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
    try:
        async with anonymous_transaction() as session:
            await session.execute(bound_text("select 1"))
        database = True
    except Exception:  # noqa: S110 - readiness reports a boolean only
        pass
    try:
        redis = Redis.from_url(str(get_settings().redis_url), socket_connect_timeout=2)
        async with redis:
            queue = bool(await redis.ping())
    except Exception:  # noqa: S110
        pass
    ok = database and queue
    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return Readiness(status="ok" if ok else "degraded", database=database, queue=queue)
