"""A doctor's targets and notes (0043; Phase 7.4, H15): written only by a registered doctor
with live doctor access, read by whoever reads the profile, nothing for anyone else."""

from datetime import date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.db.sql import bound_text

from .conftest import as_user, grant, make_patient, make_user, scalar
from .test_dashboard import seeded  # noqa: F401 - the catalog (autouse)

pytestmark = pytest.mark.db


def _today() -> date:
    """Ulaanbaatar's day, as the database's local_today() reads it."""
    return datetime.now(ZoneInfo("Asia/Ulaanbaatar")).date()


_TARGET = bound_text("select set_patient_target(:p, 'TAC', 5, 8, :f, 'trough')")
_NOTE = bound_text("select add_doctor_note(:p, 'Check trough in 2 weeks')")


async def _shared(app_engine: AsyncEngine, owner_engine: AsyncEngine) -> tuple[UUID, UUID, UUID]:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    doctor = await make_user(owner_engine, "doctor")
    await grant(app_engine, owner, patient, doctor, "doctor")
    return owner, patient, doctor


async def test_a_treating_doctor_writes_and_every_reader_sees(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, patient, doctor = await _shared(app_engine, owner_engine)
    viewer = await make_user(owner_engine)
    await grant(app_engine, owner, patient, viewer, "viewer")
    async with as_user(app_engine, doctor) as conn:
        await conn.execute(_TARGET, {"p": patient, "f": _today()})
        await conn.execute(_NOTE, {"p": patient})
        # a new target ends the one before
        await conn.execute(
            bound_text("select set_patient_target(:p, 'TAC', 4, 6, :f, null)"),
            {"p": patient, "f": _today() + timedelta(days=30)},
        )
    for reader in (owner, viewer, doctor):
        async with as_user(app_engine, reader) as conn:
            rows = (
                await conn.execute(bound_text("select * from profile_targets(:p)"), {"p": patient})
            ).all()
            assert [(r.valid_from, r.valid_to) for r in rows] == [
                (_today() + timedelta(days=30), None),
                (_today(), _today() + timedelta(days=29)),
            ]
            assert rows[0].unit == "ng/mL"
            [note] = (
                await conn.execute(
                    bound_text("select * from profile_doctor_notes(:p)"), {"p": patient}
                )
            ).all()
            assert note.mine == (reader == doctor)


async def test_nobody_else_writes(app_engine: AsyncEngine, owner_engine: AsyncEngine) -> None:
    owner, patient, _ = await _shared(app_engine, owner_engine)
    carer, viewer, stranger = [await make_user(owner_engine) for _ in range(3)]
    await grant(app_engine, owner, patient, carer, "caregiver")
    await grant(app_engine, owner, patient, viewer, "viewer")
    # 'doctor' access held by an account that is not a registered doctor (Q61 f)
    not_md = await make_user(owner_engine)
    await grant(app_engine, owner, patient, not_md, "doctor")
    doctor_elsewhere = await make_user(owner_engine, "doctor")
    for user in (owner, carer, viewer, stranger, not_md, doctor_elsewhere, None):
        async with as_user(app_engine, user) as conn:
            with pytest.raises(DBAPIError):
                await conn.execute(_TARGET, {"p": patient, "f": date(2026, 1, 1)})
        async with as_user(app_engine, user) as conn:
            with pytest.raises(DBAPIError):
                await conn.execute(_NOTE, {"p": patient})
        async with as_user(app_engine, user) as conn:
            for table in ("patient_targets", "doctor_notes"):
                with pytest.raises(DBAPIError):
                    await conn.execute(
                        bound_text(f"insert into {table} (patient_id) values (:p)"),  # noqa: S608
                        {"p": patient},
                    )
    async with as_user(app_engine, stranger) as conn:
        assert (
            await conn.execute(bound_text("select * from profile_targets(:p)"), {"p": patient})
        ).all() == []
        assert await scalar(conn, bound_text("select count(*) from doctor_notes")) == 0


async def test_only_the_author_removes_a_note_and_a_revoked_doctor_writes_nothing(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, patient, doctor = await _shared(app_engine, owner_engine)
    async with as_user(app_engine, doctor) as conn:
        note = await scalar(conn, _NOTE, {"p": patient})
    async with as_user(app_engine, owner) as conn:
        assert not await scalar(conn, bound_text("select remove_doctor_note(:n)"), {"n": note})
        assert await scalar(
            conn, bound_text("select revoke_share(:p, :u)"), {"p": patient, "u": doctor}
        )
    async with as_user(app_engine, doctor) as conn:
        with pytest.raises(DBAPIError):
            await conn.execute(_NOTE, {"p": patient})
    async with as_user(app_engine, doctor) as conn:
        assert not await scalar(conn, bound_text("select remove_doctor_note(:n)"), {"n": note})


async def test_no_doctor_writes_on_a_minors_profile(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    child = await make_patient(app_engine, owner, minor=True)
    doctor = await make_user(owner_engine, "doctor")
    await grant(app_engine, owner, child, doctor, "doctor")
    async with as_user(app_engine, doctor) as conn:
        with pytest.raises(DBAPIError):
            await conn.execute(_NOTE, {"p": child})


async def test_ending_a_target_and_direct_writes(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, patient, doctor = await _shared(app_engine, owner_engine)
    today = _today()
    async with as_user(app_engine, doctor) as conn:
        target = await scalar(conn, _TARGET, {"p": patient, "f": today})
        await conn.execute(_NOTE, {"p": patient})
    other_md = await make_user(owner_engine, "doctor")
    carer = await make_user(owner_engine)
    await grant(app_engine, owner, patient, carer, "caregiver")
    end = bound_text("select end_patient_target(:t, :o)")
    for user in (owner, carer, other_md, None):
        async with as_user(app_engine, user) as conn:
            assert not await scalar(conn, end, {"t": target, "o": today})
    async with as_user(app_engine, doctor) as conn:
        for sql in ("update patient_targets set low = 0", "delete from doctor_notes"):
            with pytest.raises(DBAPIError):
                await conn.execute(bound_text(sql))
    async with as_user(app_engine, doctor) as conn:
        # a target never rewrites the days already shown
        with pytest.raises(DBAPIError):
            await conn.execute(_TARGET, {"p": patient, "f": date(2020, 1, 1)})
    async with as_user(app_engine, doctor) as conn:
        assert await scalar(conn, end, {"t": target, "o": today})
    # a removed author: the note stays readable, never "mine", no name
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text("update doctor_notes set author_id = null where patient_id = :p"),
            {"p": patient},
        )
    async with as_user(app_engine, owner) as conn:
        [note] = (
            await conn.execute(bound_text("select * from profile_doctor_notes(:p)"), {"p": patient})
        ).all()
    assert (note.mine, note.author_name) == (False, None)
