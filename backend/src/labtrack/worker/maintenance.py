"""Daily maintenance as `labtrack_maint` (docs/03 roles; docs/04 §1 deletion; Phase 1.8).

- Erase accounts deleted more than 30 days ago (maint_purge_deleted_users: owned profiles and
  their health data, the account, the user's key - crypto-shredding).
- Drop login/lockout records older than 90 days (auth_attempts retention).

No task arguments; logs carry counts only.
"""

import asyncio
from dataclasses import dataclass
from typing import Final

import structlog
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from labtrack.db.sql import bound_text

log = structlog.get_logger(__name__)

PURGE_BATCH: Final = 50  # short transactions: each batch cascades whole profiles
AUTH_ATTEMPT_RETENTION_DAYS: Final = 90


@dataclass(frozen=True)
class MaintenanceResult:
    purged_accounts: int
    auth_attempts_removed: int


async def _purge(engine: AsyncEngine) -> int:
    purged = 0
    while True:  # one transaction per batch: a failure keeps earlier batches done
        async with engine.connect() as conn, conn.begin():
            ids = (
                (
                    await conn.execute(
                        bound_text("select * from maint_purge_deleted_users(:n)"),
                        {"n": PURGE_BATCH},
                    )
                )
                .scalars()
                .all()
            )
        # Production (OpenBao): the purged users' named keys are destroyed here as well; the
        # dev/test key rows went with the accounts in the same transaction. An account that
        # could not be purged is skipped and reported (security.purge_failed audit).
        purged += len(ids)
        if len(ids) < PURGE_BATCH:
            return purged


async def _retention(engine: AsyncEngine) -> int:
    async with engine.connect() as conn, conn.begin():
        removed = (
            await conn.execute(
                bound_text(
                    "delete from auth_attempts where at < now() - make_interval(days => :d)"
                ),
                {"d": AUTH_ATTEMPT_RETENTION_DAYS},
            )
        ).rowcount
    return int(removed or 0)


async def run_daily(maint_url: str) -> MaintenanceResult:
    """Both jobs run even if the other fails; a failure is logged (IDs/counts only) and raised
    so the task shows as failed."""
    engine = create_async_engine(maint_url, hide_parameters=True)
    failures: list[BaseException] = []
    purged = removed = 0
    try:
        try:
            purged = await _purge(engine)
        except Exception as exc:  # reported below; retention still runs
            # no traceback: driver text can carry row values
            log.error("maintenance_purge_failed", error=type(exc).__name__)  # noqa: TRY400
            failures.append(exc)
        try:
            removed = await _retention(engine)
        except Exception as exc:
            log.error("maintenance_retention_failed", error=type(exc).__name__)  # noqa: TRY400
            failures.append(exc)
    finally:
        await engine.dispose()
    result = MaintenanceResult(purged, removed)
    log.info(
        "maintenance_done",
        purged_accounts=result.purged_accounts,
        auth_attempts_removed=result.auth_attempts_removed,
    )
    if failures:
        raise failures[0]
    return result


def run_daily_sync(maint_url: str) -> MaintenanceResult:
    return asyncio.run(run_daily(maint_url))
