"""Uploaded documents (Phase 3.1-3.2; docs/03 "documents", docs/04 §3, Q49).

An upload is checked (files.check), sealed with the KEK envelope and only then stored; the row
is written in the same transaction, so a storage failure leaves no row. Deleting a row queues
its object for deletion (document_deletions, 0029) - never deleted before the commit.
Retries are idempotent by the app's `client_id`; the same file twice for one profile returns
the document already there. Audited by id only.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from anyio import CapacityLimiter, to_thread
from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from labtrack.api.errors import AppError
from labtrack.core.envelope import EnvelopeError, field_aad
from labtrack.db.sql import bound_text
from labtrack.documents.files import FileRejectedError, check
from labtrack.keys import decrypt_bytes, encrypt_bytes, get_key_provider
from labtrack.records.repository import audit
from labtrack.storage import ObjectStore, StorageError

log = get_logger(__name__)

_SCANNED = frozenset({"queued", "processing", "needs_review", "confirmed"})
MAX_DOCUMENTS = 2000  # per profile; years of monthly results with room to spare


@dataclass(frozen=True)
class Document:
    id: UUID
    mime_type: str
    size_bytes: int
    page_count: int | None
    has_text_layer: bool | None
    status: str
    error_code: str | None
    created_at: datetime


@dataclass(frozen=True)
class Uploaded:
    document: Document
    created: bool  # False: a retry or the same file again - the stored document


_SELECT = (
    "select id, mime_type, size_bytes, page_count, has_text_layer, status::text as status,"
    " error_code, created_at from documents where patient_id = :p"
)
_BY_ID = bound_text(_SELECT + " and id = :i")
_BY_CLIENT = bound_text(_SELECT + " and client_id = :c")
_BY_HASH = bound_text(_SELECT + " and sha256 = :h")
_LIST = bound_text(_SELECT + " order by created_at desc limit :n")


def _aad(document_id: UUID) -> bytes:
    return field_aad("documents", "file", document_id)


def storage_key(patient_id: UUID, document_id: UUID) -> str:
    return f"{patient_id}/{document_id}/original"


async def _one(db: AsyncSession, sql: object, params: dict[str, object]) -> Document | None:
    row = (await db.execute(sql, params)).mappings().first()  # type: ignore[call-overload]
    return Document(**row) if row else None


async def upload(
    db: AsyncSession,
    store: ObjectStore,
    patient_id: UUID,
    client_id: UUID,
    data: bytes,
) -> Uploaded:
    retried = await _one(db, _BY_CLIENT, {"p": patient_id, "c": client_id})
    if retried:
        return Uploaded(retried, created=False)
    try:
        # at most a few files are parsed at once: memory (images) and PDFium (one thread at
        # a time, files.py) - security review 3.2
        checked = await to_thread.run_sync(check, data, limiter=_checks())
    except FileRejectedError as exc:
        raise AppError(_STATUS.get(exc.code, 422), exc.code) from exc
    same = await _one(db, _BY_HASH, {"p": patient_id, "h": checked.sha256})
    if same:
        return Uploaded(same, created=False)
    count = (
        await db.execute(
            bound_text("select count(*) from documents where patient_id = :p"), {"p": patient_id}
        )
    ).scalar_one()
    if count >= MAX_DOCUMENTS:
        raise AppError(409, "document.too_many")
    document_id = uuid4()
    key = storage_key(patient_id, document_id)
    sealed = await encrypt_bytes(get_key_provider(), checked.data, _aad(document_id))
    inserted = await db.execute(
        bound_text(
            "insert into documents (id, patient_id, client_id, storage_key, mime_type,"
            " size_bytes, page_count, sha256, has_text_layer)"
            " values (:i, :p, :c, :k, :m, :s, :n, :h, :t)"
            " on conflict do nothing returning id"
        ),
        {
            "i": document_id,
            "p": patient_id,
            "c": client_id,
            "k": key,
            "m": checked.mime_type,
            "s": len(checked.data),
            "n": checked.page_count,
            "h": checked.sha256,
            "t": checked.has_text_layer,
        },
    )
    if inserted.first() is None:
        # the same upload or file arrived at the same moment: the one stored first
        winner = await _one(db, _BY_CLIENT, {"p": patient_id, "c": client_id}) or await _one(
            db, _BY_HASH, {"p": patient_id, "h": checked.sha256}
        )
        if winner is None:
            raise AppError(409, "document.conflict")
        return Uploaded(winner, created=False)
    await audit(db, "document.upload", "document", document_id, patient_id)
    try:
        await store.put(key, sealed)
    except StorageError as exc:
        # the transaction rolls back: no row without its object. (An object stored and then
        # a failed commit is an orphan: the daily orphan sweep removes it - Phase 3.3.)
        raise AppError(503, "document.storage_unavailable") from exc
    return Uploaded(await get(db, patient_id, document_id), created=True)


async def get(db: AsyncSession, patient_id: UUID, document_id: UUID) -> Document:
    found = await _one(db, _BY_ID, {"p": patient_id, "i": document_id})
    if found is None:
        raise AppError(404, "document.not_found")
    return found


async def list_documents(db: AsyncSession, patient_id: UUID) -> list[Document]:
    rows = (await db.execute(_LIST, {"p": patient_id, "n": MAX_DOCUMENTS})).mappings().all()
    return [Document(**row) for row in rows]


_KEY = bound_text("select storage_key from documents where patient_id = :p and id = :i")


async def read_file(
    db: AsyncSession, store: ObjectStore, patient_id: UUID, document_id: UUID
) -> tuple[bytes, str]:
    document = await get(db, patient_id, document_id)
    # only a file that passed the virus scan is handed out (commit security review 3.3)
    if document.status == "uploaded":
        raise AppError(409, "document.not_ready")
    if document.status not in _SCANNED:
        raise AppError(409, "document.not_available")
    try:
        # the stored key: a moved document keeps its first profile's prefix (0037)
        key = (await db.execute(_KEY, {"p": patient_id, "i": document_id})).scalar_one()
        sealed = await store.get(key)
        data = await decrypt_bytes(get_key_provider(), sealed, _aad(document_id))
    except StorageError as exc:
        raise AppError(503, "document.storage_unavailable") from exc
    except EnvelopeError as exc:
        raise AppError(500, "document.unreadable") from exc
    await audit(db, "document.view", "document", document_id, patient_id)
    return data, document.mime_type


async def delete(db: AsyncSession, patient_id: UUID, document_id: UUID) -> None:
    await get(db, patient_id, document_id)
    deleted = await db.execute(
        bound_text("delete from documents where patient_id = :p and id = :i"),
        {"p": patient_id, "i": document_id},
    )
    if deleted.rowcount == 0:  # type: ignore[attr-defined]
        # readable but not this user's to erase (only the owner or the uploader - 0029)
        raise AppError(403, "document.not_yours")
    await audit(db, "document.delete", "document", document_id, patient_id)
    # the object is not deleted here: the row's trigger queued its key in document_deletions
    # in this transaction, and the maintenance worker deletes it after the commit (a sealed
    # object stays readable with the KEK, so it must go - security review 3.2)


_LIMITER: CapacityLimiter | None = None


def _checks() -> CapacityLimiter:
    global _LIMITER  # noqa: PLW0603 - created inside the running event loop, once
    if _LIMITER is None:
        _LIMITER = CapacityLimiter(2)
    return _LIMITER


_STATUS = {"document.too_large": 413, "document.unsupported_type": 415}


# --- processing (Phase 3.3) -------------------------------------------------------------------

STUCK_AFTER = timedelta(minutes=2)


async def enqueue(document_id: UUID, user_id: UUID) -> None:
    """The scan task, a moment after the upload commits (the task retries while the row is not
    visible yet). Ids only. A broker that is down does not fail the upload: the next status
    request sends it again (enqueue_if_stuck)."""
    from labtrack.api.ratelimit import _redis  # noqa: PLC0415
    from labtrack.worker.celery_app import app  # noqa: PLC0415

    try:
        # one task per document for 5 minutes: polling the status never piles tasks up
        if not await _redis().set(f"doc-scan:{document_id}", "1", nx=True, ex=300):
            return
        app.send_task(
            "labtrack.documents.process", args=[str(document_id), str(user_id)], countdown=2
        )
    except Exception:
        log.warning("document_enqueue_failed", document_id=str(document_id))


async def enqueue_if_stuck(
    db: AsyncSession, patient_id: UUID, document: Document, user_id: UUID
) -> None:
    """Sent again only for someone who may write the profile: the task runs as them."""
    if document.status != "uploaded" or datetime.now(UTC) - document.created_at <= STUCK_AFTER:
        return
    may_write = (
        await db.execute(bound_text("select can_write_patient(:p)"), {"p": patient_id})
    ).scalar_one()
    if may_write:
        await enqueue(document.id, user_id)
