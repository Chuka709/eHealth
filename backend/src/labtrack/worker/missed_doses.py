"""Dose alerts to caregivers, found by the server (Phase 2.8e; decision (a); H16).

Every few minutes, on the maintenance worker (no internet, no uploads):
1. maint_caregiver_alert_targets() gives (profile, caregiver, delay) as ids only (labtrack_maint).
2. Each profile is read *as that caregiver* (labtrack_app, app.user_id = the caregiver) under
   the normal RLS - the maintenance role never reads health data (0020). Only what planning
   needs is read: no medication name, strength or note is loaded.
3. core.caregiver_alerts picks the planned doses with nothing recorded, due within the last
   hour; each gets a dose_alerts row (unique per dose and caregiver, so a rerun adds none).
   One 'dose_overdue' notification per profile and run, however many doses are due (H16);
   its entity is the first new alert. The push worker sends it with generic text.

Only medications with reminders on are watched: those are the doses the user chose to be
reminded of and records (CLAUDE.md 10b: user-configured reminders); the caregiver sees how
many are watched (api/caregivers.py). As-needed ones have no planned doses.

A run stops taking new profiles before the task's time limit (the rest wait 5 minutes, in a
new random order, so no profile is always last). No task arguments; logs carry counts only.
"""

import asyncio
import random
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final
from uuid import UUID

import structlog
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from labtrack.core.caregiver_alerts import alert_range, overdue_slots, planned_in_time
from labtrack.core.slots import MedicationPlan, dose_slots
from labtrack.db.sql import bound_text
from labtrack.records import repository as repo
from labtrack.records.service import zone_switches

log = structlog.get_logger(__name__)

RUN_BUDGET_SECONDS: Final = 200  # the task's soft limit is 240 s (celery_app.py)

_SET_USER = bound_text("select set_config('app.user_id', :uid, true)")
_WATCHED = bound_text(
    "select id, reminder_timezone_mode, started_on, stopped_on, planned_end_on, created_at"
    " from medications where patient_id = :p and reminders_enabled"
)
_ALERT = bound_text(
    "insert into dose_alerts (patient_id, medication_id, slot_at, alerted_user_id)"
    " values (:p, :m, :at, app_user_id()) on conflict do nothing returning id"
)
_NOTIFY = bound_text(
    "select notify(app_user_id(), 'dose_overdue', :p, :e, 'notification.dose_overdue')"
)


@dataclass(frozen=True)
class Target:
    patient_id: UUID
    caregiver_user_id: UUID
    after_min: int


@dataclass(frozen=True)
class MissedDoseResult:
    targets: int = 0
    alerts: int = 0  # doses announced
    notices: int = 0  # notifications made (one per profile and run at most)
    failed: int = 0
    skipped: int = 0  # left for the next run (time budget)


async def _targets(maint: AsyncEngine) -> list[Target]:
    async with maint.connect() as conn:
        rows = (
            await conn.execute(bound_text("select * from maint_caregiver_alert_targets()"))
        ).all()
    return [Target(**r._mapping) for r in rows]


def _plan(med: Any, history: Sequence[Any]) -> MedicationPlan:
    return MedicationPlan(
        mode=med.reminder_timezone_mode,
        started_on=med.started_on,
        stopped_on=med.stopped_on,
        planned_end_on=med.planned_end_on,
        regimens=history,
    )


async def check_profile(db: AsyncSession, target: Target, now: datetime) -> int:
    """Within a transaction acting as the caregiver: the doses announced now (0 or more, with
    one notification for all of them)."""
    delay = timedelta(minutes=target.after_min)
    start, end = alert_range(now, delay)
    meds = (await db.execute(_WATCHED, {"p": target.patient_id})).all()
    if not meds:
        return 0
    history = await repo.regimens(db, target.patient_id, [m.id for m in meds])
    switches = await zone_switches(db, target.patient_id, start, end)
    recorded: dict[UUID, list[datetime]] = {}
    for r in await repo.scheduled_intakes(db, target.patient_id, start, end):
        recorded.setdefault(r.medication_id, []).append(r.scheduled_at)
    first: int | None = None
    made = 0
    for med in meds:
        regimens = [r for r in history if r.medication_id == med.id]
        # a medication counts from when it was entered (no alerts for doses before that)
        slots = dose_slots(_plan(med, regimens), switches, max(start, med.created_at), end)
        for slot in overdue_slots(slots, recorded.get(med.id, []), now, delay):
            if not planned_in_time(slot, regimens):
                continue
            alert = (
                await db.execute(
                    _ALERT, {"p": target.patient_id, "m": med.id, "at": slot.scheduled_at}
                )
            ).scalar_one_or_none()
            if alert is None:
                continue  # announced already
            first = alert if first is None else first
            made += 1
    if first is not None:
        await db.execute(_NOTIFY, {"p": target.patient_id, "e": str(first)})
    return made


async def run(
    maint_url: str,
    app_url: str,
    now: datetime | None = None,
    budget_seconds: float = RUN_BUDGET_SECONDS,
) -> MissedDoseResult:
    maint = create_async_engine(maint_url, hide_parameters=True)
    app = create_async_engine(app_url, hide_parameters=True, pool_reset_on_return="rollback")
    at = now or datetime.now(UTC)
    deadline = time.monotonic() + budget_seconds
    alerts = notices = failed = skipped = 0
    targets: list[Target] = []
    try:
        targets = await _targets(maint)
        random.shuffle(targets)
        for target in targets:
            if time.monotonic() > deadline:
                skipped += 1
                continue
            try:
                async with AsyncSession(app) as db, db.begin():
                    await db.execute(_SET_USER, {"uid": str(target.caregiver_user_id)})
                    made = await check_profile(db, target, at)
                alerts += made
                notices += made > 0
            except SoftTimeLimitExceeded:
                raise  # the run is out of time: stop, never count it as one profile's failure
            except Exception as exc:  # one profile never stops the others
                # no traceback: driver text can carry row values
                log.warning("missed_dose_check_failed", error=type(exc).__name__)
                failed += 1
    finally:
        await maint.dispose()
        await app.dispose()
    result = MissedDoseResult(len(targets), alerts, notices, failed, skipped)
    if result.failed or result.skipped:
        # a caregiver may not hear about a dose: make it visible (Sentry), counts only
        log.error(
            "missed_doses_incomplete",
            targets=result.targets,
            failed=result.failed,
            skipped=result.skipped,
        )
    elif result.alerts:
        log.info(
            "missed_doses_checked",
            targets=result.targets,
            alerts=result.alerts,
            notices=result.notices,
        )
    return result


def run_sync(maint_url: str, app_url: str) -> MissedDoseResult:
    return asyncio.run(run(maint_url, app_url))
