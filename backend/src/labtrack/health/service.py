"""Use cases for a profile's clinical events, vitals, allergies, emergency contacts,
appointments and questions (Phase 2.6).

- Creates are idempotent by the device's client_id: a retry gets the stored row
  (`created=False`).
- Every list stays bounded: a per-profile cap on each kind (far above any real use) and a
  daily cap on vitals - the phone caches these lists.
- Every write is audited by record id and field names only (CLAUDE.md rule 3).
"""

import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import Row
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from labtrack.api.errors import AppError
from labtrack.core.vitals import RULES
from labtrack.health import repository as repo
from labtrack.records.repository import audit

# (table, cap, audit entity, not-found code); the audit action is "<code prefix>.<verb>"
# (audit_write allows [a-z]+ before the dot)
KINDS: dict[str, tuple[repo.Table, int, str, str]] = {
    "events": (repo.EVENTS, 500, "clinical_event", "event.not_found"),
    "allergies": (repo.ALLERGIES, 100, "allergy", "allergy.not_found"),
    "contacts": (repo.CONTACTS, 30, "emergency_contact", "contact.not_found"),
    "appointments": (repo.APPOINTMENTS, 1000, "appointment", "appointment.not_found"),
    "questions": (repo.QUESTIONS, 500, "doctor_question", "question.not_found"),
}
MAX_VITALS_PER_DAY = 500
VITAL_KINDS = sorted(RULES)


def _action(code: str) -> str:
    return code.split(".", 1)[0]  # "event.not_found" -> "event"


@dataclass(frozen=True)
class Saved:
    id: UUID
    created: bool


def _pg(exc: DBAPIError) -> object:
    return getattr(exc.orig, "__cause__", None) or exc.orig


def _db_error(exc: DBAPIError) -> AppError:
    state = getattr(_pg(exc), "sqlstate", None)
    name = getattr(_pg(exc), "constraint_name", None) or ""
    if state == "23503":  # a link to a record that is not this profile's (or does not exist)
        if name == "clinical_events_transplant_id_patient_id_fkey":
            return AppError(422, "transplant.not_found")
        if name == "doctor_questions_appointment_id_patient_id_fkey":
            return AppError(422, "appointment.not_found")
        raise exc
    if state in {"23514", "22001", "22023", "23502", "23505", "22P02"}:
        return AppError(422, "validation")
    raise exc


async def _guarded[T](db: AsyncSession, work: Callable[[], Awaitable[T]]) -> T:
    try:
        async with db.begin_nested():
            return await work()
    except DBAPIError as exc:
        raise _db_error(exc) from None


async def create(
    db: AsyncSession, kind: str, patient_id: UUID, client_id: UUID, values: Mapping[str, object]
) -> Saved:
    table, cap, entity, missing = KINDS[kind]
    stored = await repo.by_client(db, table, patient_id, client_id)
    if stored is not None:
        return Saved(stored, created=False)  # a retry: the stored record
    await repo.lock_kind(db, patient_id, kind)
    if await repo.count(db, table, patient_id) >= cap:
        raise AppError(409, "record.too_many")
    new_id = await _guarded(db, lambda: repo.insert(db, table, patient_id, client_id, values))
    if new_id is None:  # a parallel retry won
        stored = await repo.by_client(db, table, patient_id, client_id)
        if stored is None:
            raise AppError(409, "record.conflict")
        return Saved(stored, created=False)
    await audit(db, f"{_action(missing)}.create", entity, new_id, patient_id)
    return Saved(new_id, created=True)


async def update(
    db: AsyncSession, kind: str, patient_id: UUID, row_id: UUID, values: Mapping[str, object]
) -> None:
    table, _, entity, missing = KINDS[kind]
    before = await repo.lock(db, table, patient_id, row_id)
    if before is None:
        if await repo.exists(db, table, patient_id, row_id):
            # history and the emergency card: only the owner or whoever wrote it edits it (0019)
            raise AppError(403, "record.edit_not_allowed")
        raise AppError(404, missing)
    current = before._mapping
    changed = sorted(k for k, v in values.items() if current.get(k) != v)
    if changed:
        await _guarded(db, lambda: repo.update(db, table, patient_id, row_id, values))
        await audit(db, f"{_action(missing)}.update", entity, row_id, patient_id, changed)


async def delete(db: AsyncSession, kind: str, patient_id: UUID, row_id: UUID) -> None:
    table, _, entity, missing = KINDS[kind]
    if not await repo.delete(db, table, patient_id, row_id):
        if await repo.exists(db, table, patient_id, row_id):
            # history and the emergency card: only the owner or whoever wrote it erases it
            raise AppError(403, "health.delete_not_allowed")
        raise AppError(404, missing)
    await audit(db, f"{_action(missing)}.delete", entity, row_id, patient_id)


# --- vitals -----------------------------------------------------------------------------------


def item_client_id(client_id: UUID, kind: str) -> UUID:
    """One reading (e.g. blood pressure) is several rows: each gets a client_id derived from the
    reading's, so a retried reading finds every stored row."""
    return uuid.uuid5(client_id, kind)


async def record_vitals(
    db: AsyncSession,
    patient_id: UUID,
    client_id: UUID,
    items: Sequence[Mapping[str, Any]],
    common: Mapping[str, object],
) -> tuple[Sequence[Row[Any]], bool]:
    """A reading of one or more kinds measured together (systolic + diastolic + pulse share a
    group). Returns the stored rows and whether they were created now."""
    kinds = {str(i["kind"]) for i in items}
    ids = [item_client_id(client_id, k) for k in sorted(kinds)]
    every = [item_client_id(client_id, k) for k in VITAL_KINDS]
    stored = await repo.vitals_by_clients(db, patient_id, every)
    grouped = await repo.vital_group_kinds(db, patient_id, client_id)
    if stored or grouped:
        # a retry of this reading - or the client_id reused for another one (a conflict)
        if {str(r.kind) for r in stored} != kinds or (grouped and grouped != kinds):
            raise AppError(409, "record.conflict")
        return stored, False
    await repo.lock_kind(db, patient_id, "vitals")
    if await repo.recent_vitals(db, patient_id) >= MAX_VITALS_PER_DAY:
        raise AppError(429, "record.too_many", retry_after=timedelta(hours=1))
    group = client_id if len(items) > 1 else None
    by_kind = {str(i["kind"]): i for i in items}
    for cid, item in zip(ids, (by_kind[k] for k in sorted(kinds)), strict=True):
        values: dict[str, object] = {**common, **item, "group_id": group}

        async def insert(c: UUID = cid, v: dict[str, object] = values) -> UUID | None:
            return await repo.insert_vital(db, patient_id, c, v)

        new_id = await _guarded(db, insert)
        if new_id is not None:
            await audit(db, "vital.create", "vital", new_id, patient_id)
    return await repo.vitals_by_clients(db, patient_id, ids), True


async def delete_vital(db: AsyncSession, patient_id: UUID, vital_id: UUID) -> None:
    if not await repo.delete_vital(db, patient_id, vital_id):
        if await repo.vital_exists(db, patient_id, vital_id):
            raise AppError(403, "health.delete_not_allowed")
        raise AppError(404, "vital.not_found")
    await audit(db, "vital.delete", "vital", vital_id, patient_id)
