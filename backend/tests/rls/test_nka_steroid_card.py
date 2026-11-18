"""A confirmed "no known allergies" and the steroid emergency card mark (0048; Q39, Q36; H17,
H28): written only through their functions, by the right people, read by whoever reads the
profile, nothing for anyone else."""

from datetime import datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.db.sql import bound_text

from .conftest import as_user, grant, make_patient, make_user, scalar

pytestmark = pytest.mark.db

_CONFIRM = bound_text("select confirm_no_known_allergies(:p)")
_CLEAR = bound_text("select clear_no_known_allergies(:p)")
_NKA = bound_text("select count(*) from no_known_allergies where patient_id = :p")
_ALLERGY = bound_text(
    "insert into allergies (patient_id, client_id, substance) values (:p, :c, 'Penicillin')"
)
_MARK = bound_text("select set_steroid_card(:p, :on)")
_CARD = bound_text("select * from profile_steroid_card(:p)")


async def _profile(app_engine: AsyncEngine, owner_engine: AsyncEngine) -> tuple[UUID, UUID]:
    owner = await make_user(owner_engine)
    return owner, await make_patient(app_engine, owner)


# --- no known allergies ------------------------------------------------------------------


async def test_confirmed_today_and_ended_by_an_allergy(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, patient = await _profile(app_engine, owner_engine)
    async with as_user(app_engine, owner) as conn:
        day = await scalar(conn, _CONFIRM, {"p": patient})
        assert day == datetime.now(ZoneInfo("Asia/Ulaanbaatar")).date()
        assert await scalar(conn, _NKA, {"p": patient}) == 1
        await conn.execute(_ALLERGY, {"p": patient, "c": uuid4()})
        # the two are never stored together; the ending is audited (ids only)
        assert await scalar(conn, _NKA, {"p": patient}) == 0
    async with owner_engine.connect() as conn:
        actions = (
            (
                await conn.execute(
                    bound_text("select action from audit_logs where patient_id = :p"),
                    {"p": patient},
                )
            )
            .scalars()
            .all()
        )
    assert {"allergy.none_confirmed", "allergy.none_ended"} <= set(actions)
    async with as_user(app_engine, owner) as conn:
        with pytest.raises(DBAPIError):  # refused while an allergy is recorded
            await conn.execute(_CONFIRM, {"p": patient})


async def test_a_writer_confirms_and_clears_and_nobody_else(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, patient = await _profile(app_engine, owner_engine)
    carer, viewer, doctor, stranger = [await make_user(owner_engine) for _ in range(4)]
    await grant(app_engine, owner, patient, carer, "caregiver")
    await grant(app_engine, owner, patient, viewer, "viewer")
    await grant(app_engine, owner, patient, doctor, "doctor")
    expired, revoked = await make_user(owner_engine), await make_user(owner_engine)
    await grant(
        app_engine, owner, patient, expired, "caregiver",
        expires=datetime.now(ZoneInfo("UTC")) - timedelta(days=1),
    )  # fmt: skip
    await grant(app_engine, owner, patient, revoked, "caregiver", revoked=True)
    async with as_user(app_engine, carer) as conn:
        await conn.execute(_CONFIRM, {"p": patient})
    for user in (viewer, doctor, stranger, expired, revoked, None):
        for sql in (_CONFIRM, _CLEAR):
            async with as_user(app_engine, user) as conn:
                with pytest.raises(DBAPIError):
                    await conn.execute(sql, {"p": patient})
        async with as_user(app_engine, user) as conn:
            for direct in (
                "insert into no_known_allergies (patient_id, confirmed_on) values (:p, now())",
                "delete from no_known_allergies where patient_id = :p",
            ):
                with pytest.raises(DBAPIError):
                    async with conn.begin_nested():
                        await conn.execute(bound_text(direct), {"p": patient})
    for user in (stranger, expired, revoked, None):
        async with as_user(app_engine, user) as conn:
            assert await scalar(conn, _NKA, {"p": patient}) == 0
    for user in (owner, viewer, doctor):
        async with as_user(app_engine, user) as conn:
            assert await scalar(conn, _NKA, {"p": patient}) == 1
    async with as_user(app_engine, owner) as conn:
        assert await scalar(conn, _CLEAR, {"p": patient})
        assert not await scalar(conn, _CLEAR, {"p": patient})


# --- the steroid emergency card ----------------------------------------------------------


async def test_a_treating_doctor_or_the_owner_marks_it(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, patient = await _profile(app_engine, owner_engine)
    doctor = await make_user(owner_engine, "doctor")
    await grant(app_engine, owner, patient, doctor, "doctor")
    async with as_user(app_engine, owner) as conn:
        assert await scalar(conn, _MARK, {"p": patient, "on": True})
        [card] = (await conn.execute(_CARD, {"p": patient})).all()
        assert (card.by_doctor, card.doctor_name) == (False, None)
    async with as_user(app_engine, doctor) as conn:
        await conn.execute(_MARK, {"p": patient, "on": True})
    async with as_user(app_engine, owner) as conn:
        # the owner's own mark never replaces the doctor's (and is not audited as a change)
        assert not await scalar(conn, _MARK, {"p": patient, "on": True})
        [card] = (await conn.execute(_CARD, {"p": patient})).all()
        assert (card.by_doctor, card.doctor_name) == (True, "Test")
        assert await scalar(conn, _MARK, {"p": patient, "on": False})
        assert not await scalar(conn, _MARK, {"p": patient, "on": False})
    async with as_user(app_engine, doctor) as conn:
        await conn.execute(_MARK, {"p": patient, "on": True})
        assert await scalar(conn, _MARK, {"p": patient, "on": False})


async def test_nobody_else_marks_it(app_engine: AsyncEngine, owner_engine: AsyncEngine) -> None:
    owner, patient = await _profile(app_engine, owner_engine)
    carer, viewer, stranger = [await make_user(owner_engine) for _ in range(3)]
    await grant(app_engine, owner, patient, carer, "caregiver")
    await grant(app_engine, owner, patient, viewer, "viewer")
    not_md = await make_user(owner_engine)  # doctor access, not a registered doctor
    await grant(app_engine, owner, patient, not_md, "doctor")
    revoked_md = await make_user(owner_engine, "doctor")
    await grant(app_engine, owner, patient, revoked_md, "doctor", revoked=True)
    async with as_user(app_engine, owner) as conn:
        await conn.execute(_MARK, {"p": patient, "on": True})
    for user in (carer, viewer, stranger, not_md, revoked_md, None):
        for on in (True, False):
            async with as_user(app_engine, user) as conn:
                with pytest.raises(DBAPIError):
                    await conn.execute(_MARK, {"p": patient, "on": on})
        async with as_user(app_engine, user) as conn:
            with pytest.raises(DBAPIError):
                async with conn.begin_nested():
                    await conn.execute(bound_text("delete from steroid_cards"))
            rows = (await conn.execute(_CARD, {"p": patient})).all()
            seen = await scalar(conn, bound_text("select count(*) from steroid_cards"))
        readable = user in (carer, viewer, not_md)
        assert (len(rows), seen) == ((1, 1) if readable else (0, 0)), user


async def test_no_doctor_marks_a_minors_profile(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    child = await make_patient(app_engine, owner, minor=True)
    doctor = await make_user(owner_engine, "doctor")
    await grant(app_engine, owner, child, doctor, "doctor")
    async with as_user(app_engine, doctor) as conn:
        with pytest.raises(DBAPIError):
            await conn.execute(_MARK, {"p": child, "on": True})
    async with as_user(app_engine, owner) as conn:
        assert await scalar(conn, _MARK, {"p": child, "on": True})


async def test_the_share_function_reads_nothing_without_a_live_session(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, patient = await _profile(app_engine, owner_engine)
    async with as_user(app_engine, owner) as conn:
        await conn.execute(_CONFIRM, {"p": patient})
        # a signed-in user is never a share session
        assert await scalar(conn, bound_text("select share_no_known_allergies('x')")) is None
    async with as_user(app_engine, None) as conn:
        assert await scalar(conn, bound_text("select share_no_known_allergies('x')")) is None
