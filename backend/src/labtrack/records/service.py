"""Use cases for a profile's transplants, medications, dose history and intakes.

- Creates are idempotent by the device's client_id: a retry of the SAME request gets the
  stored row (`created=False`); a client_id reused for a different record is a conflict (409),
  never "success" for a row the user did not mean.
- A dose change is a new regimen row (CLAUDE.md rule 10, H8); a mistaken future row is voided,
  never edited or deleted.
- Two records of one scheduled dose merge with core.medications.merge_intake (H20): a
  "skipped" sent after "taken" is answered with the stored "taken" (a success, not an error).
- Every write is audited by record id and field names only (rule 3).
"""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import Row
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from labtrack.api.errors import AppError
from labtrack.core.medications import IntakeRecord, merge_intake
from labtrack.core.slots import (
    MedicationPlan,
    Summary,
    ZoneSwitch,
    dose_slots,
    month_window,
    summarize,
)
from labtrack.db.sql import bound_text
from labtrack.records import repository as repo

MAX_INTAKE_WINDOW = timedelta(days=93)


@dataclass(frozen=True)
class Saved:
    id: UUID
    created: bool


def _pg(exc: DBAPIError) -> object:
    return getattr(exc.orig, "__cause__", None) or exc.orig


def _db_error(exc: DBAPIError) -> AppError:
    """Constraint failures a request can cause, as domain errors (never driver text)."""
    state = getattr(_pg(exc), "sqlstate", None)
    name = getattr(_pg(exc), "constraint_name", None) or ""
    if state == "23503":  # a link to a record that is not this profile's (or does not exist)
        if "catalog" in name:
            return AppError(422, "medication.unknown_catalog_code")
        if "transplant" in name:
            return AppError(422, "transplant.not_found")
        return AppError(404, "medication.not_found")
    if state in {"23514", "22001", "22023", "23502"}:  # check, too long, invalid, missing
        return AppError(422, "validation")
    raise exc


async def _guarded[T](db: AsyncSession, work: Callable[[], Awaitable[T]]) -> T:
    """One statement in a savepoint: its constraint failure becomes a domain error and the
    transaction stays usable."""
    try:
        async with db.begin_nested():
            return await work()
    except DBAPIError as exc:
        raise _db_error(exc) from None


async def _created_or_stored(
    db: AsyncSession, table: str, patient_id: UUID, client_id: UUID, new_id: UUID | None
) -> Saved:
    if new_id is not None:
        return Saved(new_id, created=True)
    stored = await repo.id_by_client(db, table, patient_id, client_id)
    if stored is None:
        raise AppError(409, "record.conflict")
    return Saved(stored, created=False)


def _changed(before: Row[Any], values: Mapping[str, object]) -> list[str]:
    current = before._mapping
    return sorted(k for k, v in values.items() if current.get(k) != v)


# --- transplants ------------------------------------------------------------------------------


async def create_transplant(
    db: AsyncSession, patient_id: UUID, client_id: UUID, values: Mapping[str, object]
) -> Saved:
    new_id = await _guarded(db, lambda: repo.insert_transplant(db, patient_id, client_id, values))
    saved = await _created_or_stored(db, "transplants", patient_id, client_id, new_id)
    if saved.created:
        await repo.audit(db, "transplant.create", "transplant", saved.id, patient_id)
    return saved


async def update_transplant(
    db: AsyncSession, patient_id: UUID, transplant_id: UUID, values: Mapping[str, object]
) -> None:
    before = await repo.transplant_for_update(db, patient_id, transplant_id)
    if before is None:
        raise AppError(404, "transplant.not_found")
    changed = _changed(before, values)
    if changed:
        await _guarded(db, lambda: repo.update_transplant(db, patient_id, transplant_id, values))
        await repo.audit(db, "transplant.update", "transplant", transplant_id, patient_id, changed)


# --- medications ------------------------------------------------------------------------------

# Far above any real list (a transplant patient takes ~5-15 medicines; a taper adds a few dose
# changes a month), low enough that the full list the phone caches stays small (security
# review 2.5b): GET /medications returns every medication with its whole dose history.
MAX_MEDICATIONS = 300
MAX_REGIMENS = 200
MAX_PROFILE_REGIMENS = 3000  # the whole list's history (security re-review 2.5b)


async def create_medication(
    db: AsyncSession,
    patient_id: UUID,
    client_id: UUID,
    values: Mapping[str, object],
    regimen: tuple[UUID, Mapping[str, object]] | None,
) -> Saved:
    stored = await repo.id_by_client(db, "medications", patient_id, client_id)
    if stored is None and await repo.count_medications(db, patient_id) >= MAX_MEDICATIONS:
        raise AppError(409, "medication.too_many")
    new_id = await _guarded(db, lambda: repo.insert_medication(db, patient_id, client_id, values))
    saved = await _created_or_stored(db, "medications", patient_id, client_id, new_id)
    if saved.created:
        await repo.audit(db, "medication.create", "medication", saved.id, patient_id)
        if regimen is not None:
            await add_regimen(db, patient_id, saved.id, regimen[0], regimen[1])
    return saved


async def update_medication(
    db: AsyncSession, patient_id: UUID, medication_id: UUID, values: Mapping[str, object]
) -> None:
    before = await repo.medication_for_update(db, patient_id, medication_id)
    if before is None:
        raise AppError(404, "medication.not_found")
    changed = _changed(before, values)
    if changed:
        await _guarded(db, lambda: repo.update_medication(db, patient_id, medication_id, values))
        # a renamed medication keeps its dose history: the audit records that (and who)
        await repo.audit(db, "medication.update", "medication", medication_id, patient_id, changed)


async def add_regimen(
    db: AsyncSession,
    patient_id: UUID,
    medication_id: UUID,
    client_id: UUID,
    values: Mapping[str, object],
) -> Saved:
    """A dose or schedule from `effective_from` on: always a new row (H8)."""
    if await repo.regimen_by_client(db, patient_id, client_id) is None and (
        await repo.count_regimens(db, patient_id, medication_id) >= MAX_REGIMENS
        or await repo.count_regimens(db, patient_id, None) >= MAX_PROFILE_REGIMENS
    ):
        raise AppError(409, "medication.too_many")
    new_id = await _guarded(
        db, lambda: repo.insert_regimen(db, patient_id, medication_id, client_id, values)
    )
    if new_id is not None:
        await repo.audit(db, "medication.dose_change", "medication_regimen", new_id, patient_id)
        return Saved(new_id, created=True)
    stored = await repo.regimen_by_client(db, patient_id, client_id)
    if stored is None or stored.medication_id != medication_id:
        raise AppError(409, "record.conflict")  # this client_id is another medication's change
    return Saved(stored.id, created=False)


async def void_regimen(
    db: AsyncSession, patient_id: UUID, medication_id: UUID, regimen_id: UUID, reason: str
) -> None:
    """Mark a dose change that has not started yet as entered by mistake (once). The row
    stays in the history; a started dose is history and cannot be voided."""
    try:
        async with db.begin_nested():
            count = await repo.void_regimen(db, patient_id, medication_id, regimen_id, reason)
    except DBAPIError as exc:
        if getattr(_pg(exc), "sqlstate", None) == "23514":
            raise AppError(409, "regimen.not_voidable") from None
        raise _db_error(exc) from None
    if not count:
        raise AppError(404, "regimen.not_found")  # unknown, another medication's, or voided
    await repo.audit(
        db, "medication.dose_void", "medication_regimen", regimen_id, patient_id, ["voided_at"]
    )


# --- intakes (H20) ----------------------------------------------------------------------------


def _same_dose(stored: Row[Any], values: Mapping[str, Any]) -> bool:
    return bool(
        stored.medication_id == values["medication_id"]
        and stored.scheduled_at == values["scheduled_at"]
    )


async def record_intake(
    db: AsyncSession, patient_id: UUID, client_id: UUID, values: Mapping[str, Any]
) -> Saved:
    new_id = await _guarded(db, lambda: repo.insert_intake(db, patient_id, client_id, values))
    if new_id is not None:
        await repo.audit(db, "intake.record", "medication_intake", new_id, patient_id)
        return Saved(new_id, created=True)
    # a retry of the same request - or a client_id reused for another dose (a conflict)
    by_client = await repo.intake_by_client(db, patient_id, client_id)
    if by_client is not None:
        # the stored status may since have merged with another device's record (skipped ->
        # taken); a "taken" retry can never find "skipped" (taken never becomes skipped)
        taken_lost = values["status"] != "skipped" and by_client.status == "skipped"
        if not _same_dose(by_client, values) or taken_lost:
            raise AppError(409, "record.conflict")
        return Saved(by_client.id, created=False)
    # another record of the same scheduled dose (the other device, the notification button)
    stored = (
        await repo.intake_for_dose(db, patient_id, values["medication_id"], values["scheduled_at"])
        if values["scheduled_at"] is not None
        else None
    )
    if stored is None:
        raise AppError(409, "record.conflict")
    me = (await db.execute(bound_text("select app_user_id()"))).scalar_one()
    current = IntakeRecord(stored.status, stored.taken_at)
    if current.status != "skipped" and values["status"] != "skipped":
        # Q24: the dose was already taken - by someone, at some time. The first record stays
        # as it is (who, when, who may undo it - H20) and this one is kept beside it as a fact
        # (no judgement, rule 10b); the same person's same time again is a repeat, not a record
        repeat = stored.taken_by == me and stored.taken_at == values["taken_at"]
        kept = not repeat and await _guarded(
            db,
            lambda: repo.insert_intake_extra(
                db, patient_id, stored.id, values["status"], values["taken_at"]
            ),
        )
        if kept:
            await repo.audit(db, "intake.extra", "medication_intake", stored.id, patient_id)
        return Saved(stored.id, created=False)
    merged = merge_intake(current, IntakeRecord(values["status"], values["taken_at"]))
    note = values.get("note") if stored.note is None else None
    changed = [
        f
        for f, a, b in (
            ("status", current.status, merged.status),
            ("taken_at", current.taken_at, merged.taken_at),
        )
        if a != b
    ]
    if note:
        changed.append("note")
    if changed:
        update = {"status": merged.status, "taken_at": merged.taken_at, "note": note}
        count = await _guarded(db, lambda: repo.merge_intake(db, patient_id, stored.id, update))
        if count:
            await repo.audit(
                db, "intake.merge", "medication_intake", stored.id, patient_id, changed
            )
    return Saved(stored.id, created=False)


def window_ok(since: datetime, until: datetime) -> bool:
    return since < until and until - since <= MAX_INTAKE_WINDOW


# --- reminder time zone and monthly summary ---------------------------------------------------


# per user per profile; and for everyone but the owner, per profile together - caregivers
# cannot use up the owner's switches (commit security review)
MAX_SWITCHES_PER_DAY = 20
MAX_PROFILE_SWITCHES_PER_DAY = 40


async def switch_zone(
    db: AsyncSession, patient_id: UUID, client_id: UUID, timezone: str, effective_at: datetime
) -> tuple[Row[Any], bool]:
    """A new zone from `effective_at` on (append-only; Q22). Idempotent by client_id: a retry
    gets the stored row (False), another switch under the same client_id is a conflict.

    - Never before the latest stored switch: a switch that arrives late from an offline phone
      starts when the newest one did (doses already due under that one are not moved -
      medical review H1); the stored row says when it took effect.
    - At most MAX_SWITCHES_PER_DAY new switches per user per profile in 24 hours, and
      MAX_PROFILE_SWITCHES_PER_DAY by everyone together - the owner excepted: 429 (the
      phone's queue keeps it and retries on its next flush - app start, network back,
      foreground)."""
    stored = await repo.zone_by_client(db, patient_id, client_id)
    if stored is not None:
        return _same_switch(stored, timezone, effective_at), False
    await repo.lock_zones(db, patient_id)
    stored = await repo.zone_by_client(db, patient_id, client_id)  # a parallel retry won
    if stored is not None:
        return _same_switch(stored, timezone, effective_at), False
    others, mine, owner = await repo.recent_zone_switches(db, patient_id)
    if mine >= MAX_SWITCHES_PER_DAY or (
        not owner and others + mine >= MAX_PROFILE_SWITCHES_PER_DAY
    ):
        raise AppError(429, "timezone.too_many", retry_after=timedelta(hours=1))
    latest = await repo.latest_zone_switch(db, patient_id)
    starts = max(effective_at, latest) if latest is not None else effective_at
    new_id = await _guarded(
        db, lambda: repo.insert_zone(db, patient_id, client_id, timezone, starts)
    )
    stored = await repo.zone_by_client(db, patient_id, client_id)
    if new_id is None or stored is None:
        raise AppError(409, "record.conflict")
    await repo.audit(db, "timezone.switch", "patient_timezone", new_id, patient_id)
    return stored, True


def _same_switch(stored: Row[Any], timezone: str, effective_at: datetime) -> Row[Any]:
    """A retry of this request: the same zone, taking effect when asked or later (moved to
    the newest switch then)."""
    if stored.timezone != timezone or stored.effective_at < effective_at:
        raise AppError(409, "record.conflict")
    return stored


async def stored_switch(
    db: AsyncSession, patient_id: UUID, client_id: UUID, timezone: str, effective_at: datetime
) -> Row[Any] | None:
    """The stored switch this exact request made, if any (a late retry of a queued write)."""
    stored = await repo.zone_by_client(db, patient_id, client_id)
    if stored is None or stored.timezone != timezone or stored.effective_at < effective_at:
        return None
    return stored


async def zone_switches(
    db: AsyncSession, patient_id: UUID, since: datetime, until: datetime
) -> list[ZoneSwitch]:
    """Switches for a summary window. Past ZONE_WINDOW_MAX in the window (only rows written
    around the caps over many days) the newest are kept and the summary still answers."""
    rows = await repo.zones(db, patient_id, since, until)
    return [ZoneSwitch(r.timezone, r.effective_at, r.seq) for r in rows]


@dataclass(frozen=True)
class MedicationSummary:
    medication_id: UUID
    summary: Summary


async def month_summary(
    db: AsyncSession, patient_id: UUID, year: int, month: int, now: datetime
) -> tuple[Summary, list[MedicationSummary]]:
    """Planned doses of the month up to `now` against the recorded ones (Q23: counts only).

    A medication counts from when it was entered in the app: doses before that (a medication
    taken since 2019, entered today) were never recordable and are not "not recorded"."""
    start, end = month_window(year, month)
    end = min(end, now)
    if end <= start:
        return Summary(0, 0, 0, 0, 0), []
    meds = await repo.medications(db, patient_id)
    history = await repo.regimens(db, patient_id, [m.id for m in meds])
    switches = await zone_switches(db, patient_id, start, end)
    records: dict[UUID, list[tuple[datetime, IntakeRecord]]] = {}
    for r in await repo.scheduled_intakes(db, patient_id, start, end):
        records.setdefault(r.medication_id, []).append(
            (r.scheduled_at, IntakeRecord(r.status, r.taken_at))
        )
    per: list[MedicationSummary] = []
    for m in meds:
        plan = MedicationPlan(
            mode=m.reminder_timezone_mode,
            started_on=m.started_on,
            stopped_on=m.stopped_on,
            planned_end_on=m.planned_end_on,
            regimens=[r for r in history if r.medication_id == m.id],
        )
        slots = dose_slots(plan, switches, max(start, m.created_at), end)
        if slots:
            summary = summarize(slots, records.get(m.id, []), now)
            per.append(MedicationSummary(m.id, summary))
    total = Summary(
        sum(p.summary.planned for p in per),
        sum(p.summary.taken for p in per),
        sum(p.summary.skipped for p in per),
        sum(p.summary.unrecorded for p in per),
        sum(p.summary.open for p in per),
    )
    return total, per


# --- deletes ----------------------------------------------------------------------------------

_DELETES = {
    "transplants": ("transplant.delete", "transplant"),
    "medications": ("medication.delete", "medication"),
    "medication_intakes": ("intake.delete", "medication_intake"),
}


async def delete(
    db: AsyncSession,
    table: str,
    patient_id: UUID,
    row_id: UUID,
    *,
    missing: AppError,
    refused: AppError,
) -> None:
    action, entity = _DELETES[table]
    if table == "medication_intakes" and (await repo.intake_extras(db, patient_id, [row_id])):
        # others logged this dose too: undoing it would erase their records (2.8g, H20)
        raise AppError(409, "intake.has_other_records")
    if await repo.delete_row(db, table, patient_id, row_id):
        await repo.audit(db, action, entity, row_id, patient_id)
        return
    if await repo.row_visible(db, table, patient_id, row_id):
        raise refused  # RLS kept it (history is the owner's; a taken dose its recorder's)
    raise missing
