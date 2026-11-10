"""The push tasks' wrapper: the on/off switch, one run at a time, and the database engine.

No task arguments; the result and logs are counts only.
"""

import asyncio
import secrets
from collections.abc import Callable
from typing import Any, Literal, Protocol

import structlog
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import create_async_engine

from labtrack.config import get_settings
from labtrack.worker.push import ExpoGateway, PushGateway, check_receipts, send_pending

log = structlog.get_logger(__name__)

Job = Literal["send", "receipts"]
# compare-and-delete: a run never releases a lock that expired and was taken by the next one
_RELEASE = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) end"


class LockStore(Protocol):
    """The two Valkey commands the run lock uses (redis.Redis in production)."""

    def set(self, name: str, value: str, *, nx: bool, ex: int) -> Any: ...

    # Valkey EVAL of the constant Lua script above - not Python's eval
    def eval(self, script: str, numkeys: int, *keys_and_args: str) -> Any: ...


def _gateway() -> PushGateway:
    token = get_settings().expo_access_token
    return ExpoGateway(token.get_secret_value() if token else None)


async def _run(job: Job, maint_url: str, gateway: PushGateway) -> dict[str, int]:
    engine = create_async_engine(maint_url, hide_parameters=True)
    try:
        if job == "send":
            sent = await send_pending(engine, gateway)
            return {
                "sent": sent.sent,
                "failed_tickets": sent.failed_tickets,
                "failed_requests": sent.failed_requests,
                "marked": sent.marked,
            }
        checked = await check_receipts(engine, gateway)
        return {
            "ok": checked.ok,
            "errors": checked.errors,
            "forgotten_tokens": checked.forgotten_tokens,
            "expired": checked.expired,
        }
    finally:
        await engine.dispose()


def run_push(
    job: Job,
    maint_url: str,
    lock_seconds: int,
    *,
    gateway: Callable[[], PushGateway] = _gateway,
    redis: Callable[[], LockStore] | None = None,
) -> dict[str, int]:
    if not get_settings().push_enabled:
        # decision (c): no credentials yet - nothing is sent and nothing is marked as sent
        return {"disabled": 1}
    if (
        get_settings().environment not in {"dev", "test"}
        and get_settings().expo_access_token is None
    ):
        # without Expo's access token (and Enhanced Push Security on) anyone who learns a token
        # could push to that phone as LabTrack: refuse to run rather than send without it
        log.error("push_access_token_missing")
        return {"misconfigured": 1}
    client: LockStore = redis() if redis else Redis.from_url(str(get_settings().redis_url))
    key, owner = f"lock:push:{job}", secrets.token_hex(16)
    try:
        if not client.set(key, owner, nx=True, ex=lock_seconds):
            return {"busy": 1}  # the previous run is still going
    except RedisError:
        # without the lock two runs could send the same notices twice: skip this one
        log.warning("push_lock_unavailable", job=job)
        return {"busy": 1}
    try:
        return asyncio.run(_run(job, maint_url, gateway()))
    finally:
        try:
            client.eval(_RELEASE, 1, key, owner)
        except RedisError:
            log.warning("push_lock_release_failed", job=job)  # it expires on its own
