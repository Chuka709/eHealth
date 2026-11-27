import contextlib
import time
from functools import lru_cache
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from redis.asyncio import Redis

from labtrack.config import get_settings
from labtrack.core.envelope import field_aad
from labtrack.db.session import anonymous_transaction
from labtrack.db.sql import bound_text
from labtrack.keys import decrypt_field, encrypt_field, get_key_provider

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
    keys: bool


@router.get("/healthz", response_model=Health)
async def healthz() -> Health:
    """Liveness: the process is up. No dependencies checked."""
    return Health(status="ok")


@router.get("/readyz", response_model=Readiness)
async def readyz(response: Response) -> Readiness:
    """Readiness: database, queue and the key service. Error details are never returned.

    The keys are checked by sealing and opening a canary (SERVER_INSTALL_PLAN S2): an OpenBao
    that is sealed, unreachable, refusing this role or missing the KEK makes the API unready -
    the container healthcheck, and so Caddy's start and the monitoring, see it."""
    database = queue = False
    # Readiness reports booleans only; the failure reason is never returned.
    with contextlib.suppress(Exception):
        async with anonymous_transaction() as session:
            await session.execute(bound_text("select 1"))
        database = True
    with contextlib.suppress(Exception):
        queue = bool(await _redis().ping())
    keys = await _keys_ready()
    ok = database and queue and keys
    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return Readiness(status="ok" if ok else "degraded", database=database, queue=queue, keys=keys)


# a fixed row id: nothing is stored, the value only travels to OpenBao and back
_CANARY = field_aad("readiness", "canary", UUID(int=0))
# a passed check is kept this long: readiness calls (anyone on the stack's networks can make
# them) must not turn into a stream of OpenBao requests and audit lines (review S2 L1)
_KEYS_OK_FOR_S = 30.0
_keys_ok_until = 0.0


async def _keys_ready() -> bool:
    global _keys_ok_until  # noqa: PLW0603 - one value per process
    if time.monotonic() < _keys_ok_until:
        return True
    try:
        provider = get_key_provider()
        sealed = await encrypt_field(provider, "ok", _CANARY)
        ok = await decrypt_field(provider, sealed, _CANARY) == "ok"
    except Exception:
        ok = False
    _keys_ok_until = time.monotonic() + _KEYS_OK_FOR_S if ok else 0.0
    return ok
