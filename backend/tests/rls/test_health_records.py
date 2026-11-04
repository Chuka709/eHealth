"""RLS and shape for the Phase 2.6 tables (0018; phi-table)."""

from datetime import UTC, datetime, timedelta
from typing import Any, LiteralString
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.db.sql import bound_text

from .conftest import as_user, grant, make_patient, make_user, scalar
from .test_account_deletion import _age, _purge, _request

pytestmark = pytest.mark.db

_INSERTS: dict[str, LiteralString] = {
    "clinical_events": "insert into clinical_events (patient_id, client_id, kind, title,"
    " started_on) values (:p, :c, 'biopsy', 'Бөөрний биопси', '2026-10-01') returning id",
    "vitals": "insert into vitals (patient_id, client_id, kind, value, unit, measured_at)"
    " values (:p, :c, 'bp_systolic', 128, 'mmHg', now()) returning id",
    "allergies": "insert into allergies (patient_id, client_id, substance, severity)"
    " values (:p, :c, 'Пенициллин', 'severe') returning id",
    "emergency_contacts": "insert into emergency_contacts (patient_id, client_id, name, phone)"
    " values (:p, :c, 'Дорж', '+976 9911 2233') returning id",
    "appointments": "insert into appointments (patient_id, client_id, kind, title, scheduled_at)"
    " values (:p, :c, 'lab', 'Такролимусын түвшин', now() + interval '2 days') returning id",
    "doctor_questions": "insert into doctor_questions (patient_id, client_id, text)"
    " values (:p, :c, 'Вакцин хийлгэж болох уу?') returning id",
}
_COUNTS: dict[str, LiteralString] = {
    "clinical_events": "select count(*) from clinical_events where patient_id = :p",
    "vitals": "select count(*) from vitals where patient_id = :p",
    "allergies": "select count(*) from allergies where patient_id = :p",
    "emergency_contacts": "select count(*) from emergency_contacts where patient_id = :p",
    "appointments": "select count(*) from appointments where patient_id = :p",
    "doctor_questions": "select count(*) from doctor_questions where patient_id = :p",
}
_UPDATES: dict[str, LiteralString] = {
    "clinical_events": "update clinical_events set title = 'x' where id = :i",
    "allergies": "update allergies set reaction = 'x' where id = :i",
    "emergency_contacts": "update emergency_contacts set relation = 'x' where id = :i",
    "appointments": "update appointments set notes = 'x' where id = :i",
    "doctor_questions": "update doctor_questions set answer = 'x' where id = :i",
}
_DELETES: dict[str, LiteralString] = {
    "clinical_events": "delete from clinical_events where id = :i",
    "vitals": "delete from vitals where id = :i",
    "allergies": "delete from allergies where id = :i",
    "emergency_contacts": "delete from emergency_contacts where id = :i",
    "appointments": "delete from appointments where id = :i",
    "doctor_questions": "delete from doctor_questions where id = :i",
}
_WRITERS: dict[str, LiteralString] = {
    "clinical_events": "select recorded_by from clinical_events where id = :i",
    "vitals": "select recorded_by from vitals where id = :i",
    "allergies": "select recorded_by from allergies where id = :i",
    "emergency_contacts": "select recorded_by from emergency_contacts where id = :i",
    "appointments": "select recorded_by from appointments where id = :i",
    "doctor_questions": "select recorded_by from doctor_questions where id = :i",
}
_ALL: dict[str, LiteralString] = {
    "clinical_events": "select count(*) from clinical_events",
    "vitals": "select count(*) from vitals",
    "allergies": "select count(*) from allergies",
    "emergency_contacts": "select count(*) from emergency_contacts",
    "appointments": "select count(*) from appointments",
    "doctor_questions": "select count(*) from doctor_questions",
}
TABLES = list(_INSERTS)


async def _seed(app_engine: AsyncEngine, user: UUID, patient: UUID) -> dict[str, UUID]:
    out = {}
    async with as_user(app_engine, user) as conn:
        for table, sql in _INSERTS.items():
            out[table] = await scalar(conn, bound_text(sql), {"p": patient, "c": uuid4()})
    return out


async def _counts(app_engine: AsyncEngine, user: UUID | None, patient: UUID) -> list[int]:
    async with as_user(app_engine, user) as conn:
        return [await scalar(conn, bound_text(_COUNTS[t]), {"p": patient}) for t in TABLES]


async def test_owner_reads_writes_and_the_database_records_the_writer(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    ids = await _seed(app_engine, owner, patient)
    assert await _counts(app_engine, owner, patient) == [1] * len(TABLES)
    async with as_user(app_engine, owner) as conn:
        for table, sql in _UPDATES.items():
            assert (await conn.execute(bound_text(sql), {"i": ids[table]})).rowcount == 1
    async with owner_engine.connect() as conn:
        for table in TABLES:
            writer = await scalar(
                conn,
                bound_text(_WRITERS[table]),
                {"i": ids[table]},
            )
            assert writer == owner, table


async def test_vitals_are_never_edited(app_engine: AsyncEngine, owner_engine: AsyncEngine) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    ids = await _seed(app_engine, owner, patient)
    with pytest.raises(DBAPIError, match="permission denied"):
        async with as_user(app_engine, owner) as conn:
            await conn.execute(
                bound_text("update vitals set value = 130 where id = :i"), {"i": ids["vitals"]}
            )
    async with as_user(app_engine, owner) as conn:  # a wrong one is deleted and entered again
        await conn.execute(bound_text(_DELETES["vitals"]), {"i": ids["vitals"]})


@pytest.mark.parametrize(
    ("kind", "value", "unit"),
    [
        ("bp_systolic", "1200", "mmHg"),  # a typo, not a reading
        ("bp_systolic", "128", "kg"),  # the wrong unit for the kind
        ("pulse", "72.5", "bpm"),
        ("temperature", "29.9", "C"),
        ("glucose", "120", "mmol_L"),  # mg/dL written as mmol/L
        ("spo2", "101", "percent"),
        ("weight", "0", "kg"),
        ("urine_output", "-1", "ml"),
    ],
)
async def test_implausible_vitals_are_refused(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, kind: str, value: str, unit: str
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    with pytest.raises(DBAPIError, match="check constraint"):
        async with as_user(app_engine, owner) as conn:
            await conn.execute(
                bound_text(
                    "insert into vitals (patient_id, client_id, kind, value, unit, measured_at)"
                    " values (:p, :c, cast(:k as vital_kind), cast(:v as numeric), :u, now())"
                ),
                {"p": patient, "c": uuid4(), "k": kind, "v": value, "u": unit},
            )


async def test_a_blood_pressure_reading_has_one_value_per_kind(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    group = uuid4()
    insert = bound_text(
        "insert into vitals (patient_id, client_id, kind, value, unit, measured_at, group_id)"
        " values (:p, :c, cast(:k as vital_kind), :v, :u, now(), :g)"
    )
    async with as_user(app_engine, owner) as conn:
        for kind, value, unit in (("bp_systolic", 128, "mmHg"), ("bp_diastolic", 82, "mmHg")):
            await conn.execute(
                insert, {"p": patient, "c": uuid4(), "k": kind, "v": value, "u": unit, "g": group}
            )
    with pytest.raises(DBAPIError, match="unique"):
        async with as_user(app_engine, owner) as conn:
            await conn.execute(
                insert,
                {"p": patient, "c": uuid4(), "k": "bp_systolic", "v": 130, "u": "mmHg", "g": group},
            )


async def test_identity_columns_belong_to_the_database(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, other = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    ids = await _seed(app_engine, owner, patient)
    statements: list[tuple[LiteralString, dict[str, Any]]] = [
        ("update allergies set recorded_by = :o where id = :i", {"o": other}),
        ("update appointments set created_at = now() where id = :i", {}),
        ("update clinical_events set patient_id = gen_random_uuid() where id = :i", {}),
        ("update doctor_questions set client_id = gen_random_uuid() where id = :i", {}),
    ]
    for sql, extra in statements:
        table = sql.split()[1]
        with pytest.raises(DBAPIError, match="permission denied"):
            async with as_user(app_engine, owner) as conn:
                await conn.execute(bound_text(sql), {"i": ids[table], **extra})


async def test_rows_cannot_point_at_another_profiles_rows(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    mine, child = (
        await make_patient(app_engine, owner),
        await make_patient(app_engine, owner, minor=True),
    )
    theirs = await _seed(app_engine, owner, child)
    with pytest.raises(DBAPIError, match="foreign key"):
        async with as_user(app_engine, owner) as conn:
            await conn.execute(
                bound_text(
                    "insert into doctor_questions (patient_id, client_id, text, appointment_id)"
                    " values (:p, :c, 'q', :a)"
                ),
                {"p": mine, "c": uuid4(), "a": theirs["appointments"]},
            )


async def test_a_retried_write_is_one_row(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    cid = uuid4()
    async with as_user(app_engine, owner) as conn:
        await conn.execute(bound_text(_INSERTS["allergies"]), {"p": patient, "c": cid})
    with pytest.raises(DBAPIError, match="unique"):
        async with as_user(app_engine, owner) as conn:
            await conn.execute(bound_text(_INSERTS["allergies"]), {"p": patient, "c": cid})


async def test_stranger_sees_and_changes_nothing(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, stranger = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    ids = await _seed(app_engine, owner, patient)
    assert await _counts(app_engine, stranger, patient) == [0] * len(TABLES)
    async with as_user(app_engine, stranger) as conn:
        for table, sql in _UPDATES.items():
            assert (await conn.execute(bound_text(sql), {"i": ids[table]})).rowcount == 0
        for table, sql in _DELETES.items():
            assert (await conn.execute(bound_text(sql), {"i": ids[table]})).rowcount == 0
    for table, sql in _INSERTS.items():
        with pytest.raises(DBAPIError, match="row-level security"):
            async with as_user(app_engine, stranger) as conn:
                await conn.execute(bound_text(sql), {"p": patient, "c": uuid4()})
        del table


@pytest.mark.parametrize(
    ("expires", "revoked", "visible"),
    [
        (None, False, 1),
        (datetime.now(UTC) - timedelta(minutes=1), False, 0),
        (None, True, 0),
    ],
)
async def test_shared_access_respects_expiry_and_revocation(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    expires: datetime | None,
    revoked: bool,
    visible: int,
) -> None:
    owner, doctor = await make_user(owner_engine), await make_user(owner_engine, "doctor")
    patient = await make_patient(app_engine, owner)
    await _seed(app_engine, owner, patient)
    await grant(app_engine, owner, patient, doctor, "doctor", expires=expires, revoked=revoked)
    assert await _counts(app_engine, doctor, patient) == [visible] * len(TABLES)


@pytest.mark.parametrize("level", ["doctor", "viewer"])
async def test_readers_cannot_write(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, level: str
) -> None:
    owner, reader = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    ids = await _seed(app_engine, owner, patient)
    await grant(app_engine, owner, patient, reader, level)
    async with as_user(app_engine, reader) as conn:
        for table, sql in _UPDATES.items():
            assert (await conn.execute(bound_text(sql), {"i": ids[table]})).rowcount == 0
        for table, sql in _DELETES.items():
            assert (await conn.execute(bound_text(sql), {"i": ids[table]})).rowcount == 0
    for sql in _INSERTS.values():
        with pytest.raises(DBAPIError, match="row-level security"):
            async with as_user(app_engine, reader) as conn:
                await conn.execute(bound_text(sql), {"p": patient, "c": uuid4()})


async def test_caregiver_writes_and_is_recorded(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, carer = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    await grant(app_engine, owner, patient, carer, "caregiver")
    ids = await _seed(app_engine, carer, patient)
    async with as_user(app_engine, owner) as conn:
        await conn.execute(bound_text(_UPDATES["allergies"]), {"i": ids["allergies"]})
    async with owner_engine.connect() as conn:
        row = (
            await conn.execute(
                bound_text("select recorded_by, updated_by from allergies where id = :i"),
                {"i": ids["allergies"]},
            )
        ).one()
    assert (row.recorded_by, row.updated_by) == (carer, owner)


async def test_no_user_context_and_admin_roles_see_nothing(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    admin_engine: AsyncEngine,
    admin_login_engine: AsyncEngine,
    maint_engine: AsyncEngine,
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    await _seed(app_engine, owner, patient)
    assert await _counts(app_engine, None, patient) == [0] * len(TABLES)
    for engine in (admin_engine, admin_login_engine, maint_engine):
        for table in TABLES:
            with pytest.raises(DBAPIError, match="permission denied"):
                async with engine.connect() as conn:
                    await conn.execute(bound_text(_ALL[table]))


async def test_purging_an_account_erases_its_records(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, maint_engine: AsyncEngine
) -> None:
    leaving = await make_user(owner_engine)
    patient = await make_patient(app_engine, leaving)
    await _seed(app_engine, leaving, patient)
    await _request(app_engine, leaving)
    await _age(owner_engine, leaving, 31)
    assert leaving in await _purge(maint_engine)
    async with owner_engine.connect() as conn:
        for table in TABLES:
            assert await scalar(conn, bound_text(_COUNTS[table]), {"p": patient}) == 0, table


async def test_caregiver_cannot_erase_the_owners_history(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    """Security review 2.6a M1: allergies (the emergency card), events, contacts and vitals
    are erased only by the owner or by whoever wrote the row."""
    owner, carer = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    await grant(app_engine, owner, patient, carer, "caregiver")
    ids = await _seed(app_engine, owner, patient)
    async with as_user(app_engine, carer) as conn:
        for t in ("clinical_events", "allergies", "emergency_contacts", "vitals"):
            assert (await conn.execute(bound_text(_DELETES[t]), {"i": ids[t]})).rowcount == 0, t
        for t in ("appointments", "doctor_questions"):
            assert (await conn.execute(bound_text(_DELETES[t]), {"i": ids[t]})).rowcount == 1, t
    mine = await _seed(app_engine, carer, patient)
    async with as_user(app_engine, carer) as conn:
        for t in ("clinical_events", "allergies", "emergency_contacts", "vitals"):
            assert (await conn.execute(bound_text(_DELETES[t]), {"i": mine[t]})).rowcount == 1, t
    async with as_user(app_engine, owner) as conn:
        assert (
            await conn.execute(bound_text(_DELETES["allergies"]), {"i": ids["allergies"]})
        ).rowcount == 1


async def test_an_event_links_only_this_profiles_transplant(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    mine = await make_patient(app_engine, owner)
    child = await make_patient(app_engine, owner, minor=True)
    async with as_user(app_engine, owner) as conn:
        theirs = await scalar(
            conn,
            bound_text(
                "insert into transplants (patient_id, client_id, organ, transplant_date, country,"
                " hospital) values (:p, gen_random_uuid(), 'kidney', '2021-06-14', 'MN', 'X')"
                " returning id"
            ),
            {"p": child},
        )
    ids = await _seed(app_engine, owner, mine)
    with pytest.raises(DBAPIError, match="foreign key"):
        async with as_user(app_engine, owner) as conn:
            await conn.execute(
                bound_text("update clinical_events set transplant_id = :t where id = :i"),
                {"t": theirs, "i": ids["clinical_events"]},
            )
