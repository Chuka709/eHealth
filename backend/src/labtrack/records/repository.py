"""SQL for transplants, medications, regimens and intakes (migration 0014).

Every statement runs in the caller's user transaction (RLS); column lists are written out
(no SQL is assembled from strings). Values are bound; nothing here logs them.
"""

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Row
from sqlalchemy.ext.asyncio import AsyncSession

from labtrack.db.sql import bound_text

# --- transplants ------------------------------------------------------------------------------

TRANSPLANT_FIELDS = (
    "organ",
    "organ_detail",
    "transplant_date",
    "date_precision",
    "country",
    "city",
    "hospital",
    "surgeon",
    "transplant_number",
    "donor_type",
    "donor_relation",
    "recipient_blood_type",
    "donor_blood_type",
    "abo_incompatible",
    "cmv_donor",
    "cmv_recipient",
    "ebv_donor",
    "ebv_recipient",
    "hla_mismatch",
    "primary_disease",
    "pre_transplant_dialysis",
    "induction_therapy",
    "graft_status",
    "graft_status_date",
    "graft_failure_reason",
    "follow_up_center",
    "follow_up_doctor",
    "notes",
)

_TRANSPLANT_SELECT = bound_text(
    "select id, organ::text as organ, organ_detail, transplant_date, date_precision, country,"
    " city, hospital, surgeon, transplant_number, donor_type::text as donor_type, donor_relation,"
    " recipient_blood_type, donor_blood_type, abo_incompatible, cmv_donor, cmv_recipient,"
    " ebv_donor, ebv_recipient, hla_mismatch, primary_disease, pre_transplant_dialysis,"
    " induction_therapy, graft_status::text as graft_status, graft_status_date,"
    " graft_failure_reason, follow_up_center, follow_up_doctor, notes, created_at, updated_at"
    " from transplants where patient_id = :p and (cast(:i as uuid) is null or id = :i)"
    " order by transplant_date desc, created_at desc"
)
_TRANSPLANT_LOCK = bound_text(
    "select organ::text as organ, organ_detail, transplant_date, date_precision, country, city,"
    " hospital, surgeon, transplant_number, donor_type::text as donor_type, donor_relation,"
    " recipient_blood_type, donor_blood_type, abo_incompatible, cmv_donor, cmv_recipient,"
    " ebv_donor, ebv_recipient, hla_mismatch, primary_disease, pre_transplant_dialysis,"
    " induction_therapy, graft_status::text as graft_status, graft_status_date,"
    " graft_failure_reason, follow_up_center, follow_up_doctor, notes"
    " from transplants where patient_id = :p and id = :i for update"
)

_TRANSPLANT_INSERT = bound_text(
    "insert into transplants (patient_id, client_id, organ, organ_detail, transplant_date,"
    " date_precision, country, city, hospital, surgeon, transplant_number, donor_type,"
    " donor_relation, recipient_blood_type, donor_blood_type, abo_incompatible, cmv_donor,"
    " cmv_recipient, ebv_donor, ebv_recipient, hla_mismatch, primary_disease,"
    " pre_transplant_dialysis, induction_therapy, graft_status, graft_status_date,"
    " graft_failure_reason, follow_up_center, follow_up_doctor, notes)"
    " values (:p, :client_id, cast(:organ as organ), :organ_detail, :transplant_date,"
    " :date_precision, :country, :city, :hospital, :surgeon, :transplant_number,"
    " cast(:donor_type as donor_type), :donor_relation, :recipient_blood_type,"
    " :donor_blood_type, :abo_incompatible, :cmv_donor, :cmv_recipient, :ebv_donor,"
    " :ebv_recipient, :hla_mismatch, :primary_disease, :pre_transplant_dialysis,"
    " :induction_therapy, cast(:graft_status as graft_status), :graft_status_date,"
    " :graft_failure_reason, :follow_up_center, :follow_up_doctor, :notes)"
    " on conflict (patient_id, client_id) do nothing returning id"
)

_TRANSPLANT_UPDATE = bound_text(
    "update transplants set organ = cast(:organ as organ), organ_detail = :organ_detail,"
    " transplant_date = :transplant_date, date_precision = :date_precision, country = :country,"
    " city = :city, hospital = :hospital, surgeon = :surgeon,"
    " transplant_number = :transplant_number, donor_type = cast(:donor_type as donor_type),"
    " donor_relation = :donor_relation, recipient_blood_type = :recipient_blood_type,"
    " donor_blood_type = :donor_blood_type, abo_incompatible = :abo_incompatible,"
    " cmv_donor = :cmv_donor, cmv_recipient = :cmv_recipient, ebv_donor = :ebv_donor,"
    " ebv_recipient = :ebv_recipient, hla_mismatch = :hla_mismatch,"
    " primary_disease = :primary_disease, pre_transplant_dialysis = :pre_transplant_dialysis,"
    " induction_therapy = :induction_therapy, graft_status = cast(:graft_status as graft_status),"
    " graft_status_date = :graft_status_date, graft_failure_reason = :graft_failure_reason,"
    " follow_up_center = :follow_up_center, follow_up_doctor = :follow_up_doctor, notes = :notes"
    " where patient_id = :p and id = :i"
)


async def transplants(
    db: AsyncSession, patient_id: UUID, transplant_id: UUID | None = None
) -> Sequence[Row[Any]]:
    return (await db.execute(_TRANSPLANT_SELECT, {"p": patient_id, "i": transplant_id})).all()


async def transplant_for_update(
    db: AsyncSession, patient_id: UUID, transplant_id: UUID
) -> Row[Any] | None:
    """The editable fields, locked until the transaction ends (concurrent edits queue)."""
    return (await db.execute(_TRANSPLANT_LOCK, {"p": patient_id, "i": transplant_id})).one_or_none()


async def insert_transplant(
    db: AsyncSession, patient_id: UUID, client_id: UUID, values: Mapping[str, object]
) -> UUID | None:
    """The new id, or None when this client_id was already stored (a retried request)."""
    params = {"p": patient_id, "client_id": client_id, **values}
    new_id: UUID | None = (await db.execute(_TRANSPLANT_INSERT, params)).scalar_one_or_none()
    return new_id


async def update_transplant(
    db: AsyncSession, patient_id: UUID, transplant_id: UUID, values: Mapping[str, object]
) -> int:
    params = {"p": patient_id, "i": transplant_id, **values}
    return (await db.execute(_TRANSPLANT_UPDATE, params)).rowcount  # type: ignore[attr-defined, no-any-return]


async def id_by_client(
    db: AsyncSession, table: str, patient_id: UUID, client_id: UUID
) -> UUID | None:
    sql = _BY_CLIENT[table]
    found: UUID | None = (
        await db.execute(sql, {"p": patient_id, "c": client_id})
    ).scalar_one_or_none()
    return found


_BY_CLIENT = {
    "transplants": bound_text(
        "select id from transplants where patient_id = :p and client_id = :c"
    ),
    "medications": bound_text(
        "select id from medications where patient_id = :p and client_id = :c"
    ),
    "medication_regimens": bound_text(
        "select id from medication_regimens where patient_id = :p and client_id = :c"
    ),
    "medication_intakes": bound_text(
        "select id from medication_intakes where patient_id = :p and client_id = :c"
    ),
    "patient_timezones": bound_text(
        "select id from patient_timezones where patient_id = :p and client_id = :c"
    ),
}

_DELETE = {
    "transplants": bound_text("delete from transplants where patient_id = :p and id = :i"),
    "medications": bound_text("delete from medications where patient_id = :p and id = :i"),
    "medication_intakes": bound_text(
        "delete from medication_intakes where patient_id = :p and id = :i"
    ),
}
_EXISTS = {
    "transplants": bound_text("select 1 from transplants where patient_id = :p and id = :i"),
    "medications": bound_text("select 1 from medications where patient_id = :p and id = :i"),
    "medication_intakes": bound_text(
        "select 1 from medication_intakes where patient_id = :p and id = :i"
    ),
}


async def delete_row(db: AsyncSession, table: str, patient_id: UUID, row_id: UUID) -> int:
    return (await db.execute(_DELETE[table], {"p": patient_id, "i": row_id})).rowcount  # type: ignore[attr-defined, no-any-return]


async def row_visible(db: AsyncSession, table: str, patient_id: UUID, row_id: UUID) -> bool:
    return (await db.execute(_EXISTS[table], {"p": patient_id, "i": row_id})).first() is not None


# --- medications ------------------------------------------------------------------------------

MEDICATION_FIELDS = (
    "catalog_code",
    "name",
    "brand",
    "form",
    "strength",
    "route",
    "purpose",
    "prescribed_by",
    "transplant_id",
    "started_on",
    "stopped_on",
    "stop_reason",
    "planned_end_on",
    "is_long_term",
    "reminders_enabled",
    "reminder_timezone_mode",
    "notes",
)

_MEDICATION_SELECT = bound_text(
    "select m.id, m.catalog_code, c.category, m.name, m.brand, m.form, m.strength, m.route,"
    " m.purpose, m.prescribed_by, m.transplant_id, m.started_on, m.stopped_on, m.stop_reason,"
    " m.planned_end_on, m.is_long_term, m.reminders_enabled, m.reminder_timezone_mode,"
    " m.notes, m.created_at, m.updated_at from medications m"
    " left join medication_catalog c on c.code = m.catalog_code"
    " where m.patient_id = :p and (cast(:i as uuid) is null or m.id = :i)"
    # current first, immunosuppressants first among them (docs/08 "Эм")
    " order by coalesce(m.stopped_on is not null or m.planned_end_on < local_today(), false),"
    " (c.category = 'immunosuppressant') desc nulls last,"
    " m.name, m.created_at"
)

_MEDICATION_INSERT = bound_text(
    "insert into medications (patient_id, client_id, catalog_code, name, brand, form, strength,"
    " route, purpose, prescribed_by, transplant_id, started_on, stopped_on, stop_reason,"
    " planned_end_on, is_long_term, reminders_enabled, reminder_timezone_mode, notes)"
    " values (:p, :client_id, :catalog_code, :name, :brand, :form, :strength, :route, :purpose,"
    " :prescribed_by, :transplant_id, :started_on, :stopped_on, :stop_reason, :planned_end_on,"
    " :is_long_term, :reminders_enabled, :reminder_timezone_mode, :notes)"
    " on conflict (patient_id, client_id) do nothing returning id"
)

_MEDICATION_UPDATE = bound_text(
    "update medications set catalog_code = :catalog_code, name = :name, brand = :brand,"
    " form = :form, strength = :strength, route = :route, purpose = :purpose,"
    " prescribed_by = :prescribed_by, transplant_id = :transplant_id, started_on = :started_on,"
    " stopped_on = :stopped_on, stop_reason = :stop_reason, planned_end_on = :planned_end_on,"
    " is_long_term = :is_long_term,"
    " reminders_enabled = :reminders_enabled, reminder_timezone_mode = :reminder_timezone_mode,"
    " notes = :notes where patient_id = :p and id = :i"
)


async def medications(
    db: AsyncSession, patient_id: UUID, medication_id: UUID | None = None
) -> Sequence[Row[Any]]:
    return (await db.execute(_MEDICATION_SELECT, {"p": patient_id, "i": medication_id})).all()


_MEDICATION_LOCK = bound_text(
    "select catalog_code, name, brand, form, strength, route, purpose, prescribed_by,"
    " transplant_id, started_on, stopped_on, stop_reason, planned_end_on, is_long_term,"
    " reminders_enabled, reminder_timezone_mode, notes from medications"
    " where patient_id = :p and id = :i for update"
)


async def medication_for_update(
    db: AsyncSession, patient_id: UUID, medication_id: UUID
) -> Row[Any] | None:
    return (await db.execute(_MEDICATION_LOCK, {"p": patient_id, "i": medication_id})).one_or_none()


async def insert_medication(
    db: AsyncSession, patient_id: UUID, client_id: UUID, values: Mapping[str, object]
) -> UUID | None:
    params = {"p": patient_id, "client_id": client_id, **values}
    new_id: UUID | None = (await db.execute(_MEDICATION_INSERT, params)).scalar_one_or_none()
    return new_id


async def update_medication(
    db: AsyncSession, patient_id: UUID, medication_id: UUID, values: Mapping[str, object]
) -> int:
    params = {"p": patient_id, "i": medication_id, **values}
    return (await db.execute(_MEDICATION_UPDATE, params)).rowcount  # type: ignore[attr-defined, no-any-return]


# --- regimens (append-only) -------------------------------------------------------------------

_REGIMEN_SELECT = bound_text(
    "select id, medication_id, seq, effective_from, dose_amount, dose_unit, dose_unit_text,"
    " schedule, instructions, changed_by_note, voided_at, void_reason, created_at"
    " from medication_regimens"
    " where patient_id = :p and medication_id = any(cast(:m as uuid[]))"
    " order by effective_from desc, seq desc"
)
_REGIMEN_INSERT = bound_text(
    "insert into medication_regimens (patient_id, medication_id, client_id, effective_from,"
    " dose_amount, dose_unit, dose_unit_text, schedule, instructions, changed_by_note)"
    " values (:p, :m, :client_id, :effective_from, :dose_amount, :dose_unit, :dose_unit_text,"
    " cast(:schedule as jsonb), :instructions, :changed_by_note)"
    " on conflict (patient_id, client_id) do nothing returning id"
)


_REGIMEN_BY_CLIENT = bound_text(
    "select id, medication_id from medication_regimens where patient_id = :p and client_id = :c"
)
_REGIMEN_VOID = bound_text(
    "update medication_regimens set voided_at = now(), void_reason = :r"
    " where patient_id = :p and medication_id = :m and id = :i and voided_at is null"
)


_MEDICATION_COUNT = bound_text("select count(*) from medications where patient_id = :p")
_REGIMEN_COUNT = bound_text(
    "select count(*) from medication_regimens where patient_id = :p"
    " and (cast(:m as uuid) is null or medication_id = :m)"
)


async def count_medications(db: AsyncSession, patient_id: UUID) -> int:
    n: int = (await db.execute(_MEDICATION_COUNT, {"p": patient_id})).scalar_one()
    return n


async def count_regimens(db: AsyncSession, patient_id: UUID, medication_id: UUID | None) -> int:
    """One medication's dose history rows, or the whole profile's (None)."""
    n: int = (await db.execute(_REGIMEN_COUNT, {"p": patient_id, "m": medication_id})).scalar_one()
    return n


async def regimen_by_client(db: AsyncSession, patient_id: UUID, client_id: UUID) -> Row[Any] | None:
    return (await db.execute(_REGIMEN_BY_CLIENT, {"p": patient_id, "c": client_id})).one_or_none()


async def void_regimen(
    db: AsyncSession, patient_id: UUID, medication_id: UUID, regimen_id: UUID, reason: str
) -> int:
    params = {"p": patient_id, "m": medication_id, "i": regimen_id, "r": reason}
    return (await db.execute(_REGIMEN_VOID, params)).rowcount  # type: ignore[attr-defined, no-any-return]


async def regimens(
    db: AsyncSession, patient_id: UUID, medication_ids: Sequence[UUID]
) -> Sequence[Row[Any]]:
    return (await db.execute(_REGIMEN_SELECT, {"p": patient_id, "m": list(medication_ids)})).all()


async def insert_regimen(
    db: AsyncSession,
    patient_id: UUID,
    medication_id: UUID,
    client_id: UUID,
    values: Mapping[str, object],
) -> UUID | None:
    params = {
        "p": patient_id,
        "m": medication_id,
        "client_id": client_id,
        **values,
        "schedule": json.dumps(values["schedule"]),
    }
    new_id: UUID | None = (await db.execute(_REGIMEN_INSERT, params)).scalar_one_or_none()
    return new_id


# --- intakes ----------------------------------------------------------------------------------

_INTAKE_COLUMNS = (
    "select id, medication_id, scheduled_at, taken_at, status, note, created_at, updated_at,"
    # who recorded the dose as taken, relative to the caller - never a name (Q24)
    " taken_by, intake_recorder_role(id)"
    " as recorded_by_role from medication_intakes where patient_id = :p"
)
_INTAKES_RANGE = bound_text(
    _INTAKE_COLUMNS + " and coalesce(scheduled_at, taken_at) >= :since"
    " and coalesce(scheduled_at, taken_at) < :until"
    " and (cast(:m as uuid) is null or medication_id = :m)"
    " order by coalesce(scheduled_at, taken_at) desc limit :limit"
)
_INTAKE_BY_ID = bound_text(_INTAKE_COLUMNS + " and id = :i")
_INTAKE_BY_CLIENT = bound_text(_INTAKE_COLUMNS + " and client_id = :c")
INTAKE_PAGE = 2000
_INTAKE_BY_DOSE = bound_text(
    _INTAKE_COLUMNS + " and medication_id = :m and scheduled_at = :at for update"
)
_INTAKE_INSERT = bound_text(
    "insert into medication_intakes (patient_id, medication_id, client_id, scheduled_at,"
    " taken_at, status, note) values (:p, :medication_id, :c, :scheduled_at, :taken_at,"
    " :status, :note)"
    " on conflict do nothing returning id"
)
_INTAKE_MERGE = bound_text(
    "update medication_intakes set status = :status, taken_at = :taken_at,"
    " note = coalesce(note, :note) where patient_id = :p and id = :i"
)


_EXTRAS = bound_text(
    "select intake_id, status, taken_at, extra_recorder_role(id) as by_role"
    " from medication_intake_extra where patient_id = :p and intake_id = any(cast(:ids as uuid[]))"
    " order by taken_at, created_at"
)
_EXTRA_COUNT = bound_text(
    "select count(*) from medication_intake_extra where patient_id = :p and intake_id = :i"
)
EXTRA_MAX = 10  # as the database caps it (0027)
_EXTRA_INSERT = bound_text(
    "insert into medication_intake_extra (patient_id, intake_id, status, taken_at)"
    " values (:p, :i, :status, :taken_at) on conflict do nothing"
)


async def intake_extras(
    db: AsyncSession, patient_id: UUID, intake_ids: Sequence[UUID]
) -> dict[UUID, list[Row[Any]]]:
    """The other "taken" records of these doses (Q24), by dose."""
    if not intake_ids:
        return {}
    out: dict[UUID, list[Row[Any]]] = {}
    for row in await db.execute(_EXTRAS, {"p": patient_id, "ids": list(intake_ids)}):
        out.setdefault(row.intake_id, []).append(row)
    return out


_EXTRA_DELETE_MINE = bound_text(
    "delete from medication_intake_extra where patient_id = :p and intake_id = :i"
    " and recorded_by = app_user_id()"
)


async def delete_my_extras(db: AsyncSession, patient_id: UUID, intake_id: UUID) -> int:
    result = await db.execute(_EXTRA_DELETE_MINE, {"p": patient_id, "i": intake_id})
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


async def insert_intake_extra(
    db: AsyncSession, patient_id: UUID, intake_id: UUID, status: str, taken_at: object
) -> bool:
    """Kept unless the dose already has the most records kept (then the earlier ones stay)."""
    if (
        await db.execute(_EXTRA_COUNT, {"p": patient_id, "i": intake_id})
    ).scalar_one() >= EXTRA_MAX:
        return False
    result = await db.execute(
        _EXTRA_INSERT, {"p": patient_id, "i": intake_id, "status": status, "taken_at": taken_at}
    )
    return bool(result.rowcount)  # type: ignore[attr-defined]


async def intakes(
    db: AsyncSession,
    patient_id: UUID,
    since: datetime,
    until: datetime,
    medication_id: UUID | None,
) -> Sequence[Row[Any]]:
    params = {
        "p": patient_id,
        "since": since,
        "until": until,
        "m": medication_id,
        "limit": INTAKE_PAGE + 1,  # one more tells "too many" from "exactly the page"
    }
    return (await db.execute(_INTAKES_RANGE, params)).all()


async def intake(db: AsyncSession, patient_id: UUID, intake_id: UUID) -> Row[Any] | None:
    return (await db.execute(_INTAKE_BY_ID, {"p": patient_id, "i": intake_id})).one_or_none()


async def intake_by_client(db: AsyncSession, patient_id: UUID, client_id: UUID) -> Row[Any] | None:
    return (await db.execute(_INTAKE_BY_CLIENT, {"p": patient_id, "c": client_id})).one_or_none()


async def intake_for_dose(
    db: AsyncSession, patient_id: UUID, medication_id: UUID, scheduled_at: datetime
) -> Row[Any] | None:
    params = {"p": patient_id, "m": medication_id, "at": scheduled_at}
    return (await db.execute(_INTAKE_BY_DOSE, params)).one_or_none()


async def insert_intake(
    db: AsyncSession, patient_id: UUID, client_id: UUID, values: Mapping[str, object]
) -> UUID | None:
    params = {"p": patient_id, "c": client_id, **values}
    new_id: UUID | None = (await db.execute(_INTAKE_INSERT, params)).scalar_one_or_none()
    return new_id


async def merge_intake(
    db: AsyncSession, patient_id: UUID, intake_id: UUID, values: Mapping[str, object]
) -> int:
    result = await db.execute(_INTAKE_MERGE, {"p": patient_id, "i": intake_id, **values})
    return result.rowcount  # type: ignore[attr-defined, no-any-return]


# --- reminder time zone (0017) --------------------------------------------------------------

_ZONE_COLUMNS = "select id, timezone, effective_at, seq, created_at from patient_timezones"
# Switches that can place a dose in [since, until): those from a margin before `since` (a dose
# day starts up to 14 hours before UTC midnight) plus the one in force before them - an older
# switch never wins over that one (core.slots.place). Never the whole history.
_ZONES_WINDOW = bound_text(
    "("
    + _ZONE_COLUMNS
    + " where patient_id = :p and effective_at >= cast(:since as timestamptz) - interval '2 days'"
    " and effective_at < :until order by effective_at desc, seq desc limit :limit)"
    " union all (" + _ZONE_COLUMNS + " where patient_id = :p"
    " and effective_at < cast(:since as timestamptz) - interval '2 days'"
    " order by effective_at desc, seq desc limit 1)"
    " order by effective_at desc, seq desc"
)
# 20 a day by the owner + 40 by others (service caps) over a month, its 2-day margin and 7
# days of backdating: at most 60 * 40 = 2400; past this a summary keeps the newest
ZONE_WINDOW_MAX = 2500
_ZONES_RECENT = bound_text(
    "select count(*) filter (where recorded_by is distinct from app_user_id()),"
    " count(*) filter (where recorded_by = app_user_id()), is_owner(:p)"
    " from patient_timezones where patient_id = :p"
    " and created_at > now() - interval '24 hours'"
)
_ZONE_LATEST = bound_text("select max(effective_at) from patient_timezones where patient_id = :p")
# one switch at a time per profile: the daily cap and the order check see every committed row
_ZONE_LOCK = bound_text(
    "select pg_advisory_xact_lock("
    "hashtextextended('patient_timezones:' || cast(cast(:p as uuid) as text), 0))"
)
_ZONE_BY_CLIENT = bound_text(_ZONE_COLUMNS + " where patient_id = :p and client_id = :c")
_ZONE_INSERT = bound_text(
    "insert into patient_timezones (patient_id, client_id, timezone, effective_at)"
    " values (:p, :c, :timezone, :effective_at) on conflict do nothing returning id"
)


async def zones(
    db: AsyncSession, patient_id: UUID, since: datetime, until: datetime
) -> Sequence[Row[Any]]:
    """Newest first: the switches that can place a dose in [since, until) (see above); at most
    ZONE_WINDOW_MAX of them in the window (the newest) plus the one before."""
    params = {"p": patient_id, "since": since, "until": until, "limit": ZONE_WINDOW_MAX}
    return (await db.execute(_ZONES_WINDOW, params)).all()


async def lock_zones(db: AsyncSession, patient_id: UUID) -> None:
    await db.execute(_ZONE_LOCK, {"p": patient_id})


async def recent_zone_switches(db: AsyncSession, patient_id: UUID) -> tuple[int, int, bool]:
    """Switches written in the last 24 hours: (by others, by the acting user), and whether
    the acting user owns the profile."""
    row = (await db.execute(_ZONES_RECENT, {"p": patient_id})).one()
    return int(row[0]), int(row[1]), bool(row[2])


async def latest_zone_switch(db: AsyncSession, patient_id: UUID) -> datetime | None:
    found: datetime | None = (
        await db.execute(_ZONE_LATEST, {"p": patient_id})
    ).scalar_one_or_none()
    return found


async def zone_by_client(db: AsyncSession, patient_id: UUID, client_id: UUID) -> Row[Any] | None:
    return (await db.execute(_ZONE_BY_CLIENT, {"p": patient_id, "c": client_id})).one_or_none()


async def insert_zone(
    db: AsyncSession, patient_id: UUID, client_id: UUID, timezone: str, effective_at: datetime
) -> UUID | None:
    params = {"p": patient_id, "c": client_id, "timezone": timezone, "effective_at": effective_at}
    new_id: UUID | None = (await db.execute(_ZONE_INSERT, params)).scalar_one_or_none()
    return new_id


# --- monthly summary --------------------------------------------------------------------------

_SCHEDULED_INTAKES = bound_text(
    "select medication_id, scheduled_at, status, taken_at from medication_intakes"
    " where patient_id = :p and scheduled_at >= :since and scheduled_at < :until"
)


async def scheduled_intakes(
    db: AsyncSession, patient_id: UUID, since: datetime, until: datetime
) -> Sequence[Row[Any]]:
    """Records of planned doses in [since, until) - a month at most (≤ 12 doses a day per
    medication, so no page is needed)."""
    params = {"p": patient_id, "since": since, "until": until}
    return (await db.execute(_SCHEDULED_INTAKES, params)).all()


# --- catalog ----------------------------------------------------------------------------------

_CATALOG_SEARCH = bound_text(
    "select code, generic_mn, generic_en, brands, category, forms from medication_catalog"
    " where is_active and (:q = '' or generic_mn ilike :like or generic_en ilike :like"
    " or exists (select 1 from unnest(brands) b where b ilike :like))"
    " order by (category = 'immunosuppressant') desc, generic_mn limit 30"
)


async def search_catalog(db: AsyncSession, query: str) -> Sequence[Row[Any]]:
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return (await db.execute(_CATALOG_SEARCH, {"q": query, "like": f"%{escaped}%"})).all()


# --- audit ------------------------------------------------------------------------------------

_AUDIT = bound_text(
    "select audit_write(:action, :entity, cast(:eid as text), :pid,"
    " case when cast(:fields as jsonb) is null then null"
    " else jsonb_build_object('fields', cast(:fields as jsonb)) end)"
)


async def audit(  # noqa: PLR0917 - one audit row's parts, in audit_write's order
    db: AsyncSession,
    action: str,
    entity: str,
    entity_id: object,
    patient_id: UUID,
    fields: Sequence[str] | None = None,
) -> None:
    """Which record and which fields changed - never their values (CLAUDE.md rule 3)."""
    await db.execute(
        _AUDIT,
        {
            "action": action,
            "entity": entity,
            "eid": str(entity_id),
            "pid": patient_id,
            "fields": json.dumps(sorted(fields)) if fields is not None else None,
        },
    )
