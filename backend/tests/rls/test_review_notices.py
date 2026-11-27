"""Flags, critical drafts and who is told when a document is read (Phase 5.2; 0035; H5)."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.db.sql import bound_text
from labtrack.extraction.types import PrintedIdentity, ReadDocument, ReadReport, ReadResult
from labtrack.storage import MemoryObjectStore
from labtrack.worker import extraction as worker

from .conftest import as_user, grant, make_patient, make_user, scalar
from .test_document_extraction import _queued, _reader, test_code  # noqa: F401 - fixture

pytestmark = pytest.mark.db


def _critical_reading(code: str, value: str = "2,1") -> ReadDocument:
    row = ReadResult(
        f"Глюкоз {code}", value, "ммоль/л", "4.11 - 6.38", None, 1, "row",
        critical_text="< 2.5",
    )  # fmt: skip
    return ReadDocument(
        reader="unte.v1",
        reports=(ReadReport("Lab", "Биохими", "цус", "2025-08-18", None, (row,), None),),
        identity=PrintedIdentity(family_name="Patient", given_name="Test"),
    )


async def _notices(app_engine: AsyncEngine, user: UUID) -> list[tuple[str, str]]:
    async with as_user(app_engine, user) as conn:
        rows = (await conn.execute(bound_text("select kind, entity_id from notifications"))).all()
    return [(r.kind, r.entity_id) for r in rows]


async def _alerts(owner_engine: AsyncEngine, patient: UUID, carer: UUID, *, on: bool) -> None:
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "insert into caregiver_alert_settings (patient_id, caregiver_user_id,"
                " critical_result) values (:p, :c, :on)"
            ),
            {"p": patient, "c": carer, "on": on},
        )


async def test_a_critical_draft_tells_owner_uploader_and_alerting_caregivers_only(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    test_code: str,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = MemoryObjectStore()
    owner, uploader, quiet, doctor, stranger = [await make_user(owner_engine) for _ in range(5)]
    patient = await make_patient(app_engine, owner)
    for carer in (uploader, quiet):
        await grant(app_engine, owner, patient, carer, "caregiver")
    await grant(app_engine, owner, patient, doctor, "doctor")
    await _alerts(owner_engine, patient, uploader, on=False)  # told as the uploader anyway
    await _alerts(owner_engine, patient, quiet, on=False)
    doc = await _queued(app_engine, store, uploader, patient)
    monkeypatch.setattr(worker, "_read", _reader(_critical_reading(test_code)))
    assert (await worker.extract(app_engine, store, doc, uploader)).result == "needs_review"
    async with as_user(app_engine, owner) as conn:
        report = (
            await conn.execute(
                bound_text(
                    "select r.has_unconfirmed_critical, x.flag::text as flag, x.critical_low,"
                    " x.critical_high, x.issues from lab_reports r"
                    " join lab_results x on x.report_id = r.id where r.document_id = :d"
                ),
                {"d": doc},
            )
        ).one()
    assert report.has_unconfirmed_critical
    # "< 2.5" printed as the critical limit: critical below 2.5
    assert (report.flag, report.critical_low, report.critical_high) == (
        "critical_low",
        Decimal("2.5"),
        None,
    )
    expected = [("critical_pending", str(doc))]
    assert await _notices(app_engine, owner) == expected
    assert await _notices(app_engine, uploader) == expected
    assert await _notices(app_engine, quiet) == []  # alerts off
    assert await _notices(app_engine, doctor) == []  # a reader never hears of a draft
    assert await _notices(app_engine, stranger) == []
    # announced once, however often it is asked
    async with as_user(app_engine, uploader) as conn:
        await conn.execute(bound_text("select notify_document_read(:d)"), {"d": doc})
    assert await _notices(app_engine, owner) == expected


async def test_a_caregiver_with_critical_alerts_on_is_told(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    test_code: str,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = MemoryObjectStore()
    owner, carer, paused = [await make_user(owner_engine) for _ in range(3)]
    patient = await make_patient(app_engine, owner)
    for c in (carer, paused):
        await grant(app_engine, owner, patient, c, "caregiver")
    await _alerts(owner_engine, patient, carer, on=True)
    await _alerts(owner_engine, patient, paused, on=True)
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "update caregiver_alert_settings set owner_paused = true"
                " where caregiver_user_id = :c"
            ),
            {"c": paused},
        )
    doc = await _queued(app_engine, store, owner, patient)
    monkeypatch.setattr(worker, "_read", _reader(_critical_reading(test_code)))
    assert (await worker.extract(app_engine, store, doc, owner)).result == "needs_review"
    assert await _notices(app_engine, carer) == [("critical_pending", str(doc))]
    assert await _notices(app_engine, paused) == []


async def test_only_the_uploader_may_announce_a_document(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    test_code: str,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = MemoryObjectStore()
    owner, carer, stranger = [await make_user(owner_engine) for _ in range(3)]
    patient = await make_patient(app_engine, owner)
    await grant(app_engine, owner, patient, carer, "caregiver")
    doc = await _queued(app_engine, store, owner, patient)
    monkeypatch.setattr(worker, "_read", _reader(_critical_reading(test_code, "5,0")))
    await worker.extract(app_engine, store, doc, owner)
    for user in (carer, stranger):
        with pytest.raises(DBAPIError, match="notification not allowed"):
            async with as_user(app_engine, user) as conn:
                await conn.execute(bound_text("select notify_document_read(:d)"), {"d": doc})
    with pytest.raises(DBAPIError, match="notification not allowed"):
        async with as_user(app_engine, owner) as conn:
            await conn.execute(bound_text("select notify_document_read(:d)"), {"d": uuid4()})


async def test_an_earlier_confirmed_value_marks_duplicates_and_large_changes(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    test_code: str,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = MemoryObjectStore()
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text("update test_catalog set delta_check_pct = 50 where code = :c"),
            {"c": test_code},
        )
        for day, value in ((datetime(2025, 8, 17, 1, tzinfo=UTC), "2.0"),
                           (datetime(2025, 8, 18, 1, tzinfo=UTC), "5.0")):  # fmt: skip
            report = uuid4()
            await conn.execute(
                bound_text(
                    "insert into lab_reports (id, patient_id, collected_at, status, confirmed_at,"
                    " recorded_by) values (:r, :p, :at, 'confirmed', now(), :u)"
                ),
                {"r": report, "p": patient, "at": day, "u": owner},
            )
            await conn.execute(
                bound_text(
                    "insert into lab_results (report_id, patient_id, position, test_code,"
                    " raw_name, raw_value, value_numeric, value_canonical, unit_canonical)"
                    " values (:r, :p, 0, :c, 'x', :raw, :v, :v, 'mmol/L')"
                ),
                {"r": report, "p": patient, "c": test_code, "raw": value, "v": Decimal(value)},
            )
    doc = await _queued(app_engine, store, owner, patient)
    monkeypatch.setattr(worker, "_read", _reader(_critical_reading(test_code, "5,0")))
    await worker.extract(app_engine, store, doc, owner)
    async with as_user(app_engine, owner) as conn:
        issues = await scalar(
            conn,
            bound_text(
                "select x.issues from lab_results x join lab_reports r on r.id = x.report_id"
                " where r.document_id = :d"
            ),
            {"d": doc},
        )
    # 5.0 again on 18 August: maybe the same result twice; 2.0 -> 5.0 the day before: +150 %
    assert "possible_duplicate" in issues
    assert "large_delta" in issues


async def test_review_ready_goes_to_owner_and_uploader_only(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    test_code: str,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = MemoryObjectStore()
    owner, carer = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    await grant(app_engine, owner, patient, carer, "caregiver")
    await _alerts(owner_engine, patient, carer, on=True)  # critical alerts only
    doc = await _queued(app_engine, store, owner, patient)
    monkeypatch.setattr(worker, "_read", _reader(_critical_reading(test_code, "5,0")))
    await worker.extract(app_engine, store, doc, owner)
    assert await _notices(app_engine, owner) == [("review_ready", str(doc))]
    assert await _notices(app_engine, carer) == []


@pytest.mark.parametrize("who", ["caregiver", "owner"])
async def test_a_withdrawn_consent_stops_caregiver_critical_alerts(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    test_code: str,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    who: str,
) -> None:
    store = MemoryObjectStore()
    owner, carer = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    await grant(app_engine, owner, patient, carer, "caregiver")
    await _alerts(owner_engine, patient, carer, on=True)
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "insert into consents (user_id, kind, version, granted)"
                " values (:u, 'sensitive_data', 'v1', false)"
            ),
            {"u": carer if who == "caregiver" else owner},
        )
    doc = await _queued(app_engine, store, owner, patient)
    monkeypatch.setattr(worker, "_read", _reader(_critical_reading(test_code)))
    await worker.extract(app_engine, store, doc, owner)
    assert await _notices(app_engine, carer) == []


async def test_nobody_is_told_about_an_owner_deleting_the_account(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    test_code: str,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Q46: nothing more is read out for an owner who asked to delete the account."""
    store = MemoryObjectStore()
    owner, carer = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    await grant(app_engine, owner, patient, carer, "caregiver")
    await _alerts(owner_engine, patient, carer, on=True)
    doc = await _queued(app_engine, store, carer, patient)
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text("update users set deleted_at = now() where id = :u"), {"u": owner}
        )
    monkeypatch.setattr(worker, "_read", _reader(_critical_reading(test_code)))
    await worker.extract(app_engine, store, doc, carer)
    assert await _notices(app_engine, carer) == []
