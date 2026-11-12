"""Daily maintenance as `labtrack_maint` (docs/03 roles; docs/04 §1 deletion; Phase 1.8).

- Erase accounts deleted more than 30 days ago (maint_purge_deleted_users: owned profiles and
  their health data, the account, the user's key - crypto-shredding).
- Drop login/lockout records older than 90 days (auth_attempts retention).
- Drop push receipts older than 7 days (Phase 2.8b).

No task arguments; logs carry counts only.
"""

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import structlog
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from labtrack.db.sql import bound_text

if TYPE_CHECKING:
    from labtrack.storage import ObjectStore

log = structlog.get_logger(__name__)

PURGE_BATCH: Final = 50  # short transactions: each batch cascades whole profiles
AUTH_ATTEMPT_RETENTION_DAYS: Final = 90
PUSH_RECEIPT_RETENTION_DAYS: Final = 7


@dataclass(frozen=True)
class MaintenanceResult:
    purged_accounts: int
    auth_attempts_removed: int
    push_receipts_removed: int = 0


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


async def _receipt_retention(engine: AsyncEngine) -> int:
    # push receipts are only needed until Expo has answered (a day); a week leaves room to look
    async with engine.connect() as conn, conn.begin():
        removed = (
            await conn.execute(
                bound_text(
                    "delete from push_receipts where created_at < now() - make_interval(days => :d)"
                ),
                {"d": PUSH_RECEIPT_RETENTION_DAYS},
            )
        ).rowcount
    return int(removed or 0)


async def run_daily(maint_url: str) -> MaintenanceResult:
    """Both jobs run even if the other fails; a failure is logged (IDs/counts only) and raised
    so the task shows as failed."""
    engine = create_async_engine(maint_url, hide_parameters=True)
    failures: list[BaseException] = []
    purged = removed = receipts = 0
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
        try:
            receipts = await _receipt_retention(engine)
        except Exception as exc:
            log.error("maintenance_receipts_failed", error=type(exc).__name__)  # noqa: TRY400
            failures.append(exc)
    finally:
        await engine.dispose()
    result = MaintenanceResult(purged, removed, receipts)
    log.info(
        "maintenance_done",
        purged_accounts=result.purged_accounts,
        auth_attempts_removed=result.auth_attempts_removed,
        push_receipts_removed=result.push_receipts_removed,
    )
    if failures:
        raise failures[0]
    return result


def run_daily_sync(maint_url: str) -> MaintenanceResult:
    return asyncio.run(run_daily(maint_url))


# --- objects of deleted documents (Phase 3.3) ------------------------------------------------

DELETION_BATCH: Final = 500


async def delete_queued(engine: AsyncEngine, store: "ObjectStore") -> dict[str, int]:
    """Objects whose rows are gone (document_deletions, filled by a trigger in the deleting
    transaction): deleted from storage, then their keys. A key is kept when the store fails, so
    the next run tries again. Keys are ids only."""
    from labtrack.storage import StorageError  # noqa: PLC0415

    async with engine.connect() as conn:
        keys = list(
            (
                await conn.execute(
                    bound_text(
                        "select storage_key from document_deletions order by created_at limit :n"
                    ),
                    {"n": DELETION_BATCH},
                )
            ).scalars()
        )
    done: list[str] = []
    failed = 0
    for key in keys:
        try:
            await store.delete(key)
        except StorageError:
            failed += 1
            continue
        done.append(key)
    if done:
        async with engine.connect() as conn, conn.begin():
            await conn.execute(
                bound_text("delete from document_deletions where storage_key = any(:k)"),
                {"k": done},
            )
    log.info("document_objects_deleted", deleted=len(done), failed=failed)
    return {"deleted": len(done), "failed": failed}


def delete_queued_objects(maint_url: str) -> dict[str, int]:
    from labtrack.storage import get_store  # noqa: PLC0415

    async def main() -> dict[str, int]:
        engine = create_async_engine(maint_url, hide_parameters=True)
        try:
            return await delete_queued(engine, get_store())
        finally:
            await engine.dispose()

    return asyncio.run(main())


ORPHAN_AGE: Final = 24 * 3600  # seconds: well past any upload still being committed


async def delete_orphans(engine: AsyncEngine, store: "ObjectStore") -> dict[str, int]:
    """Objects older than a day that belong to no document (an upload whose transaction failed
    after the object was stored). The database answers only which keys are still live
    (maint_live_document_keys, 0030); keys are ids only."""
    from datetime import UTC, datetime, timedelta  # noqa: PLC0415

    from labtrack.storage import StorageError  # noqa: PLC0415

    old = await store.keys_before(datetime.now(UTC) - timedelta(seconds=ORPHAN_AGE))
    removed = failed = 0
    for start in range(0, len(old), DELETION_BATCH):
        batch = old[start : start + DELETION_BATCH]
        async with engine.connect() as conn:
            live = set(
                (
                    await conn.execute(
                        bound_text("select * from maint_live_document_keys(:k)"), {"k": batch}
                    )
                ).scalars()
            )
        for key in batch:
            if key in live:
                continue
            try:
                await store.delete(key)
                removed += 1
            except StorageError:
                failed += 1
    log.info("document_orphans_deleted", deleted=removed, failed=failed)
    return {"deleted": removed, "failed": failed}


def delete_orphan_objects(maint_url: str) -> dict[str, int]:
    from labtrack.storage import get_store  # noqa: PLC0415

    async def main() -> dict[str, int]:
        engine = create_async_engine(maint_url, hide_parameters=True)
        try:
            return await delete_orphans(engine, get_store())
        finally:
            await engine.dispose()

    return asyncio.run(main())


# --- documents stuck in reading (Phase 4.4, security review M1) ------------------------------


async def sweep_extractions(engine: AsyncEngine) -> list[tuple[str, str]]:
    """Documents left "processing" fail; ones still "queued" are handed back to be read.

    maint_sweep_extractions (0032) does both and returns (document, uploader) ids only.
    """
    async with engine.connect() as conn, conn.begin():
        rows = (await conn.execute(bound_text("select * from maint_sweep_extractions()"))).all()
    return [(str(r.document_id), str(r.user_id)) for r in rows]


def sweep_extractions_sync(maint_url: str) -> list[tuple[str, str]]:
    async def main() -> list[tuple[str, str]]:
        engine = create_async_engine(maint_url, hide_parameters=True)
        try:
            return await sweep_extractions(engine)
        finally:
            await engine.dispose()

    return asyncio.run(main())
