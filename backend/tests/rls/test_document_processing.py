"""The upload's scan task and the sweep of deleted objects (Phase 3.3)."""

from hashlib import sha256
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.config import get_settings
from labtrack.db.sql import bound_text
from labtrack.documents import scan as scan_module
from labtrack.documents.scan import ScanUnavailableError
from labtrack.documents.service import _aad, storage_key
from labtrack.keys import encrypt_bytes, get_key_provider
from labtrack.storage import MemoryObjectStore
from labtrack.worker import documents as worker
from labtrack.worker.maintenance import delete_queued

from .conftest import as_user, make_patient, make_user, scalar

pytestmark = pytest.mark.db


async def _uploaded(app_engine: AsyncEngine, store: MemoryObjectStore, user: UUID) -> UUID:
    patient = await make_patient(app_engine, user)
    doc = uuid4()
    key = storage_key(patient, doc)
    await store.put(key, await encrypt_bytes(get_key_provider(), b"%PDF-1.7 test", _aad(doc)))
    async with as_user(app_engine, user) as conn:
        await conn.execute(
            bound_text(
                "insert into documents (id, patient_id, client_id, storage_key, mime_type,"
                " size_bytes, sha256) values (:i, :p, :c, :k, 'application/pdf', 13, :h)"
            ),
            {"i": doc, "p": patient, "c": uuid4(), "k": key, "h": sha256(doc.bytes).hexdigest()},
        )
    return doc


async def _status(app_engine: AsyncEngine, user: UUID, doc: UUID) -> tuple[str, str | None]:
    async with as_user(app_engine, user) as conn:
        row = (
            await conn.execute(
                bound_text(
                    "select status::text as s, error_code as e from documents where id = :d"
                ),
                {"d": doc},
            )
        ).one()
    return row.s, row.e


async def test_without_a_scanner_in_test_the_document_is_queued(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    store, user = MemoryObjectStore(), await make_user(owner_engine)
    doc = await _uploaded(app_engine, store, user)
    assert (await worker.process(app_engine, store, doc, user, last_try=False)).result == "queued"
    # marked: in production the config refuses to start without a scanner
    assert await _status(app_engine, user, doc) == ("queued", "scan_skipped")
    # a second run changes nothing: the status moves only from "uploaded"
    assert (await worker.process(app_engine, store, doc, user, last_try=False)).result == "done"


async def test_an_infected_file_is_rejected(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(worker, "scanner_configured", lambda: True)
    monkeypatch.setattr(worker, "scan", lambda data: "infected")
    store, user = MemoryObjectStore(), await make_user(owner_engine)
    doc = await _uploaded(app_engine, store, user)
    assert (await worker.process(app_engine, store, doc, user, last_try=False)).result == "rejected"
    assert await _status(app_engine, user, doc) == ("rejected", "infected")


async def test_a_scanner_that_stays_down_fails_the_document_after_retries(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    def down(data: bytes) -> str:
        raise ScanUnavailableError

    monkeypatch.setattr(worker, "scanner_configured", lambda: True)
    monkeypatch.setattr(worker, "scan", down)
    store, user = MemoryObjectStore(), await make_user(owner_engine)
    doc = await _uploaded(app_engine, store, user)
    assert (await worker.process(app_engine, store, doc, user, last_try=False)).result == "retry"
    assert await _status(app_engine, user, doc) == ("uploaded", None)
    assert (await worker.process(app_engine, store, doc, user, last_try=True)).result == "failed"
    assert await _status(app_engine, user, doc) == ("failed", "scan_unavailable")


def test_production_without_a_scanner_accepts_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings().model_copy(update={"environment": "production", "clamd_host": None})
    monkeypatch.setattr(scan_module, "get_settings", lambda: settings)
    with pytest.raises(ScanUnavailableError):
        scan_module.scanner_configured()


async def test_a_task_for_another_user_finds_nothing(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    store = MemoryObjectStore()
    owner, stranger = await make_user(owner_engine), await make_user(owner_engine)
    doc = await _uploaded(app_engine, store, owner)
    result = await worker.process(app_engine, store, doc, stranger, last_try=True)
    assert result.result == "missing"
    assert await _status(app_engine, owner, doc) == ("uploaded", None)


async def test_deleted_documents_objects_are_removed_by_the_sweep(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, maint_engine: AsyncEngine
) -> None:
    store, user = MemoryObjectStore(), await make_user(owner_engine)
    doc = await _uploaded(app_engine, store, user)
    async with as_user(app_engine, user) as conn:
        key = await scalar(
            conn, bound_text("select storage_key from documents where id = :d"), {"d": doc}
        )
        await conn.execute(bound_text("delete from documents where id = :d"), {"d": doc})
    assert key in store.objects
    result = await delete_queued(maint_engine, store)
    assert result["deleted"] >= 1
    assert key not in store.objects
    async with owner_engine.connect() as conn:
        left = await scalar(
            conn,
            bound_text("select count(*) from document_deletions where storage_key = :k"),
            {"k": key},
        )
    assert left == 0


async def test_a_readers_task_changes_nothing(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    from .conftest import grant  # noqa: PLC0415

    store = MemoryObjectStore()
    owner, reader = await make_user(owner_engine), await make_user(owner_engine)
    doc = await _uploaded(app_engine, store, owner)
    async with as_user(app_engine, owner) as conn:
        patient = await scalar(
            conn, bound_text("select patient_id from documents where id = :d"), {"d": doc}
        )
    await grant(app_engine, owner, patient, reader, "viewer")
    assert (await worker.process(app_engine, store, doc, reader, last_try=False)).result == "denied"
    assert await _status(app_engine, owner, doc) == ("uploaded", None)


async def test_objects_left_by_a_failed_upload_are_swept(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, maint_engine: AsyncEngine
) -> None:
    from datetime import UTC, datetime, timedelta  # noqa: PLC0415

    from labtrack.worker.maintenance import delete_orphans  # noqa: PLC0415

    store, user = MemoryObjectStore(), await make_user(owner_engine)
    doc = await _uploaded(app_engine, store, user)
    async with as_user(app_engine, user) as conn:
        live = await scalar(
            conn, bound_text("select storage_key from documents where id = :d"), {"d": doc}
        )
    orphan = f"{uuid4()}/{uuid4()}/original"
    await store.put(orphan, b"sealed")
    day_ago = datetime.now(UTC) - timedelta(days=2)
    store.stored_at = dict.fromkeys(store.stored_at, day_ago)
    result = await delete_orphans(maint_engine, store)
    assert result["deleted"] == 1
    assert orphan not in store.objects
    assert live in store.objects
