"""Reading a scanned document into draft reports, as the uploader (Phase 4.4)."""

from collections.abc import AsyncIterator
from datetime import timedelta
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.core.text import normalize_name, normalize_unit
from labtrack.db.sql import bound_text
from labtrack.documents.service import _aad, storage_key
from labtrack.extraction.isolated import Reading
from labtrack.extraction.types import PrintedIdentity, ReadDocument, ReadReport, ReadResult
from labtrack.keys import encrypt_bytes, get_key_provider
from labtrack.storage import MemoryObjectStore
from labtrack.worker import extraction as worker

from .conftest import as_user, grant, make_patient, make_user, scalar

pytestmark = pytest.mark.db


@pytest.fixture
async def test_code(owner_engine: AsyncEngine) -> AsyncIterator[str]:
    """A catalog test of its own (the test database has no seeded catalog)."""
    code = f"T_{uuid4().hex[:8].upper()}"
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "insert into test_catalog (code, name_mn, name_en, category, canonical_unit,"
                " physio_min, physio_max) values (:c, 'Тест', 'Test', 'test', 'mmol/L', 0.5, 60)"
            ),
            {"c": code},
        )
        await conn.execute(
            bound_text(
                "insert into test_synonyms (test_code, synonym, synonym_norm) values (:c, :s, :k)"
            ),
            {"c": code, "s": code, "k": normalize_name(f"Глюкоз {code}")},
        )
        await conn.execute(
            bound_text(
                "insert into unit_aliases (alias_norm, unit) values (:a, 'mmol/L')"
                " on conflict do nothing"
            ),
            {"a": normalize_unit("ммоль/л")},
        )
    yield code
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(bound_text("delete from lab_results where test_code = :c"), {"c": code})
        await conn.execute(bound_text("delete from test_catalog where code = :c"), {"c": code})


def _reading(code: str, *, family: str = "Patient", given: str = "Test") -> ReadDocument:
    """As the reader returns it; the conftest profile is "Test Patient"."""
    rows = (
        ReadResult(f"Глюкоз {code}", "5,37", "ммоль/л", "4.11 - 6.38", None, 1, "row one"),
        ReadResult("Альфа амилаза", "73.7", "нэгж/л", "28.0 - 100.0", "H", 1, "row two"),
    )
    return ReadDocument(
        reader="unte.v1",
        reports=(
            ReadReport(
                "Lab",
                "Биохими",
                "цус",
                "2025-08-18",
                "2025-08-18 12:05:52",
                rows,
                "2025-08-18 10:15:21",
            ),
        ),
        identity=PrintedIdentity(family_name=family, given_name=given),
    )


async def _queued(
    app_engine: AsyncEngine, store: MemoryObjectStore, user: UUID, patient: UUID
) -> UUID:
    doc = uuid4()
    key = storage_key(patient, doc)
    await store.put(key, await encrypt_bytes(get_key_provider(), b"%PDF-1.7 test", _aad(doc)))
    async with as_user(app_engine, user) as conn:
        await conn.execute(
            bound_text(
                "insert into documents (id, patient_id, client_id, storage_key, mime_type,"
                " size_bytes, sha256, has_text_layer) values"
                " (:i, :p, :c, :k, 'application/pdf', 13, :h, true)"
            ),
            {"i": doc, "p": patient, "c": uuid4(), "k": key, "h": sha256(doc.bytes).hexdigest()},
        )
        await conn.execute(
            bound_text("update documents set status = 'queued' where id = :i"), {"i": doc}
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


async def _age(owner_engine: AsyncEngine, doc: UUID, age: timedelta) -> None:
    """Make a document look this long untouched (the touch trigger would reset the time)."""
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(bound_text("alter table documents disable trigger documents_touch"))
        await conn.execute(
            bound_text(
                "update documents set updated_at = now() - make_interval(secs => :s),"
                " created_at = now() - make_interval(secs => :s) where id = :d"
            ),
            {"d": doc, "s": age.total_seconds()},
        )
        await conn.execute(bound_text("alter table documents enable trigger documents_touch"))


def _reader(document: ReadDocument | None, lines: tuple[tuple[int, str], ...] = ()) -> Any:
    return lambda data, claimed: Reading(document, lines)


async def test_a_known_layout_becomes_draft_reports_for_review(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    test_code: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, user = MemoryObjectStore(), await make_user(owner_engine)
    patient = await make_patient(app_engine, user)
    doc = await _queued(app_engine, store, user, patient)
    monkeypatch.setattr(worker, "_read", _reader(_reading(test_code)))
    assert (await worker.extract(app_engine, store, doc, user)).result == "needs_review"
    assert await _status(app_engine, user, doc) == ("needs_review", None)
    async with as_user(app_engine, user) as conn:
        report = (
            await conn.execute(
                bound_text(
                    "select r.status::text as status, r.collected_at, r.collected_precision,"
                    " r.analysed_at, r.recorded_by,"
                    " r.has_unconfirmed_critical, r.name_match_score, x.method, x.reader,"
                    " x.raw_output"
                    " from lab_reports r join extraction_runs x on x.id = r.extraction_run_id"
                    " where r.document_id = :d"
                ),
                {"d": doc},
            )
        ).one()
        results = (
            await conn.execute(
                bound_text(
                    "select position, test_code, value_numeric, ref_low, ref_high, lab_flag,"
                    " flag::text as flag, flag_source, flag_mismatch, unit_canonical,"
                    " value_canonical, issues, confidence from lab_results"
                    " where patient_id = :p order by position"
                ),
                {"p": patient},
            )
        ).all()
    async with owner_engine.connect() as conn:  # the app role cannot read the audit log
        audited = await scalar(
            conn,
            bound_text(
                "select count(*) from audit_logs where action = 'document.extract'"
                " and entity_id = :d"
            ),
            {"d": str(doc)},
        )
    assert (report.status, report.recorded_by, report.has_unconfirmed_critical) == (
        "needs_review",
        user,
        False,
    )
    assert (report.method, report.reader) == ("local", "unte.v1")
    assert report.collected_precision == "day"  # H30: no made-up midnight
    assert report.analysed_at is not None
    # the printed name never reaches storage (only how well it matched)
    assert "Patient" not in str(report.raw_output)
    assert str(report.name_match_score) == "1.00"
    glucose, amylase = results
    assert (glucose.test_code, str(glucose.value_numeric), glucose.issues) == (
        test_code,
        "5.37",
        [],
    )
    assert (str(glucose.ref_low), str(glucose.ref_high), glucose.flag) == (
        "4.11",
        "6.38",
        "normal",
    )
    assert (glucose.flag_source, glucose.unit_canonical, str(glucose.value_canonical)) == (
        "computed_document_range",
        "mmol/L",
        "5.37",
    )
    # the lab's H on a value inside its printed range: for the person to check
    assert (amylase.test_code, amylase.lab_flag, amylase.flag, amylase.flag_mismatch) == (
        None,
        "H",
        "normal",
        True,
    )
    assert amylase.issues == ["unknown_test", "flag_mismatch"]
    assert str(amylase.confidence) == "0.80"
    assert audited == 1
    async with as_user(app_engine, user) as conn:  # the owner (and uploader) is told once
        notices = (
            await conn.execute(bound_text("select kind, entity_id from notifications"))
        ).all()
    assert [(n.kind, n.entity_id) for n in notices] == [("review_ready", str(doc))]
    # a second run changes nothing: the status moved on
    assert (await worker.extract(app_engine, store, doc, user)).result == "done"


async def test_a_name_that_does_not_fit_the_profile_is_marked(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    test_code: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, user = MemoryObjectStore(), await make_user(owner_engine)
    patient = await make_patient(app_engine, user)
    doc = await _queued(app_engine, store, user, patient)
    monkeypatch.setattr(
        worker, "_read", _reader(_reading(test_code, family="Өөр", given="Хүнийнэр"))
    )
    await worker.extract(app_engine, store, doc, user)
    async with as_user(app_engine, user) as conn:
        row = (
            await conn.execute(
                bound_text(
                    "select r.name_match_score, x.issues from lab_reports r"
                    " join extraction_runs x on x.id = r.extraction_run_id where r.document_id = :d"
                ),
                {"d": doc},
            )
        ).one()
    assert row.name_match_score == 0
    assert "name_mismatch" in row.issues


async def test_an_unknown_layout_or_a_scan_is_not_read_here(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, user = MemoryObjectStore(), await make_user(owner_engine)
    patient = await make_patient(app_engine, user)
    doc = await _queued(app_engine, store, user, patient)
    monkeypatch.setattr(worker, "_read", _reader(None))
    assert (await worker.extract(app_engine, store, doc, user)).result == "not_read"
    assert await _status(app_engine, user, doc) == ("failed", "not_read")


async def test_an_error_while_reading_fails_the_document_without_partial_rows(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    test_code: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, user = MemoryObjectStore(), await make_user(owner_engine)
    patient = await make_patient(app_engine, user)
    doc = await _queued(app_engine, store, user, patient)
    monkeypatch.setattr(worker, "_read", _reader(_reading(test_code)))

    def broken(*args: object, **kwargs: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(worker, "_result_params", broken)
    assert (await worker.extract(app_engine, store, doc, user)).result == "failed"
    assert await _status(app_engine, user, doc) == ("failed", "extraction_error")
    async with as_user(app_engine, user) as conn:
        assert (
            await scalar(
                conn,
                bound_text(
                    "select (select count(*) from lab_reports where patient_id = :p)"
                    " + (select count(*) from extraction_runs where patient_id = :p)"
                ),
                {"p": patient},
            )
            == 0
        )


async def test_a_file_missing_from_storage_is_unreadable(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    store, user = MemoryObjectStore(), await make_user(owner_engine)
    patient = await make_patient(app_engine, user)
    doc = await _queued(app_engine, store, user, patient)
    await store.delete(storage_key(patient, doc))
    assert (await worker.extract(app_engine, store, doc, user)).result == "failed"
    assert await _status(app_engine, user, doc) == ("failed", "unreadable")


@pytest.mark.parametrize("level", ["doctor", "viewer"])
async def test_a_readers_task_reads_nothing(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    test_code: str,
    monkeypatch: pytest.MonkeyPatch,
    level: str,
) -> None:
    store = MemoryObjectStore()
    owner, reader = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    await grant(app_engine, owner, patient, reader, level)
    doc = await _queued(app_engine, store, owner, patient)
    monkeypatch.setattr(worker, "_read", _reader(_reading(test_code)))
    assert (await worker.extract(app_engine, store, doc, reader)).result == "done"
    assert await _status(app_engine, owner, doc) == ("queued", None)


async def test_a_strangers_or_an_admins_task_reads_and_writes_nothing(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    test_code: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, owner = MemoryObjectStore(), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    doc = await _queued(app_engine, store, owner, patient)
    monkeypatch.setattr(worker, "_read", _reader(_reading(test_code)))
    for other in (
        await make_user(owner_engine),
        await make_user(owner_engine, "super_admin"),  # rule 2a
        await make_user(owner_engine, "support"),
    ):
        assert (await worker.extract(app_engine, store, doc, other)).result == "done"
    assert await _status(app_engine, owner, doc) == ("queued", None)
    async with owner_engine.connect() as conn:
        assert (
            await scalar(
                conn,
                bound_text("select count(*) from extraction_runs where document_id = :d"),
                {"d": doc},
            )
            == 0
        )


async def test_access_ending_mid_read_leaves_no_rows_and_the_sweep_ends_it(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    maint_engine: AsyncEngine,
    test_code: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = MemoryObjectStore()
    owner, carer = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    await grant(app_engine, owner, patient, carer, "caregiver")
    doc = await _queued(app_engine, store, carer, patient)
    monkeypatch.setattr(worker, "_read", _reader(_reading(test_code)))
    catalog = worker._catalog

    async def revoke_then_catalog(conn: Any) -> Any:
        async with owner_engine.connect() as other, other.begin():
            await other.execute(
                bound_text(
                    "update patient_access set revoked_at = now()"
                    " where patient_id = :p and user_id = :u"
                ),
                {"p": patient, "u": carer},
            )
        return await catalog(conn)

    monkeypatch.setattr(worker, "_catalog", revoke_then_catalog)
    assert (await worker.extract(app_engine, store, doc, carer)).result == "failed"
    async with owner_engine.connect() as conn, conn.begin():
        row = (
            await conn.execute(
                bound_text(
                    "select status::text as s, (select count(*) from lab_reports"
                    " where document_id = :d) as reports from documents where id = :d"
                ),
                {"d": doc},
            )
        ).one()
        assert (row.s, row.reports) == ("processing", 0)  # the carer can no longer move it
    await _age(owner_engine, doc, timedelta(minutes=11))
    async with maint_engine.connect() as conn, conn.begin():
        await conn.execute(bound_text("select * from maint_sweep_extractions()"))
    assert await _status(app_engine, owner, doc) == ("failed", "extraction_timeout")


async def test_the_sweep_hands_back_a_lost_task_and_fails_a_day_old_one(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, maint_engine: AsyncEngine
) -> None:
    store, user = MemoryObjectStore(), await make_user(owner_engine)
    patient = await make_patient(app_engine, user)
    lost = await _queued(app_engine, store, user, patient)
    old = await _queued(app_engine, store, user, patient)
    fresh = await _queued(app_engine, store, user, patient)
    for doc, age in ((lost, timedelta(minutes=20)), (old, timedelta(days=2))):
        await _age(owner_engine, doc, age)
    async with maint_engine.connect() as conn, conn.begin():
        again = (await conn.execute(bound_text("select * from maint_sweep_extractions()"))).all()
    assert (lost, user) in [(r.document_id, r.user_id) for r in again]
    assert fresh not in [r.document_id for r in again]
    assert await _status(app_engine, user, old) == ("failed", "extraction_timeout")
    assert await _status(app_engine, user, lost) == ("queued", None)
    # handed back once: not again within 15 minutes
    async with maint_engine.connect() as conn, conn.begin():
        again = (await conn.execute(bound_text("select * from maint_sweep_extractions()"))).all()
    assert lost not in [r.document_id for r in again]


async def test_a_reading_that_takes_too_long_times_out(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The child process was killed (test_isolated_reader): the document is failed."""
    store, user = MemoryObjectStore(), await make_user(owner_engine)
    patient = await make_patient(app_engine, user)
    doc = await _queued(app_engine, store, user, patient)

    def killed(data: bytes, claimed: object) -> None:
        raise TimeoutError

    monkeypatch.setattr(worker, "_read", killed)
    assert (await worker.extract(app_engine, store, doc, user)).result == "failed"
    assert await _status(app_engine, user, doc) == ("failed", "extraction_timeout")
