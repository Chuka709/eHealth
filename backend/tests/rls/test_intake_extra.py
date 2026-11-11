"""A second "taken" record of a dose, kept as a fact (0027; Q24; H20)."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.db.sql import bound_text

from .conftest import as_user, make_patient, make_user, scalar
from .test_caregivers import _caregiver

pytestmark = pytest.mark.db

DOSE = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(hours=1)


async def _taken_dose(app_engine: AsyncEngine, owner: UUID, patient: UUID) -> Any:
    async with as_user(app_engine, owner) as conn:
        med = await scalar(
            conn,
            bound_text(
                "insert into medications (patient_id, client_id, name) values (:p, :c, 'X')"
                " returning id"
            ),
            {"p": patient, "c": uuid4()},
        )
        return await scalar(
            conn,
            bound_text(
                "insert into medication_intakes (patient_id, medication_id, client_id,"
                " scheduled_at, taken_at, status) values (:p, :m, :c, :at, :at, 'taken')"
                " returning id"
            ),
            {"p": patient, "m": med, "c": uuid4(), "at": DOSE},
        )


async def _extra(app_engine: AsyncEngine, user: UUID, patient: Any, intake: Any, at: Any) -> None:
    async with as_user(app_engine, user) as conn:
        await conn.execute(
            bound_text(
                "insert into medication_intake_extra (patient_id, intake_id, status, taken_at)"
                " values (:p, :i, 'taken', :at)"
            ),
            {"p": patient, "i": intake, "at": at},
        )


async def _delete_extras(app_engine: AsyncEngine, user: UUID, intake: Any) -> int:
    async with as_user(app_engine, user) as conn:
        result = await conn.execute(
            bound_text("delete from medication_intake_extra where intake_id = :i"), {"i": intake}
        )
    return int(result.rowcount or 0)


async def test_the_writer_is_recorded_by_the_database_and_rows_never_change(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, carer, patient = await _caregiver(app_engine, owner_engine)
    intake = await _taken_dose(app_engine, owner, patient)
    await _extra(app_engine, carer, patient, intake, DOSE + timedelta(minutes=50))
    async with owner_engine.connect() as conn:
        by = await scalar(
            conn,
            bound_text("select recorded_by from medication_intake_extra where intake_id = :i"),
            {"i": intake},
        )
    assert by == carer
    for sql in (
        "update medication_intake_extra set taken_at = now() where intake_id = :i",
        "insert into medication_intake_extra (patient_id, intake_id, status, taken_at,"
        " recorded_by) values (:p, :i, 'taken', now(), :u)",
    ):
        async with as_user(app_engine, owner) as conn:
            with pytest.raises(DBAPIError, match="permission denied"):
                await conn.execute(bound_text(sql), {"i": intake, "p": patient, "u": carer})
    # roles by row, relative to whoever asks - never a name, never for a chosen user id
    roles = bound_text(
        "select intake_recorder_role(:i) as main,"
        " (select extra_recorder_role(id) from medication_intake_extra where intake_id = :i) as x"
    )
    async with as_user(app_engine, owner) as conn:
        row = (await conn.execute(roles, {"i": intake})).one()
    assert (row.main, row.x) == ("you", "caregiver")
    async with as_user(app_engine, carer) as conn:
        row = (await conn.execute(roles, {"i": intake})).one()
    assert (row.main, row.x) == ("owner", "you")


async def test_strangers_see_and_write_nothing_and_a_dose_is_its_profiles(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, _, patient = await _caregiver(app_engine, owner_engine)
    intake = await _taken_dose(app_engine, owner, patient)
    await _extra(app_engine, owner, patient, intake, DOSE + timedelta(minutes=30))
    stranger = await make_user(owner_engine)
    other = await make_patient(app_engine, stranger)
    async with as_user(app_engine, stranger) as conn:
        assert await scalar(conn, bound_text("select count(*) from medication_intake_extra")) == 0
        assert (
            await scalar(conn, bound_text("select intake_recorder_role(:i)"), {"i": intake}) is None
        )
    # refused either way: the stranger cannot see the dose, nor write on the profile
    with pytest.raises(DBAPIError, match=r"row-level security|not this profile"):
        await _extra(app_engine, stranger, patient, intake, DOSE)
    # the stranger's own profile cannot carry another profile's dose
    with pytest.raises(DBAPIError, match="not this profile"):
        await _extra(app_engine, stranger, other, intake, DOSE)
    assert await _delete_extras(app_engine, stranger, intake) == 0


async def test_at_most_ten_records_of_one_dose(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, _, patient = await _caregiver(app_engine, owner_engine)
    intake = await _taken_dose(app_engine, owner, patient)
    for n in range(10):
        await _extra(app_engine, owner, patient, intake, DOSE + timedelta(minutes=n + 1))
    with pytest.raises(DBAPIError, match="too many"):
        await _extra(app_engine, owner, patient, intake, DOSE + timedelta(minutes=30))


async def test_only_ones_own_extra_is_undone_and_a_shared_dose_stays(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    """2.8g review: undoing must never erase someone else's record of the dose."""
    owner, carer, patient = await _caregiver(app_engine, owner_engine)
    intake = await _taken_dose(app_engine, owner, patient)
    await _extra(app_engine, carer, patient, intake, DOSE + timedelta(minutes=40))
    # the owner can neither delete the caregiver's record nor undo the dose it hangs on
    assert await _delete_extras(app_engine, owner, intake) == 0
    async with as_user(app_engine, owner) as conn:
        with pytest.raises(DBAPIError, match="others logged this dose too"):
            await conn.execute(
                bound_text("delete from medication_intakes where id = :i"), {"i": intake}
            )
    # the caregiver undoes their own; then the dose can be undone again
    assert await _delete_extras(app_engine, carer, intake) == 1
    async with as_user(app_engine, owner) as conn:
        await conn.execute(
            bound_text("delete from medication_intakes where id = :i"), {"i": intake}
        )


async def test_deleting_a_medicine_still_takes_its_doses_and_records(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    """A cascade is not an undo: the guard leaves it alone."""
    owner, carer, patient = await _caregiver(app_engine, owner_engine)
    intake = await _taken_dose(app_engine, owner, patient)
    await _extra(app_engine, carer, patient, intake, DOSE + timedelta(minutes=40))
    async with as_user(app_engine, owner) as conn:
        await conn.execute(
            bound_text(
                "delete from medications where id ="
                " (select medication_id from medication_intakes where id = :i)"
            ),
            {"i": intake},
        )
    async with owner_engine.connect() as conn:
        left = await scalar(
            conn,
            bound_text("select count(*) from medication_intake_extra where intake_id = :i"),
            {"i": intake},
        )
    assert left == 0


async def test_admin_roles_see_nothing(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    """Rule 2a."""
    owner, carer, patient = await _caregiver(app_engine, owner_engine)
    intake = await _taken_dose(app_engine, owner, patient)
    await _extra(app_engine, carer, patient, intake, DOSE + timedelta(minutes=40))
    admin = await make_user(owner_engine, "super_admin")
    async with as_user(admin_engine, admin) as conn:
        with pytest.raises(DBAPIError, match="permission denied"):
            await conn.execute(bound_text("select count(*) from medication_intake_extra"))
