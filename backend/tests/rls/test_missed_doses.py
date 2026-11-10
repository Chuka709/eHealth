"""Caregivers' dose alerts found by the server (Phase 2.8e; decision (a); H16).

The worker runs for real against the test database (both roles); other tests' targets may be
there too, so every assertion looks at this test's own profile.
"""

import os
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.db.sql import bound_text
from labtrack.worker import missed_doses
from labtrack.worker.missed_doses import run

from .conftest import as_user, make_user, scalar
from .test_caregivers import _caregiver, _invite, _respond, _username

pytestmark = pytest.mark.db

UB = ZoneInfo("Asia/Ulaanbaatar")
NOW = datetime.now(UTC).replace(second=0, microsecond=0)


async def _run(now: datetime = NOW) -> None:
    await run(os.environ["TEST_MAINT_DATABASE_URL"], os.environ["TEST_DATABASE_URL"], now)


async def _medication(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    owner: UUID,
    patient: UUID,
    dose_at: datetime,
    *,
    reminders: bool = True,
    zone: ZoneInfo = UB,
    schedule_entered_late: bool = False,
) -> Any:
    """A daily medication with one dose at `dose_at` (on Ulaanbaatar time, or on the profile's
    zone when `zone` is another), entered two days ago."""
    at = dose_at.astimezone(zone).strftime("%H:%M")
    mode = "home" if zone == UB else "local"
    async with as_user(app_engine, owner) as conn:
        med = await scalar(
            conn,
            bound_text(
                "insert into medications (patient_id, client_id, name, reminders_enabled,"
                " reminder_timezone_mode) values (:p, :c, 'Такролимус', :r, :z) returning id"
            ),
            {"p": patient, "c": uuid4(), "r": reminders, "z": mode},
        )
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "update medications set created_at = now() - interval '2 days' where id = :m"
            ),
            {"m": med},
        )
        # regimens are append-only: arranged as the schema owner with the time it was entered
        await conn.execute(
            bound_text(
                "insert into medication_regimens (patient_id, medication_id, client_id,"
                " effective_from, dose_unit, schedule, created_at) values (:p, :m, :c, :d, 'mg',"
                " jsonb_build_object('type', 'daily', 'times', jsonb_build_array("
                " jsonb_build_object('at', cast(:at as text), 'amount', '1'))),"
                " case when :late then now() else now() - interval '2 days' end)"
            ),
            {
                "p": patient,
                "m": med,
                "c": uuid4(),
                "d": (NOW - timedelta(days=2)).date(),
                "at": at,
                "late": schedule_entered_late,
            },
        )
    return med


async def _alerts(owner_engine: AsyncEngine, patient: UUID) -> list[Any]:
    async with owner_engine.connect() as conn:
        return list(
            (
                await conn.execute(
                    bound_text(
                        "select a.id, a.alerted_user_id, a.slot_at,"
                        " (select count(*) from notifications n where n.kind = 'dose_overdue'"
                        "   and n.entity_id = a.id::text and n.user_id = a.alerted_user_id"
                        "   and n.patient_id = a.patient_id) as notices"
                        " from dose_alerts a where a.patient_id = :p"
                    ),
                    {"p": patient},
                )
            ).all()
        )


async def _alerting_family(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, after_min: int = 30
) -> tuple[UUID, UUID, UUID]:
    owner, carer, patient = await _caregiver(app_engine, owner_engine)
    async with as_user(app_engine, carer) as conn:
        await conn.execute(
            bound_text("select set_caregiver_alerts(:p, :m, false)"),
            {"p": patient, "m": after_min},
        )
    return owner, carer, patient


async def test_an_unrecorded_dose_is_announced_once_to_the_caregiver(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, carer, patient = await _alerting_family(app_engine, owner_engine)
    dose = NOW - timedelta(minutes=40)
    await _medication(app_engine, owner_engine, owner, patient, dose)
    await _run()
    await _run()  # a rerun (or an overlapping run) adds nothing
    [alert] = await _alerts(owner_engine, patient)
    assert (alert.alerted_user_id, alert.slot_at, alert.notices) == (carer, dose, 1)
    # the owner is not alerted about their own doses
    async with as_user(app_engine, owner) as conn:
        assert (
            await scalar(
                conn, bound_text("select count(*) from notifications where kind = 'dose_overdue'")
            )
            == 0
        )


async def test_not_yet_due_too_old_or_recorded_is_not_announced(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, _, patient = await _alerting_family(app_engine, owner_engine)
    await _medication(app_engine, owner_engine, owner, patient, NOW - timedelta(minutes=20))
    await _medication(app_engine, owner_engine, owner, patient, NOW - timedelta(minutes=100))
    recorded = NOW - timedelta(minutes=50)
    med = await _medication(app_engine, owner_engine, owner, patient, recorded)
    async with as_user(app_engine, owner) as conn:
        await conn.execute(
            bound_text(
                "insert into medication_intakes (patient_id, medication_id, client_id,"
                " scheduled_at, status) values (:p, :m, :c, :at, 'skipped')"
            ),
            {"p": patient, "m": med, "c": uuid4(), "at": recorded},
        )
    await _run()
    assert await _alerts(owner_engine, patient) == []


async def test_a_medication_without_reminders_is_not_watched(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, _, patient = await _alerting_family(app_engine, owner_engine)
    await _medication(
        app_engine, owner_engine, owner, patient, NOW - timedelta(minutes=40), reminders=False
    )
    await _run()
    assert await _alerts(owner_engine, patient) == []


async def test_a_pause_or_ended_access_stops_alerts(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, carer, patient = await _alerting_family(app_engine, owner_engine)
    await _medication(app_engine, owner_engine, owner, patient, NOW - timedelta(minutes=40))
    async with as_user(app_engine, owner) as conn:
        await conn.execute(
            bound_text("select pause_caregiver_alerts(:p, :c, true)"), {"p": patient, "c": carer}
        )
    await _run()
    assert await _alerts(owner_engine, patient) == []

    owner, carer, patient = await _alerting_family(app_engine, owner_engine)
    await _medication(app_engine, owner_engine, owner, patient, NOW - timedelta(minutes=40))
    async with as_user(app_engine, owner) as conn:
        await conn.execute(
            bound_text("select revoke_caregiver(:p, :c)"), {"p": patient, "c": carer}
        )
    await _run()
    assert await _alerts(owner_engine, patient) == []


async def _give(
    app_engine: AsyncEngine, user: UUID, kind: str, version: str, granted: bool
) -> None:
    async with as_user(app_engine, user) as conn:
        await conn.execute(
            bound_text(
                "insert into consents (user_id, kind, version, granted)"
                " values (app_user_id(), :k, :v, :g)"
            ),
            {"k": kind, "v": version, "g": granted},
        )


@pytest.mark.parametrize(
    ("who", "kind"),
    [
        ("owner", "sensitive_data"),
        ("caregiver", "sensitive_data"),
        ("owner", "terms"),
        ("caregiver", "privacy"),
    ],
)
async def test_a_withdrawn_required_consent_stops_alerts(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, who: str, kind: str
) -> None:
    owner, carer, patient = await _alerting_family(app_engine, owner_engine)
    await _medication(app_engine, owner_engine, owner, patient, NOW - timedelta(minutes=40))
    user = owner if who == "owner" else carer
    await _give(app_engine, user, kind, "1", True)
    await _give(app_engine, user, kind, "1", False)
    await _run()
    assert await _alerts(owner_engine, patient) == []
    await _give(app_engine, user, kind, "1", True)  # given again: alerts come back
    await _run()
    assert len(await _alerts(owner_engine, patient)) == 1


async def test_a_newer_consent_text_not_yet_accepted_does_not_stop_alerts(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    """Decision 2: only a withdrawal stops a caregiver's safety alerts, not a text update."""
    owner, _, patient = await _alerting_family(app_engine, owner_engine)
    await _medication(app_engine, owner_engine, owner, patient, NOW - timedelta(minutes=40))
    await _give(app_engine, owner, "sensitive_data", "an-old-version", True)
    await _run()
    assert len(await _alerts(owner_engine, patient)) == 1


async def test_each_caregiver_gets_their_own_delay(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, _, patient = await _alerting_family(app_engine, owner_engine, after_min=60)
    await _medication(app_engine, owner_engine, owner, patient, NOW - timedelta(minutes=40))
    await _run()
    assert await _alerts(owner_engine, patient) == []  # 40 minutes late, 60 asked for
    await _run(NOW + timedelta(minutes=25))
    assert len(await _alerts(owner_engine, patient)) == 1


async def test_a_schedule_entered_after_the_dose_time_is_not_held_against_anyone(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    """Medical review 3: a dose time that was not in the schedule at that time."""
    owner, _, patient = await _alerting_family(app_engine, owner_engine)
    await _medication(
        app_engine,
        owner_engine,
        owner,
        patient,
        NOW - timedelta(minutes=40),
        schedule_entered_late=True,
    )
    await _run()
    assert await _alerts(owner_engine, patient) == []


async def test_a_taken_dose_is_not_announced(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, _, patient = await _alerting_family(app_engine, owner_engine)
    dose = NOW - timedelta(minutes=40)
    med = await _medication(app_engine, owner_engine, owner, patient, dose)
    async with as_user(app_engine, owner) as conn:
        await conn.execute(
            bound_text(
                "insert into medication_intakes (patient_id, medication_id, client_id,"
                " scheduled_at, taken_at, status) values (:p, :m, :c, :at, :t, 'taken')"
            ),
            {"p": patient, "m": med, "c": uuid4(), "at": dose, "t": NOW},  # recorded late
        )
    await _run()
    assert await _alerts(owner_engine, patient) == []


async def test_many_doses_at_once_make_one_notification(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    """Security review M2 / H16: every dose is recorded as announced, one push for them."""
    owner, _, patient = await _alerting_family(app_engine, owner_engine)
    for _ in range(4):
        await _medication(app_engine, owner_engine, owner, patient, NOW - timedelta(minutes=40))
    await _run()
    alerts = await _alerts(owner_engine, patient)
    assert len(alerts) == 4
    assert sum(a.notices for a in alerts) == 1
    await _run()
    assert sum(a.notices for a in await _alerts(owner_engine, patient)) == 1


async def test_two_caregivers_each_get_their_own_alert(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, carer, patient = await _alerting_family(app_engine, owner_engine)
    second = await make_user(owner_engine)
    invitation = await _invite(app_engine, owner, patient, await _username(owner_engine, second))
    assert await _respond(app_engine, second, invitation, True)
    async with as_user(app_engine, second) as conn:
        await conn.execute(bound_text("select set_caregiver_alerts(:p, 30, false)"), {"p": patient})
    await _medication(app_engine, owner_engine, owner, patient, NOW - timedelta(minutes=40))
    await _run()
    alerts = await _alerts(owner_engine, patient)
    assert sorted(str(a.alerted_user_id) for a in alerts) == sorted([str(carer), str(second)])
    assert all(a.notices == 1 for a in alerts)


async def test_local_time_follows_the_profiles_time_zone(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    """A dose on Tokyo time (the profile switched there two days ago) is due at Tokyo time."""
    owner, _, patient = await _alerting_family(app_engine, owner_engine)
    tokyo = ZoneInfo("Asia/Tokyo")
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "insert into patient_timezones (patient_id, client_id, timezone, effective_at)"
                " values (:p, :c, 'Asia/Tokyo', now() - interval '2 days')"
            ),
            {"p": patient, "c": uuid4()},
        )
    dose = NOW - timedelta(minutes=40)
    await _medication(app_engine, owner_engine, owner, patient, dose, zone=tokyo)
    await _run()
    [alert] = await _alerts(owner_engine, patient)
    assert alert.slot_at == dose


async def test_one_failing_profile_stops_nobody_else_and_leaves_nothing_half_done(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, _, bad = await _alerting_family(app_engine, owner_engine)
    await _medication(app_engine, owner_engine, owner, bad, NOW - timedelta(minutes=40))
    owner2, _, good = await _alerting_family(app_engine, owner_engine)
    await _medication(app_engine, owner_engine, owner2, good, NOW - timedelta(minutes=40))
    real = missed_doses.check_profile

    async def flaky(db: Any, target: Any, now: datetime) -> int:
        made = await real(db, target, now)
        if target.patient_id == bad:
            raise RuntimeError("boom")  # after writing: the transaction must roll back
        return made

    monkeypatch.setattr(missed_doses, "check_profile", flaky)
    result = await run(os.environ["TEST_MAINT_DATABASE_URL"], os.environ["TEST_DATABASE_URL"], NOW)
    assert result.failed >= 1
    assert await _alerts(owner_engine, bad) == []
    assert len(await _alerts(owner_engine, good)) == 1


async def test_out_of_time_the_rest_wait_for_the_next_run(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, _, patient = await _alerting_family(app_engine, owner_engine)
    await _medication(app_engine, owner_engine, owner, patient, NOW - timedelta(minutes=40))
    result = await run(
        os.environ["TEST_MAINT_DATABASE_URL"], os.environ["TEST_DATABASE_URL"], NOW, -1
    )
    assert result.skipped == result.targets >= 1
    assert await _alerts(owner_engine, patient) == []
    await _run()
    assert len(await _alerts(owner_engine, patient)) == 1


async def test_no_alerts_for_a_deleted_owner_or_a_non_person_caregiver(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    """Q46 and security review L1."""
    owner, _, patient = await _alerting_family(app_engine, owner_engine)
    await _medication(app_engine, owner_engine, owner, patient, NOW - timedelta(minutes=40))
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text("update users set deleted_at = now() where id = :u"), {"u": owner}
        )
    owner2, carer2, patient2 = await _alerting_family(app_engine, owner_engine)
    await _medication(app_engine, owner_engine, owner2, patient2, NOW - timedelta(minutes=40))
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text("update users set role = 'support' where id = :u"), {"u": carer2}
        )
    await _run()
    assert await _alerts(owner_engine, patient) == []
    assert await _alerts(owner_engine, patient2) == []
