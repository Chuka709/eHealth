"""Sharing by username with a doctor or a viewer (0040; Phase 7.1, H36): only an accepted
invitation gives access, read-only and for the chosen time; who opened it is the owner's to see."""

from uuid import UUID

import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.db.sql import bound_text

from .conftest import as_user, make_patient, make_user, scalar
from .test_caregivers import _username

pytestmark = pytest.mark.db


async def _invite(
    app_engine: AsyncEngine, owner: UUID, patient: UUID, name: str, level: str, days: int | None
) -> UUID | None:
    async with as_user(app_engine, owner) as conn:
        inv: UUID | None = await scalar(
            conn,
            bound_text("select invite_access(:p, :u, :l, :d)"),
            {"p": patient, "u": name, "l": level, "d": days},
        )
    return inv


async def _respond(app_engine: AsyncEngine, user: UUID, inv: UUID, accept: bool) -> bool:
    async with as_user(app_engine, user) as conn:
        done: bool = await scalar(
            conn, bound_text("select respond_access_invitation(:i, :a)"), {"i": inv, "a": accept}
        )
    return done


async def _reads(app_engine: AsyncEngine, user: UUID | None, patient: UUID) -> tuple[bool, bool]:
    async with as_user(app_engine, user) as conn:
        row = (
            await conn.execute(
                bound_text("select can_read_patient(:p) as r, can_write_patient(:p) as w"),
                {"p": patient},
            )
        ).one()
    return bool(row.r), bool(row.w)


async def _setup(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> tuple[UUID, UUID, UUID, str]:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    doctor = await make_user(owner_engine, "doctor")
    return owner, patient, doctor, await _username(owner_engine, doctor)


async def test_access_starts_only_on_acceptance_read_only_and_timed(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, patient, doctor, name = await _setup(app_engine, owner_engine)
    inv = await _invite(app_engine, owner, patient, name, "doctor", 7)
    assert inv is not None
    assert await _reads(app_engine, doctor, patient) == (False, False)  # not before accepting
    assert await _respond(app_engine, doctor, inv, True)
    assert await _reads(app_engine, doctor, patient) == (True, False)  # read-only
    async with owner_engine.connect() as conn:
        days = await scalar(
            conn,
            bound_text(
                "select round(extract(epoch from expires_at - now()) / 86400)"
                " from patient_access where patient_id = :p and user_id = :u"
            ),
            {"p": patient, "u": doctor},
        )
    assert int(days) == 7
    # the same invitation cannot be answered twice
    assert not await _respond(app_engine, doctor, inv, True)


async def test_until_revoked_then_revoked_and_left(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, patient, doctor, name = await _setup(app_engine, owner_engine)
    inv = await _invite(app_engine, owner, patient, name, "viewer", None)
    assert inv is not None
    assert await _respond(app_engine, doctor, inv, True)
    async with as_user(app_engine, owner) as conn:
        [share] = (
            await conn.execute(bound_text("select * from owner_shares(:p)"), {"p": patient})
        ).all()
        assert (share.user_id, share.level, share.expires_at) == (doctor, "viewer", None)
        assert await scalar(
            conn, bound_text("select revoke_share(:p, :u)"), {"p": patient, "u": doctor}
        )
    assert await _reads(app_engine, doctor, patient) == (False, False)
    # invited again and accepted, then the viewer leaves on their own
    inv = await _invite(app_engine, owner, patient, name, "viewer", 1)
    assert inv is not None
    assert await _respond(app_engine, doctor, inv, True)
    async with as_user(app_engine, doctor) as conn:
        assert await scalar(conn, bound_text("select leave_share(:p)"), {"p": patient})
    assert await _reads(app_engine, doctor, patient) == (False, False)


async def test_nobody_but_the_owner_invites_or_manages(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, patient, doctor, name = await _setup(app_engine, owner_engine)
    stranger = await make_user(owner_engine)
    for user in (stranger, doctor, None):
        async with as_user(app_engine, user) as conn:
            with pytest.raises(DBAPIError):
                await conn.execute(
                    bound_text("select invite_access(:p, :u, 'doctor', 7)"),
                    {"p": patient, "u": name},
                )
    inv = await _invite(app_engine, owner, patient, name, "doctor", 30)
    assert inv is not None
    async with as_user(app_engine, stranger) as conn:
        assert (
            await conn.execute(bound_text("select * from owner_shares(:p)"), {"p": patient})
        ).all() == []
        assert (
            await conn.execute(
                bound_text("select * from owner_access_invitations(:p)"), {"p": patient}
            )
        ).all() == []
        assert (
            await conn.execute(bound_text("select * from owner_profile_views(:p)"), {"p": patient})
        ).all() == []
        assert not await scalar(conn, bound_text("select revoke_access_invitation(:i)"), {"i": inv})
        assert (await conn.execute(bound_text("select id from access_invitations"))).all() == []
        assert (await conn.execute(bound_text("select * from my_access_invitations()"))).all() == []
        # someone else cannot answer the doctor's invitation
        assert not await scalar(
            conn, bound_text("select respond_access_invitation(:i, true)"), {"i": inv}
        )
    assert await _reads(app_engine, stranger, patient) == (False, False)
    # no level beyond read-only, no other durations
    async with as_user(app_engine, owner) as conn:
        for level, days in (("caregiver", 7), ("owner", 7), ("doctor", 3)):
            with pytest.raises(DBAPIError):
                await conn.execute(
                    bound_text("select invite_access(:p, :u, :l, :d)"),
                    {"p": patient, "u": name, "l": level, "d": days},
                )


async def test_unknown_names_declines_and_a_caregiver_meanwhile(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, patient, doctor, name = await _setup(app_engine, owner_engine)
    assert await _invite(app_engine, owner, patient, "nobody.here", "doctor", 7) is None
    inv = await _invite(app_engine, owner, patient, name, "doctor", 7)
    assert inv is not None
    assert await _respond(app_engine, doctor, inv, False)
    # declined in the last 30 days: nothing new
    assert await _invite(app_engine, owner, patient, name, "doctor", 7) is None
    assert await _reads(app_engine, doctor, patient) == (False, False)


async def test_views_are_noted_for_doctors_and_viewers_only_and_shown_to_the_owner(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, patient, doctor, name = await _setup(app_engine, owner_engine)
    stranger = await make_user(owner_engine)
    inv = await _invite(app_engine, owner, patient, name, "doctor", 7)
    assert inv is not None
    assert await _respond(app_engine, doctor, inv, True)
    for user in (doctor, doctor, owner, stranger):
        async with as_user(app_engine, user) as conn:
            await conn.execute(bound_text("select note_profile_view(:p)"), {"p": patient})
    async with as_user(app_engine, owner) as conn:
        rows = (
            await conn.execute(bound_text("select * from owner_profile_views(:p)"), {"p": patient})
        ).all()
        [share] = (
            await conn.execute(bound_text("select * from owner_shares(:p)"), {"p": patient})
        ).all()
    assert [r.user_id for r in rows] == [doctor]  # one row a day; not the owner, not a stranger
    assert rows[0].first_at <= rows[0].last_at
    assert share.last_viewed_at == rows[0].last_at
    # nobody reads or writes the table directly
    for user in (owner, doctor):
        async with as_user(app_engine, user) as conn:
            with pytest.raises(DBAPIError):
                await conn.execute(bound_text("select * from profile_views"))


async def test_the_owner_cannot_grant_change_extend_or_drop_a_share_directly(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, patient, doctor, name = await _setup(app_engine, owner_engine)
    inv = await _invite(app_engine, owner, patient, name, "viewer", 1)
    assert inv is not None
    assert await _respond(app_engine, doctor, inv, True)
    other = await make_user(owner_engine)
    for sql in (
        "update patient_access set level = 'doctor' where patient_id = :p and user_id = :u",
        "update patient_access set expires_at = null where patient_id = :p and user_id = :u",
        "delete from patient_access where patient_id = :p and user_id = :u",
        "insert into patient_access (patient_id, user_id, level) values (:p, :s, 'viewer')",
    ):
        async with as_user(app_engine, owner) as conn:
            with pytest.raises(DBAPIError):
                await conn.execute(bound_text(sql), {"p": patient, "u": doctor, "s": other})
    assert await _reads(app_engine, doctor, patient) == (True, False)
