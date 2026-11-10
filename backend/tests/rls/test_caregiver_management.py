"""The owner's caregiver functions and the child's-profile rule (0025; H16, H20)."""

import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.db.sql import bound_text

from .conftest import as_user, make_patient, make_user, scalar
from .test_caregivers import _caregiver, _consent, _family, _invite, _username

pytestmark = pytest.mark.db


async def test_only_the_owner_sees_the_caregivers_and_open_invitations(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, carer, patient = await _caregiver(app_engine, owner_engine)
    invited = await make_user(owner_engine)
    invited_name = await _username(owner_engine, invited)
    await _invite(app_engine, owner, patient, invited_name)
    async with as_user(app_engine, carer) as conn:
        await conn.execute(bound_text("select set_caregiver_alerts(:p, 60, true)"), {"p": patient})
    async with as_user(app_engine, owner) as conn:
        [person] = (
            await conn.execute(bound_text("select * from owner_caregivers(:p)"), {"p": patient})
        ).all()
        [pending] = (
            await conn.execute(
                bound_text("select * from owner_caregiver_invitations(:p)"), {"p": patient}
            )
        ).all()
    assert (person.user_id, person.display_name, person.missed_dose_after_min) == (
        carer,
        "Test",
        60,
    )
    assert person.since is not None
    assert (person.critical_result, person.owner_paused) == (True, False)
    assert pending.username == invited_name
    stranger = await make_user(owner_engine)
    for who in (carer, invited, stranger, None):
        async with as_user(app_engine, who) as conn:
            assert (
                await conn.execute(bound_text("select * from owner_caregivers(:p)"), {"p": patient})
            ).all() == []
            assert (
                await conn.execute(
                    bound_text("select * from owner_caregiver_invitations(:p)"), {"p": patient}
                )
            ).all() == []


async def test_the_owner_ends_a_caregivers_access_with_its_alerts(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, carer, patient = await _caregiver(app_engine, owner_engine)
    async with as_user(app_engine, carer) as conn:
        await conn.execute(bound_text("select set_caregiver_alerts(:p, 30, true)"), {"p": patient})
    for who in (carer, await make_user(owner_engine)):
        async with as_user(app_engine, who) as conn:
            with pytest.raises(DBAPIError, match="not the owner"):
                await conn.execute(
                    bound_text("select revoke_caregiver(:p, :u)"), {"p": patient, "u": carer}
                )
    async with as_user(app_engine, owner) as conn:
        assert await scalar(
            conn, bound_text("select revoke_caregiver(:p, :u)"), {"p": patient, "u": carer}
        )
        assert not await scalar(
            conn, bound_text("select revoke_caregiver(:p, :u)"), {"p": patient, "u": carer}
        )
        # the owner's own row is never a caregiver's
        assert not await scalar(
            conn, bound_text("select revoke_caregiver(:p, :u)"), {"p": patient, "u": owner}
        )
    async with as_user(app_engine, carer) as conn:
        assert not await scalar(conn, bound_text("select can_read_patient(:p)"), {"p": patient})
    async with owner_engine.connect() as conn:
        assert (
            await scalar(
                conn,
                bound_text("select count(*) from caregiver_alert_settings where patient_id = :p"),
                {"p": patient},
            )
            == 0
        )
        rows = (
            await conn.execute(
                bound_text(
                    "select actor_id, entity, entity_id, diff from audit_logs"
                    " where action = 'caregiver.revoke' and patient_id = :p"
                ),
                {"p": patient},
            )
        ).all()
    assert [(r.actor_id, r.entity, r.entity_id, r.diff) for r in rows] == [
        (owner, "user", str(carer), None)
    ]


async def test_no_caregiver_invitation_on_a_childs_profile(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, carer, _, name = await _family(app_engine, owner_engine)
    child = await make_patient(app_engine, owner, minor=True)
    async with as_user(app_engine, owner) as conn:
        with pytest.raises(DBAPIError, match="minor") as caught:
            await conn.execute(
                bound_text("select invite_caregiver(:p, :u)"), {"p": child, "u": name}
            )
    assert "minor_profile" in str(caught.value.orig.__cause__.hint)  # type: ignore[union-attr]
    async with as_user(app_engine, carer) as conn:
        assert (
            await conn.execute(bound_text("select * from my_caregiver_invitations()"))
        ).all() == []


async def test_the_sharing_consent_is_checked_before_anything_else(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, _, patient, name = await _family(app_engine, owner_engine)
    await _consent(app_engine, owner, granted=False)
    async with as_user(app_engine, owner) as conn:
        with pytest.raises(DBAPIError, match="consent required"):
            await conn.execute(
                bound_text("select invite_caregiver(:p, :u)"), {"p": patient, "u": name}
            )


async def test_the_lookup_is_never_spent_on_a_childs_profile(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    """Security review H1: the child's-profile check comes before the username lookup."""
    owner, _, _, name = await _family(app_engine, owner_engine)
    child = await make_patient(app_engine, owner, minor=True)
    for username in (name, "nobody.at.all"):
        async with as_user(app_engine, owner) as conn:
            with pytest.raises(DBAPIError, match="minor"):
                await conn.execute(
                    bound_text("select invite_caregiver(:p, :u)"), {"p": child, "u": username}
                )


async def test_a_caregivers_access_row_changes_only_through_the_functions(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    """Security review L2: no unaudited direct revoke or delete by the owner."""
    owner, carer, patient = await _caregiver(app_engine, owner_engine)
    for sql in (
        "update patient_access set revoked_at = now() where patient_id = :p and user_id = :u",
        "delete from patient_access where patient_id = :p and user_id = :u",
    ):
        async with as_user(app_engine, owner) as conn:
            with pytest.raises(DBAPIError, match="through its functions"):
                await conn.execute(bound_text(sql), {"p": patient, "u": carer})
    async with as_user(app_engine, carer) as conn:
        assert await scalar(conn, bound_text("select can_read_patient(:p)"), {"p": patient})
