"""RLS for transplants, medications, medication_regimens, medication_intakes (0014; phi-table)."""

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.db.sql import bound_text

from .conftest import as_user, grant, make_patient, make_user, scalar
from .test_account_deletion import _age, _purge, _request

pytestmark = pytest.mark.db

TABLES = ("transplants", "medications", "medication_regimens", "medication_intakes")

_TRANSPLANT = bound_text(
    "insert into transplants (patient_id, client_id, organ, transplant_date, country, hospital)"
    " values (:p, :c, 'kidney', '2021-06-14', 'MN', 'Улсын нэгдүгээр төв эмнэлэг')"
    " returning id"
)
_MEDICATION = bound_text(
    "insert into medications (patient_id, client_id, catalog_code, name, strength, transplant_id)"
    " values (:p, :c, null, 'Такролимус', '1 мг', :t) returning id"
)
_REGIMEN = bound_text(
    "insert into medication_regimens (patient_id, medication_id, client_id, effective_from,"
    " dose_unit, schedule) values (:p, :m, :c, :d, 'mg', jsonb_build_object('type', 'daily',"
    " 'times', jsonb_build_array("
    " jsonb_build_object('at', '08:00', 'amount', cast(cast(:a as numeric) as text)),"
    " jsonb_build_object('at', '20:00', 'amount', cast(cast(:a as numeric) as text)))))"
    " returning id"
)
_REGIMEN_RAW = bound_text(
    "insert into medication_regimens (patient_id, medication_id, client_id, effective_from,"
    " dose_amount, dose_unit, dose_unit_text, schedule)"
    " values (:p, :m, gen_random_uuid(), :d, :a, :u, :ut, cast(:s as jsonb))"
)
_INTAKE = bound_text(
    "insert into medication_intakes (patient_id, medication_id, client_id, scheduled_at,"
    " taken_at, status) values (:p, :m, :c, :at, :at, 'taken') returning id"
)
_DAILY = json.dumps({"type": "daily", "times": ["08:00", "20:00"]})


def _minute() -> datetime:
    """Now, as a whole minute (0015: scheduled doses are HH:MM)."""
    return datetime.now(UTC).replace(second=0, microsecond=0)


def _cid() -> UUID:
    return uuid4()


async def _seed(app_engine: AsyncEngine, user: UUID, patient: UUID) -> dict[str, Any]:
    """One row in each table, written as `user` through RLS."""
    at = datetime(2026, 11, 1, 0, 0, tzinfo=UTC)
    async with as_user(app_engine, user) as conn:
        t = await scalar(conn, _TRANSPLANT, {"p": patient, "c": _cid()})
        m = await scalar(conn, _MEDICATION, {"p": patient, "c": _cid(), "t": t})
        r = await scalar(
            conn,
            _REGIMEN,
            {
                "p": patient,
                "m": m,
                "c": _cid(),
                "d": date(2026, 1, 1),
                "a": Decimal("2"),
                "s": _DAILY,
            },
        )
        i = await scalar(conn, _INTAKE, {"p": patient, "m": m, "c": _cid(), "at": at})
    return {"transplants": t, "medications": m, "medication_regimens": r, "medication_intakes": i}


async def _counts(app_engine: AsyncEngine, user: UUID | None, patient: UUID) -> list[int]:
    async with as_user(app_engine, user) as conn:
        return [
            await scalar(
                conn,
                bound_text(f"select count(*) from {t} where patient_id = :p"),  # noqa: S608 - fixed names
                {"p": patient},
            )
            for t in TABLES
        ]


async def test_owner_reads_writes_and_keeps_dose_history(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    ids = await _seed(app_engine, owner, patient)
    assert await _counts(app_engine, owner, patient) == [1, 1, 1, 1]
    async with as_user(app_engine, owner) as conn:
        for sql in (
            "update transplants set graft_status = 'functioning', notes = 'хяналт' where id = :i",
            "update medications set stopped_on = current_date, stop_reason = 'эмч' where id = :i",
        ):
            table = sql.split()[1]
            assert (await conn.execute(bound_text(sql), {"i": ids[table]})).rowcount == 1
        stamp = await scalar(
            conn,
            bound_text("select updated_at from transplants where id = :i"),
            {"i": ids["transplants"]},
        )
        assert stamp is not None
        # a dose change is a new row: the old one stays
        await conn.execute(
            _REGIMEN,
            {
                "p": patient,
                "m": ids["medications"],
                "c": _cid(),
                "d": date(2026, 3, 1),
                "a": Decimal("1.5"),
                "s": _DAILY,
            },
        )
        n = await scalar(
            conn,
            bound_text("select count(*) from medication_regimens where medication_id = :m"),
            {"m": ids["medications"]},
        )
        assert n == 2
        r = await conn.execute(
            bound_text("delete from medication_intakes where id = :i"),
            {"i": ids["medication_intakes"]},
        )
        assert r.rowcount == 1  # "Буцаах" undoes a mistaken tap


async def test_dose_history_is_append_only(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    ids = await _seed(app_engine, owner, patient)
    for sql in (
        "update medication_regimens set dose_amount = 9 where id = :i",
        "delete from medication_regimens where id = :i",
        "truncate medication_regimens",
    ):
        with pytest.raises(DBAPIError, match="permission denied"):
            async with as_user(app_engine, owner) as conn:
                await conn.execute(bound_text(sql), {"i": ids["medication_regimens"]})
    # ... but they go with their medication
    async with as_user(app_engine, owner) as conn:
        await conn.execute(
            bound_text("delete from medications where id = :i"), {"i": ids["medications"]}
        )
    assert await _counts(app_engine, owner, patient) == [1, 0, 0, 0]


async def test_identity_columns_are_fixed(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    patient, other = (
        await make_patient(app_engine, owner),
        await make_patient(app_engine, owner, minor=True),
    )
    ids = await _seed(app_engine, owner, patient)
    for sql in (
        "update transplants set patient_id = :o where id = :i",
        "update medications set patient_id = :o where id = :i",
        "update medications set client_id = gen_random_uuid() where id = :i",
        "update medication_intakes set patient_id = :o where id = :i",
        "update medication_intakes set medication_id = gen_random_uuid() where id = :i",
    ):
        table = sql.split()[1]
        with pytest.raises(DBAPIError, match="permission denied"):
            async with as_user(app_engine, owner) as conn:
                await conn.execute(bound_text(sql), {"o": other, "i": ids[table]})


async def test_rows_cannot_point_at_another_patients_rows(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    """Composite FKs: even one's own two profiles cannot be cross-linked (IDOR)."""
    owner = await make_user(owner_engine)
    mine, child = (
        await make_patient(app_engine, owner),
        await make_patient(app_engine, owner, minor=True),
    )
    ids = await _seed(app_engine, owner, mine)
    attempts: list[tuple[Any, dict[str, Any]]] = [
        (_MEDICATION, {"p": child, "c": _cid(), "t": ids["transplants"]}),
        (
            _REGIMEN,
            {
                "p": child,
                "m": ids["medications"],
                "c": _cid(),
                "d": date(2026, 1, 1),
                "a": Decimal("1"),
                "s": _DAILY,
            },
        ),
        (
            _INTAKE,
            {"p": child, "m": ids["medications"], "c": _cid(), "at": _minute()},
        ),
    ]
    for sql, params in attempts:
        with pytest.raises(DBAPIError, match="foreign key"):
            async with as_user(app_engine, owner) as conn:
                await conn.execute(sql, params)


async def test_a_retried_create_finds_the_stored_row(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    ids = await _seed(app_engine, owner, patient)
    cid = _cid()
    at = datetime(2026, 11, 2, 0, 0, tzinfo=UTC)
    params = {"p": patient, "m": ids["medications"], "c": cid, "at": at}
    async with as_user(app_engine, owner) as conn:
        await conn.execute(_INTAKE, params)
    with pytest.raises(DBAPIError, match="unique"):
        async with as_user(app_engine, owner) as conn:
            await conn.execute(_INTAKE, params)
    # one row per scheduled dose, whatever device wrote it
    with pytest.raises(DBAPIError, match="unique"):
        async with as_user(app_engine, owner) as conn:
            await conn.execute(_INTAKE, {**params, "c": _cid()})


async def test_stranger_sees_and_changes_nothing(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, stranger = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    ids = await _seed(app_engine, owner, patient)
    assert await _counts(app_engine, stranger, patient) == [0, 0, 0, 0]
    async with as_user(app_engine, stranger) as conn:
        for table in TABLES:
            if table == "medication_regimens":
                continue  # no update/delete for anyone (test above)
            column = "note" if table == "medication_intakes" else "notes"
            for sql in (
                f"update {table} set {column} = 'x' where id = :i",  # noqa: S608
                f"delete from {table} where id = :i",  # noqa: S608
            ):
                assert (await conn.execute(bound_text(sql), {"i": ids[table]})).rowcount == 0
    with pytest.raises(DBAPIError, match="row-level security"):
        async with as_user(app_engine, stranger) as conn:
            await conn.execute(_TRANSPLANT, {"p": patient, "c": _cid()})


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
    assert await _counts(app_engine, doctor, patient) == [visible] * 4


@pytest.mark.parametrize("level", ["doctor", "viewer"])
async def test_readers_cannot_write(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, level: str
) -> None:
    owner, reader = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    ids = await _seed(app_engine, owner, patient)
    await grant(app_engine, owner, patient, reader, level)
    assert await _counts(app_engine, reader, patient) == [1, 1, 1, 1]
    async with as_user(app_engine, reader) as conn:
        r = await conn.execute(
            bound_text("update medications set name = 'x' where id = :i"),
            {"i": ids["medications"]},
        )
        assert r.rowcount == 0
    with pytest.raises(DBAPIError, match="row-level security"):
        async with as_user(app_engine, reader) as conn:
            await conn.execute(
                _INTAKE,
                {
                    "p": patient,
                    "m": ids["medications"],
                    "c": _cid(),
                    "at": _minute(),
                },
            )


def _sqlstate(exc: DBAPIError) -> str | None:
    pg = getattr(exc.orig, "__cause__", None) or exc.orig
    return getattr(pg, "sqlstate", None)


async def test_caregiver_writes_and_the_database_records_the_writers(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, carer = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    ids = await _seed(app_engine, owner, patient)
    await grant(app_engine, owner, patient, carer, "caregiver")
    # the caller cannot name the writer
    with pytest.raises(DBAPIError, match="permission denied"):
        async with as_user(app_engine, carer) as conn:
            await conn.execute(
                bound_text(
                    "insert into medication_intakes (patient_id, medication_id, client_id,"
                    " scheduled_at, taken_at, status, recorded_by)"
                    " values (:p, :m, gen_random_uuid(), now(), now(), 'taken', :o)"
                ),
                {"p": patient, "m": ids["medications"], "o": owner},
            )
    at = datetime(2026, 11, 3, 0, 0, tzinfo=UTC)
    async with as_user(app_engine, carer) as conn:
        intake = await scalar(
            conn, _INTAKE, {"p": patient, "m": ids["medications"], "c": _cid(), "at": at}
        )
        regimen = await scalar(
            conn,
            _REGIMEN,
            {
                "p": patient,
                "m": ids["medications"],
                "c": _cid(),
                "d": date(2026, 4, 1),
                "a": Decimal("1"),
                "s": _DAILY,
            },
        )
    async with as_user(app_engine, owner) as conn:
        await conn.execute(
            bound_text("update medication_intakes set note = 'хоолны дараа' where id = :i"),
            {"i": intake},
        )
        row = (
            await conn.execute(
                bound_text("select recorded_by, updated_by from medication_intakes where id = :i"),
                {"i": intake},
            )
        ).one()
        by = await scalar(
            conn,
            bound_text("select recorded_by from medication_regimens where id = :i"),
            {"i": regimen},
        )
    assert (row.recorded_by, row.updated_by, by) == (carer, owner, carer)


async def test_only_the_owner_deletes_history(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    """Deleting a medication or transplant erases its dose history: a caregiver stops it."""
    owner, carer = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    ids = await _seed(app_engine, owner, patient)
    await grant(app_engine, owner, patient, carer, "caregiver")
    async with as_user(app_engine, carer) as conn:
        for table in ("medications", "transplants"):
            r = await conn.execute(
                bound_text(f"delete from {table} where id = :i"),  # noqa: S608
                {"i": ids[table]},
            )
            assert r.rowcount == 0, table
        r = await conn.execute(
            bound_text("update medications set stopped_on = current_date where id = :i"),
            {"i": ids["medications"]},
        )
        assert r.rowcount == 1
    assert await _counts(app_engine, owner, patient) == [1, 1, 1, 1]


async def test_a_taken_dose_stays_taken(app_engine: AsyncEngine, owner_engine: AsyncEngine) -> None:
    """H20 in the database: a second device's "skipped" never overwrites "taken"."""
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    ids = await _seed(app_engine, owner, patient)
    with pytest.raises(DBAPIError, match="a taken dose stays taken"):
        async with as_user(app_engine, owner) as conn:
            await conn.execute(
                bound_text(
                    "update medication_intakes set status = 'skipped', taken_at = null"
                    " where id = :i"
                ),
                {"i": ids["medication_intakes"]},
            )


async def test_regimens_in_one_transaction_keep_their_order(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    """Same effective_from, same transaction (a correction, a batch sync): the database's
    insertion order decides which is in force - never an arbitrary tie."""
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    ids = await _seed(app_engine, owner, patient)
    day = date(2026, 6, 1)
    async with as_user(app_engine, owner) as conn:
        for amount in ("3", "2.5"):
            await conn.execute(
                _REGIMEN,
                {
                    "p": patient,
                    "m": ids["medications"],
                    "c": _cid(),
                    "d": day,
                    "a": Decimal(amount),
                    "s": _DAILY,
                },
            )
        current = await scalar(
            conn,
            bound_text(
                "select schedule->'times'->0->>'amount' from medication_regimens"
                " where medication_id = :m"
                " and effective_from <= :d order by effective_from desc, seq desc limit 1"
            ),
            {"m": ids["medications"], "d": day},
        )
    assert current == "2.5"


async def test_stranger_ids_reveal_nothing(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    """With a stranger's medication id, a write fails the same way whether or not that
    patient recorded a dose then; and nobody chooses a row id (a clash would confirm one)."""
    victim, attacker = await make_user(owner_engine), await make_user(owner_engine)
    victims, own = await make_patient(app_engine, victim), await make_patient(app_engine, attacker)
    ids = await _seed(app_engine, victim, victims)
    at = datetime(2026, 11, 1, 0, 0, tzinfo=UTC)  # the victim's seeded intake time
    states = []
    for when in (at, at + timedelta(hours=1)):
        with pytest.raises(DBAPIError) as caught:
            async with as_user(app_engine, attacker) as conn:
                await conn.execute(
                    _INTAKE, {"p": own, "m": ids["medications"], "c": _cid(), "at": when}
                )
        states.append(_sqlstate(caught.value))
    assert states == ["23503", "23503"]  # the same foreign-key error either way
    with pytest.raises(DBAPIError, match="row-level security"):
        async with as_user(app_engine, attacker) as conn:
            await conn.execute(
                _INTAKE, {"p": victims, "m": ids["medications"], "c": _cid(), "at": at}
            )
    for table in TABLES:
        with pytest.raises(DBAPIError, match="permission denied"):
            async with as_user(app_engine, attacker) as conn:
                await conn.execute(
                    bound_text(f"insert into {table} (id, patient_id) values (:i, :p)"),  # noqa: S608
                    {"i": ids[table], "p": own},
                )


_TIMES = [{"at": "08:00", "amount": "2"}, {"at": "20:00", "amount": "1.5"}]


@pytest.mark.parametrize(
    ("schedule", "unit", "amount"),
    [
        ({"type": "daily"}, None, None),  # no times: the reminder would never fire (H6)
        ({"type": "daily", "times": []}, None, None),
        ({"type": "daily", "times": ["08:00"]}, None, None),  # the old shape
        ({"type": "weekly", "times": [{"at": "09:00"}]}, None, None),  # no days
        ({"type": "weekly", "times": [{"at": "09:00"}], "days": [0]}, None, None),
        ({"type": "hourly", "times": [{"at": "09:00"}]}, None, None),
        ({"type": "daily", "times": [{"at": "25:00"}]}, None, None),
        ({"type": "daily", "times": [{"at": "08:00", "amount": "0.00001"}]}, "mg", None),
        ({"type": "daily", "times": [{"at": "08:00", "amount": "1,000"}]}, "mg", None),
        ({"type": "daily", "times": [{"at": "08:00", "amount": "0"}]}, "mg", None),
        ({"type": "daily", "times": [{"at": "08:00"}, {"at": "08:00"}]}, None, None),
        ({"type": "weekly", "times": [{"at": "08:00"}], "days": [1, 1]}, None, None),
        ({"type": "daily", "times": [{"at": "08:00", "x": 1}]}, None, None),
        ({"type": "daily", "times": [{"at": "08:00"}], "note": "x"}, None, None),
        ({"type": "daily", "times": [{"at": "08:00"}], "days": [1]}, None, None),
        ({"type": "daily", "times": [{"at": "08:00", "amount": "2"}, {"at": "20:00"}]}, "mg", None),
        ({"type": "daily", "times": _TIMES}, None, None),  # amounts without a unit
        ({"type": "daily", "times": _TIMES}, "мкг", None),  # not a unit code
        ({"type": "daily", "times": [{"at": "08:00"}]}, "mg", None),  # a unit, no amount
        ({"type": "daily", "times": _TIMES}, "mg", "2"),  # dose_amount is for prn only
        ({"type": "prn"}, None, "2"),
        ({"type": "prn", "times": [{"at": "08:00"}]}, None, None),
    ],
)
async def test_regimen_shape_is_checked(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    schedule: dict[str, Any],
    unit: str | None,
    amount: str | None,
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    ids = await _seed(app_engine, owner, patient)
    params = {
        "p": patient,
        "m": ids["medications"],
        "d": date(2026, 1, 1),
        "a": Decimal(amount) if amount else None,
        "u": unit,
        "ut": None,
        "s": json.dumps(schedule),
    }
    with pytest.raises(DBAPIError, match="check constraint"):
        async with as_user(app_engine, owner) as conn:
            await conn.execute(_REGIMEN_RAW, params)


async def test_per_time_doses_and_other_units_are_stored(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    ids = await _seed(app_engine, owner, patient)
    base = {"p": patient, "m": ids["medications"], "d": date(2026, 1, 1)}
    async with as_user(app_engine, owner) as conn:
        for unit, text, amount, schedule in (
            ("mg", None, None, {"type": "daily", "times": _TIMES}),
            (
                "other",
                "халбага",
                None,
                {"type": "daily", "times": [{"at": "08:00", "amount": "1"}]},
            ),
            ("iu", None, Decimal("50000"), {"type": "prn"}),
            (None, None, None, {"type": "weekly", "times": [{"at": "09:00"}], "days": [1, 4]}),
        ):
            await conn.execute(
                _REGIMEN_RAW,
                {**base, "a": amount, "u": unit, "ut": text, "s": json.dumps(schedule)},
            )
    with pytest.raises(DBAPIError, match="check constraint"):  # "other" needs its text
        async with as_user(app_engine, owner) as conn:
            await conn.execute(
                _REGIMEN_RAW,
                {
                    **base,
                    "a": None,
                    "u": "other",
                    "ut": None,
                    "s": json.dumps({"type": "daily", "times": [{"at": "08:00", "amount": "1"}]}),
                },
            )


async def _future_regimen(app_engine: AsyncEngine, owner: UUID, patient: UUID, med: UUID) -> UUID:
    async with as_user(app_engine, owner) as conn:
        rid: UUID = await scalar(
            conn,
            _REGIMEN,
            {"p": patient, "m": med, "c": _cid(), "d": date(2099, 1, 1), "a": Decimal("1")},
        )
    return rid


async def test_a_future_dose_entered_by_mistake_is_voided_once(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, carer, viewer = [await make_user(owner_engine) for _ in range(3)]
    patient = await make_patient(app_engine, owner)
    ids = await _seed(app_engine, owner, patient)
    await grant(app_engine, owner, patient, carer, "caregiver")
    await grant(app_engine, owner, patient, viewer, "viewer")
    future = await _future_regimen(app_engine, owner, patient, ids["medications"])
    void = bound_text(
        "update medication_regimens set voided_at = now(), void_reason = 'он буруу' where id = :i"
    )
    stranger = await make_user(owner_engine)
    for reader in (viewer, stranger):
        async with as_user(app_engine, reader) as conn:
            assert (await conn.execute(void, {"i": future})).rowcount == 0
    async with as_user(app_engine, carer) as conn:
        assert (await conn.execute(void, {"i": future})).rowcount == 1
        row = (
            await conn.execute(
                bound_text("select voided_by, void_reason from medication_regimens where id = :i"),
                {"i": future},
            )
        ).one()
    assert (row.voided_by, row.void_reason) == (carer, "он буруу")
    with pytest.raises(DBAPIError, match="a voided dose stays voided"):
        async with as_user(app_engine, owner) as conn:
            await conn.execute(
                bound_text("update medication_regimens set void_reason = 'x' where id = :i"),
                {"i": future},
            )
    # a started dose is history: never voided
    with pytest.raises(DBAPIError, match="a started dose is history"):
        async with as_user(app_engine, owner) as conn:
            await conn.execute(void, {"i": ids["medication_regimens"]})
    # nothing else of a regimen changes
    with pytest.raises(DBAPIError, match="permission denied"):
        async with as_user(app_engine, owner) as conn:
            await conn.execute(
                bound_text(
                    "update medication_regimens set effective_from = '2026-01-02' where id = :i"
                ),
                {"i": future},
            )


async def test_a_scheduled_dose_is_a_whole_minute(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    ids = await _seed(app_engine, owner, patient)
    with pytest.raises(DBAPIError, match="check constraint"):
        async with as_user(app_engine, owner) as conn:
            await conn.execute(
                _INTAKE,
                {
                    "p": patient,
                    "m": ids["medications"],
                    "c": _cid(),
                    "at": datetime(2026, 11, 1, 8, 0, 30, tzinfo=UTC),
                },
            )


async def test_no_user_context_and_admin_roles_see_nothing(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    admin_engine: AsyncEngine,
    admin_login_engine: AsyncEngine,
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    await _seed(app_engine, owner, patient)
    # a worker transaction that forgot set_config, or a pooled connection after a user's
    # transaction ended (is_local), sees nothing
    assert await _counts(app_engine, None, patient) == [0, 0, 0, 0]
    for engine in (admin_engine, admin_login_engine):
        for table in TABLES:
            with pytest.raises(DBAPIError, match="permission denied"):
                async with engine.connect() as conn:
                    await conn.execute(bound_text(f"select count(*) from {table}"))  # noqa: S608


async def test_partial_dates_are_stored_as_their_first_day(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    insert = bound_text(
        "insert into transplants (patient_id, client_id, organ, transplant_date, date_precision,"
        " country, hospital) values (:p, gen_random_uuid(), 'liver', :d, :prec, 'KR', 'Asan')"
    )
    async with as_user(app_engine, owner) as conn:
        await conn.execute(insert, {"p": patient, "d": date(2019, 5, 1), "prec": "month"})
        await conn.execute(insert, {"p": patient, "d": date(2015, 1, 1), "prec": "year"})
    for d, prec in ((date(2019, 5, 14), "month"), (date(2015, 5, 1), "year")):
        with pytest.raises(DBAPIError, match="check constraint"):
            async with as_user(app_engine, owner) as conn:
                await conn.execute(insert, {"p": patient, "d": d, "prec": prec})


async def test_purging_an_account_erases_its_medications(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, maint_engine: AsyncEngine
) -> None:
    """The 30-day purge removes the profile and, through the FK cascade, every row here."""
    leaving = await make_user(owner_engine)
    patient = await make_patient(app_engine, leaving)
    await _seed(app_engine, leaving, patient)
    await _request(app_engine, leaving)
    await _age(owner_engine, leaving, 31)
    assert leaving in await _purge(maint_engine)
    async with owner_engine.connect() as conn:
        for table in TABLES:
            n = await scalar(
                conn,
                bound_text(f"select count(*) from {table} where patient_id = :p"),  # noqa: S608
                {"p": patient},
            )
            assert n == 0, table


async def test_purging_a_caregiver_keeps_what_they_recorded_for_others(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, maint_engine: AsyncEngine
) -> None:
    owner, carer = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    ids = await _seed(app_engine, owner, patient)
    await grant(app_engine, owner, patient, carer, "caregiver")
    async with as_user(app_engine, carer) as conn:
        intake = await scalar(
            conn,
            _INTAKE,
            {
                "p": patient,
                "m": ids["medications"],
                "c": _cid(),
                "at": datetime(2026, 11, 4, 0, 0, tzinfo=UTC),
            },
        )
    await _request(app_engine, carer)
    await _age(owner_engine, carer, 31)
    assert carer in await _purge(maint_engine)
    async with owner_engine.connect() as conn:
        by = await scalar(
            conn,
            bound_text("select recorded_by from medication_intakes where id = :i"),
            {"i": intake},
        )
    assert by is None  # the dose stays in the patient's record; the writer is gone


async def test_a_taken_dose_is_deleted_only_by_its_recorder_or_the_owner(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, carer, carer2 = [await make_user(owner_engine) for _ in range(3)]
    patient = await make_patient(app_engine, owner)
    ids = await _seed(app_engine, owner, patient)
    for c in (carer, carer2):
        await grant(app_engine, owner, patient, c, "caregiver")
    async with as_user(app_engine, carer) as conn:
        mine = await scalar(
            conn,
            _INTAKE,
            {
                "p": patient,
                "m": ids["medications"],
                "c": _cid(),
                "at": datetime(2026, 11, 5, 0, 0, tzinfo=UTC),
            },
        )
    delete = bound_text("delete from medication_intakes where id = :i")
    async with as_user(app_engine, carer2) as conn:
        for intake in (mine, ids["medication_intakes"]):
            assert (await conn.execute(delete, {"i": intake})).rowcount == 0
    async with as_user(app_engine, carer) as conn:  # one's own tap, undone
        assert (await conn.execute(delete, {"i": mine})).rowcount == 1
    async with as_user(app_engine, owner) as conn:
        assert (await conn.execute(delete, {"i": ids["medication_intakes"]})).rowcount == 1


async def test_who_changed_a_medication_is_kept(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, carer = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    ids = await _seed(app_engine, owner, patient)
    await grant(app_engine, owner, patient, carer, "caregiver")
    async with as_user(app_engine, carer) as conn:
        await conn.execute(
            bound_text("update medications set strength = '0.5 мг' where id = :i"),
            {"i": ids["medications"]},
        )
        row = (
            await conn.execute(
                bound_text("select recorded_by, updated_by from medications where id = :i"),
                {"i": ids["medications"]},
            )
        ).one()
    assert (row.recorded_by, row.updated_by) == (owner, carer)


async def test_deleting_a_user_inside_a_user_context_keeps_rows(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    """The FK set-null a user's deletion triggers is the database's own update: the writer
    trigger leaves it alone even when app.user_id is set in that transaction."""
    owner, carer = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    ids = await _seed(app_engine, owner, patient)
    await grant(app_engine, owner, patient, carer, "caregiver")
    async with as_user(app_engine, carer) as conn:
        intake = await scalar(
            conn,
            _INTAKE,
            {
                "p": patient,
                "m": ids["medications"],
                "c": _cid(),
                "at": datetime(2026, 11, 6, 0, 0, tzinfo=UTC),
            },
        )
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text("select set_config('app.user_id', :u, true)"), {"u": str(owner)}
        )
        await conn.execute(bound_text("delete from users where id = :u"), {"u": carer})
        row = (
            await conn.execute(
                bound_text("select recorded_by, updated_by from medication_intakes where id = :i"),
                {"i": intake},
            )
        ).one()
    assert (row.recorded_by, row.updated_by) == (None, None)


async def test_purging_whoever_voided_a_dose_keeps_the_mark(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, maint_engine: AsyncEngine
) -> None:
    """The purge's FK set null on voided_by/recorded_by passes the void trigger; the row stays
    voided (a voided mistake never comes back into force)."""
    owner, carer = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    ids = await _seed(app_engine, owner, patient)
    await grant(app_engine, owner, patient, carer, "caregiver")
    future = await _future_regimen(app_engine, carer, patient, ids["medications"])
    async with as_user(app_engine, carer) as conn:
        await conn.execute(
            bound_text(
                "update medication_regimens set voided_at = now(), void_reason = 'алдаа'"
                " where id = :i"
            ),
            {"i": future},
        )
    await _request(app_engine, carer)
    await _age(owner_engine, carer, 31)
    assert carer in await _purge(maint_engine)
    async with owner_engine.connect() as conn:
        row = (
            await conn.execute(
                bound_text(
                    "select recorded_by, voided_by, voided_at from medication_regimens"
                    " where id = :i"
                ),
                {"i": future},
            )
        ).one()
    assert (row.recorded_by, row.voided_by) == (None, None)
    assert row.voided_at is not None


async def test_even_the_owner_role_only_voids(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    ids = await _seed(app_engine, owner, patient)
    with pytest.raises(DBAPIError, match="only voiding is allowed"):
        async with owner_engine.connect() as conn, conn.begin():
            await conn.execute(
                bound_text("update medication_regimens set changed_by_note = 'x' where id = :i"),
                {"i": ids["medication_regimens"]},
            )
