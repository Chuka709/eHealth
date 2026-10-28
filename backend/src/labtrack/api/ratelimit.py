"""Per-address rate limits for unauthenticated endpoints (docs/04 §1: "IP тус бүр минутад 20").

Checked before any argon2 work, so random usernames (which never trip the per-account lockout)
cannot be used to exhaust the API. Fixed one-minute windows in Valkey. If Valkey is down the
limit fails open - the per-account lockout in the database still applies - rather than
locking every user out.
"""

import time
from collections.abc import Awaitable, Callable
from datetime import timedelta
from functools import lru_cache

import structlog
from fastapi import Request
from redis.asyncio import Redis
from redis.exceptions import RedisError

from labtrack.api.errors import AppError
from labtrack.auth.service import client_network
from labtrack.config import get_settings

log = structlog.get_logger(__name__)
WINDOW_SECONDS = 60


@lru_cache
def _redis() -> Redis:
    client: Redis = Redis.from_url(str(get_settings().redis_url), socket_connect_timeout=1)
    return client


def per_ip(name: str, limit: Callable[[], int]) -> Callable[[Request], Awaitable[None]]:
    async def dependency(request: Request) -> None:
        net = client_network(request.client.host if request.client else None) or "unknown"
        window = int(time.time()) // WINDOW_SECONDS
        key = f"rl:{name}:{net}:{window}"
        try:
            pipe = _redis().pipeline()
            pipe.incr(key)
            pipe.expire(key, WINDOW_SECONDS * 2)
            count, _ = await pipe.execute()
        except RedisError:
            log.warning("rate_limit_unavailable", limiter=name)
            return
        if int(count) > limit():
            retry = WINDOW_SECONDS - int(time.time()) % WINDOW_SECONDS
            raise AppError(429, "auth.rate_limited", retry_after=timedelta(seconds=max(1, retry)))

    return dependency
