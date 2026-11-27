"""RLS for patient_timezones (0017; phi-table; Q22, H7)."""

from datetime import UTC, datetime, timedelta
from typing import LiteralString
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.db.sql import bound_text

from .conftest import as_user, grant, make_patient, make_user, scalar
from .test_account_deletion import _age, _purge, _request

pytestmark = pytest.mark.db

_INSERT = bound_text(
    "insert into patient_timezones (patient_id, client_id, timezone, effective_at)"
    " values (:p, :c, :tz, :at) returning id"
)
_COUNT = bound_text("select count(*) from patient_timezones where patient_id = :p")
_AT = datetime.now(UTC) - timedelta(hours=1)


async def _switch(
    app_engine: AsyncEngine, user: UUID, patient: UUID, tz: str = "Asia/Seoul"
) -> UUID:
    async with as_user(app_engine, user) as conn:
        row: UUID = await scalar(conn, _INSERT, {"p": patient, "c": uuid4(), "tz": tz, "at": _AT})
    return row


async def _count(app_engine: AsyncEngine, user: UUID | None, patient: UUID) -> int:
    async with as_user(app_engine, user) as conn:
        n: int = await scalar(conn, _COUNT, {"p": patient})
    return n


async def test_owner_switches_and_the_history_is_append_only(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    row = await _switch(app_engine, owner, patient)
    await _switch(app_engine, owner, patient, "Asia/Ulaanbaatar")
    assert await _count(app_engine, owner, patient) == 2
    for sql in (
        "update patient_timezones set timezone = 'Asia/Tokyo' where id = :i",
        "delete from patient_timezones where id = :i",
        "truncate patient_timezones",
    ):
        with pytest.raises(DBAPIError, match="permission denied"):
            async with as_user(app_engine, owner) as conn:
                await conn.execute(bound_text(sql), {"i": row})


async def test_identity_columns_belong_to_the_database(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, other = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    head: LiteralString = (
        "insert into patient_timezones (patient_id, client_id, timezone, effective_at, "
    )
    tail: LiteralString = ") values (:p, :c, 'Asia/Seoul', :at, :v)"
    cases: tuple[tuple[LiteralString, object], ...] = (
        (head + "id" + tail, uuid4()),
        (head + "recorded_by" + tail, other),
        (head + "created_at" + tail, _AT),
    )
    for sql, value in cases:
        with pytest.raises(DBAPIError, match="permission denied"):
            async with as_user(app_engine, owner) as conn:
                await conn.execute(
                    bound_text(sql), {"p": patient, "c": uuid4(), "at": _AT, "v": value}
                )
    await _switch(app_engine, owner, patient)
    async with owner_engine.connect() as conn:
        writer = await scalar(
            conn,
            bound_text("select recorded_by from patient_timezones where patient_id = :p"),
            {"p": patient},
        )
    assert writer == owner


async def test_a_retried_switch_is_one_row(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    params = {"p": patient, "c": uuid4(), "tz": "Asia/Seoul", "at": _AT}
    async with as_user(app_engine, owner) as conn:
        await conn.execute(_INSERT, params)
    with pytest.raises(DBAPIError, match="unique"):
        async with as_user(app_engine, owner) as conn:
            await conn.execute(_INSERT, params)


@pytest.mark.parametrize(
    "tz", ["", "Asia/Seoul; drop", "../etc/passwd", "a" * 65, "Asia/Seoul/X/Y", "/Asia"]
)
async def test_zone_shape_is_checked(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, tz: str
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    with pytest.raises(DBAPIError, match="check constraint"):
        await _switch(app_engine, owner, patient, tz)


async def test_ancient_dates_are_refused(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    with pytest.raises(DBAPIError, match="check constraint"):
        async with as_user(app_engine, owner) as conn:
            await conn.execute(
                _INSERT,
                {
                    "p": patient,
                    "c": uuid4(),
                    "tz": "Asia/Seoul",
                    "at": datetime(2019, 1, 1, tzinfo=UTC),
                },
            )


@pytest.mark.parametrize("offset", [timedelta(days=8), timedelta(minutes=-30)])
async def test_a_switch_is_at_most_a_week_late_and_never_ahead(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, offset: timedelta
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    with pytest.raises(DBAPIError, match="check constraint"):
        async with as_user(app_engine, owner) as conn:
            await conn.execute(
                _INSERT,
                {"p": patient, "c": uuid4(), "tz": "Asia/Seoul", "at": datetime.now(UTC) - offset},
            )


async def test_stranger_sees_and_writes_nothing(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, stranger = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    await _switch(app_engine, owner, patient)
    assert await _count(app_engine, stranger, patient) == 0
    with pytest.raises(DBAPIError, match="row-level security"):
        await _switch(app_engine, stranger, patient)


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
    await _switch(app_engine, owner, patient)
    await grant(app_engine, owner, patient, doctor, "doctor", expires=expires, revoked=revoked)
    assert await _count(app_engine, doctor, patient) == visible


@pytest.mark.parametrize("level", ["doctor", "viewer"])
async def test_readers_cannot_switch(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, level: str
) -> None:
    owner, reader = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    await grant(app_engine, owner, patient, reader, level)
    with pytest.raises(DBAPIError, match="row-level security"):
        await _switch(app_engine, reader, patient)


async def test_caregiver_switches_and_is_recorded(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, carer = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    await grant(app_engine, owner, patient, carer, "caregiver")
    await _switch(app_engine, carer, patient)
    async with owner_engine.connect() as conn:
        writer = await scalar(
            conn,
            bound_text("select recorded_by from patient_timezones where patient_id = :p"),
            {"p": patient},
        )
    assert writer == carer


async def test_no_user_context_and_admin_roles_see_nothing(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    admin_engine: AsyncEngine,
    admin_login_engine: AsyncEngine,
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    await _switch(app_engine, owner, patient)
    assert await _count(app_engine, None, patient) == 0
    for engine in (admin_engine, admin_login_engine):
        with pytest.raises(DBAPIError, match="permission denied"):
            async with engine.connect() as conn:
                await conn.execute(bound_text("select count(*) from patient_timezones"))


async def test_purging_an_account_erases_its_zones(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, maint_engine: AsyncEngine
) -> None:
    leaving = await make_user(owner_engine)
    patient = await make_patient(app_engine, leaving)
    await _switch(app_engine, leaving, patient)
    await _request(app_engine, leaving)
    await _age(owner_engine, leaving, 31)
    assert leaving in await _purge(maint_engine)
    async with owner_engine.connect() as conn:
        assert await scalar(conn, _COUNT, {"p": patient}) == 0


async def test_purging_a_caregiver_keeps_their_switch(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, maint_engine: AsyncEngine
) -> None:
    owner, carer = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    await grant(app_engine, owner, patient, carer, "caregiver")
    await _switch(app_engine, carer, patient)
    await _request(app_engine, carer)
    await _age(owner_engine, carer, 31)
    assert carer in await _purge(maint_engine)
    async with owner_engine.connect() as conn:
        writer = await scalar(
            conn,
            bound_text("select recorded_by from patient_timezones where patient_id = :p"),
            {"p": patient},
        )
    assert writer is None
    assert await _count(app_engine, owner, patient) == 1
