"""Q42 (user, 2026-11-10): withdrawing the caregiver_sharing consent ends every caregiver's
access to the profiles the user owns, at once, with their alert settings (0023; H16)."""

from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.db.sql import bound_text

from .conftest import as_user, make_patient, scalar
from .test_caregivers import _caregiver, _consent, _invite, _reads, _respond, _username

pytestmark = pytest.mark.db


async def _alerts(owner_engine: AsyncEngine, patient: UUID) -> int:
    async with owner_engine.connect() as conn:
        n: int = await scalar(
            conn,
            bound_text("select count(*) from caregiver_alert_settings where patient_id = :p"),
            {"p": patient},
        )
    return n


async def test_withdrawing_the_consent_lets_every_caregiver_out(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, carer, patient = await _caregiver(app_engine, owner_engine)
    # a second profile of the same owner, with another caregiver
    child = await make_patient(app_engine, owner, minor=True)
    _, other_carer, other_patient = await _caregiver(app_engine, owner_engine)
    second = await _invite(app_engine, owner, child, await _username(owner_engine, other_carer))
    assert await _respond(app_engine, other_carer, second, True)
    async with as_user(app_engine, carer) as conn:
        await conn.execute(bound_text("select set_caregiver_alerts(:p, 30, true)"), {"p": patient})
    assert await _alerts(owner_engine, patient) == 1

    await _consent(app_engine, owner, granted=False)

    assert not await _reads(app_engine, carer, patient)
    assert not await _reads(app_engine, other_carer, child)
    assert await _alerts(owner_engine, patient) == 0
    # someone else's profile (the other caregiver's own family) is not touched
    assert await _reads(app_engine, other_carer, other_patient)
    assert await _reads(app_engine, owner, patient)  # the owner keeps their own profile
    async with owner_engine.connect() as conn:
        rows = (
            await conn.execute(
                bound_text(
                    "select actor_id, entity_id, patient_id, diff from audit_logs"
                    " where action = 'caregiver.consent_revoke' and actor_id = :o"
                ),
                {"o": owner},
            )
        ).all()
    assert {(r.entity_id, r.patient_id) for r in rows} == {
        (str(carer), patient),
        (str(other_carer), child),
    }
    assert all(r.diff is None for r in rows)  # ids only

    # giving the consent again brings nobody back: a new invitation is needed
    await _consent(app_engine, owner, granted=True)
    assert not await _reads(app_engine, carer, patient)
    again = await _invite(app_engine, owner, patient, await _username(owner_engine, carer))
    assert await _respond(app_engine, carer, again, True)
    assert await _reads(app_engine, carer, patient)


async def test_the_withdrawing_user_keeps_their_own_caregiver_access_elsewhere(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    _, carer, patient = await _caregiver(app_engine, owner_engine)
    await _consent(app_engine, carer, granted=False)  # about the carer's own profiles only
    assert await _reads(app_engine, carer, patient)


async def test_a_profile_level_row_ends_nothing(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    """Security review M2: only the user-level consent (patient_id null) lets caregivers in,
    so only its withdrawal lets them out."""
    owner, carer, patient = await _caregiver(app_engine, owner_engine)
    child = await make_patient(app_engine, owner, minor=True)
    async with as_user(app_engine, owner) as conn:
        await conn.execute(
            bound_text(
                "insert into consents (user_id, patient_id, kind, version, granted)"
                " values (app_user_id(), :c, 'caregiver_sharing', '1', false)"
            ),
            {"c": child},
        )
    assert await _reads(app_engine, carer, patient)
