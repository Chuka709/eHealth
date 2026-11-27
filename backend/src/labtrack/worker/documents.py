"""After an upload: the virus scan, then the document is ready for reading (Phase 3.3).

Run on the default worker (it parses untrusted files and holds no maintenance rights) as the
uploader (labtrack_app, app.user_id = the uploader): RLS applies as for the user. The task gets
two ids and nothing else. Status moves only from "uploaded":
- clean -> "queued" (Phase 4 reads it), infected -> "rejected" + error_code "infected";
- no scanner (clamd down) -> retried; after the last try -> "failed" + "scan_unavailable".
In dev/test without clamd the scan is skipped (production refuses to run without it).
"""

import asyncio
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from structlog import get_logger

from labtrack.core.envelope import EnvelopeError
from labtrack.db.sql import bound_text
from labtrack.documents.scan import ScanUnavailableError, scan, scanner_configured
from labtrack.documents.service import _aad
from labtrack.keys import decrypt_bytes, get_key_provider
from labtrack.openbao import KeyServiceError
from labtrack.storage import ObjectStore, StorageError, get_store

log = get_logger(__name__)

_SET_USER = bound_text("select set_config('app.user_id', :uid, true)")
_FIND = bound_text("select storage_key, status::text as status from documents where id = :d")
_SET = bound_text(
    "update documents set status = cast(:s as doc_status), error_code = :e"
    " where id = :d and status = 'uploaded'"
)


@dataclass(frozen=True)
class Outcome:
    result: str  # queued | rejected | failed | missing | done | retry


async def process(  # noqa: PLR0911 - one exit per outcome
    engine: AsyncEngine, store: ObjectStore, document_id: UUID, user_id: UUID, *, last_try: bool
) -> Outcome:
    async with engine.connect() as conn, conn.begin():
        await conn.execute(_SET_USER, {"uid": str(user_id)})
        row = (await conn.execute(_FIND, {"d": document_id})).first()
    if row is None:
        return Outcome("missing")  # not committed yet (retried), deleted, or access ended
    if row.status != "uploaded":
        return Outcome("done")
    try:
        if not scanner_configured():
            # dev/test only (config refuses to start elsewhere without a scanner); marked
            log.warning("document_scan_skipped", document_id=str(document_id))
            return await _set(engine, user_id, document_id, "queued", "scan_skipped")
        else:
            sealed = await store.get(row.storage_key)
            data = await decrypt_bytes(get_key_provider(), sealed, _aad(document_id))
            verdict = await asyncio.to_thread(scan, data)
    except (ScanUnavailableError, StorageError, KeyServiceError):
        if not last_try:
            return Outcome("retry")
        return await _set(engine, user_id, document_id, "failed", "scan_unavailable")
    except EnvelopeError:
        return await _set(engine, user_id, document_id, "failed", "unreadable")
    if verdict == "infected":
        log.warning("document_rejected", document_id=str(document_id))
        return await _set(engine, user_id, document_id, "rejected", "infected")
    return await _set(engine, user_id, document_id, "queued", None)


_RESULT = {"queued": "queued", "rejected": "rejected", "failed": "failed"}


async def _set(
    engine: AsyncEngine, user_id: UUID, document_id: UUID, status: str, code: str | None
) -> Outcome:
    async with engine.connect() as conn, conn.begin():
        await conn.execute(_SET_USER, {"uid": str(user_id)})
        changed = await conn.execute(_SET, {"s": status, "e": code, "d": document_id})
    if changed.rowcount == 0:
        # a reader's task (RLS lets them see it, not change it), or another run won
        log.warning("document_status_unchanged", document_id=str(document_id))
        return Outcome("denied")
    return Outcome(_RESULT[status])


def run_sync(app_url: str, document_id: str, user_id: str, *, last_try: bool) -> str:
    async def main() -> str:
        engine = create_async_engine(app_url, hide_parameters=True, pool_reset_on_return="rollback")
        try:
            outcome = await process(
                engine, get_store(), UUID(document_id), UUID(user_id), last_try=last_try
            )
            return outcome.result
        finally:
            await engine.dispose()

    return asyncio.run(main())
