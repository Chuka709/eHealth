"""SQL for clinical events, vitals, allergies, emergency contacts, appointments and questions
(migration 0018).

Every statement runs in the caller's user transaction (RLS); column lists are written out (no
SQL is assembled from strings). Values are bound; nothing here logs them.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Row
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import TextClause

from labtrack.db.sql import bound_text


class Table:
    """The statements of one record kind."""

    def __init__(  # noqa: PLR0917 - one table's statements
        self,
        fields: tuple[str, ...],
        select: str,
        insert: TextClause,
        update: TextClause,
        lock: TextClause,
        by_client: TextClause,
        delete: TextClause,
        count: TextClause,
        exists: TextClause,
    ) -> None:
        self.fields = fields
        self.select = select
        self.insert = insert
        self.update = update
        self.lock = lock
        self.by_client = by_client
        self.delete = delete
        self.count = count
        self.exists = exists


_EVENT_COLUMNS = (
    "select id, transplant_id, kind, title, started_on, ended_on, place, description, outcome,"
    " created_at, updated_at from clinical_events where patient_id = :p"
)
EVENTS = Table(
    fields=(
        "transplant_id",
        "kind",
        "title",
        "started_on",
        "ended_on",
        "place",
        "description",
        "outcome",
    ),
    select=_EVENT_COLUMNS,
    insert=bound_text(
        "insert into clinical_events (patient_id, client_id, transplant_id, kind, title,"
        " started_on, ended_on, place, description, outcome) values (:p, :client_id,"
        " :transplant_id, cast(:kind as clinical_event_kind), :title, :started_on, :ended_on,"
        " :place, :description, :outcome) on conflict (patient_id, client_id) do nothing"
        " returning id"
    ),
    update=bound_text(
        "update clinical_events set transplant_id = :transplant_id,"
        " kind = cast(:kind as clinical_event_kind), title = :title, started_on = :started_on,"
        " ended_on = :ended_on, place = :place, description = :description,"
        " outcome = :outcome where patient_id = :p and id = :i"
    ),
    lock=bound_text(_EVENT_COLUMNS + " and id = :i for update"),
    by_client=bound_text("select id from clinical_events where patient_id = :p and client_id = :c"),
    delete=bound_text("delete from clinical_events where patient_id = :p and id = :i"),
    count=bound_text("select count(*) from clinical_events where patient_id = :p"),
    exists=bound_text("select 1 from clinical_events where patient_id = :p and id = :i"),
)
EVENT_LIST = bound_text(_EVENT_COLUMNS + " order by started_on desc, created_at desc limit :n")
EVENT_ONE = bound_text(_EVENT_COLUMNS + " and id = :i")

_ALLERGY_COLUMNS = (
    "select id, substance, reaction, severity, noted_on, created_at, updated_at"
    " from allergies where patient_id = :p"
)
ALLERGIES = Table(
    fields=("substance", "reaction", "severity", "noted_on"),
    select=_ALLERGY_COLUMNS,
    insert=bound_text(
        "insert into allergies (patient_id, client_id, substance, reaction, severity, noted_on)"
        " values (:p, :client_id, :substance, :reaction, :severity, :noted_on)"
        " on conflict (patient_id, client_id) do nothing returning id"
    ),
    update=bound_text(
        "update allergies set substance = :substance, reaction = :reaction,"
        " severity = :severity, noted_on = :noted_on where patient_id = :p and id = :i"
    ),
    lock=bound_text(_ALLERGY_COLUMNS + " and id = :i for update"),
    by_client=bound_text("select id from allergies where patient_id = :p and client_id = :c"),
    delete=bound_text("delete from allergies where patient_id = :p and id = :i"),
    count=bound_text("select count(*) from allergies where patient_id = :p"),
    exists=bound_text("select 1 from allergies where patient_id = :p and id = :i"),
)
ALLERGY_LIST = bound_text(_ALLERGY_COLUMNS + " order by created_at limit :n")
ALLERGY_ONE = bound_text(_ALLERGY_COLUMNS + " and id = :i")

_CONTACT_COLUMNS = (
    "select id, name, relation, phone, is_transplant_center, sort_order, created_at,"
    " updated_at from emergency_contacts where patient_id = :p"
)
CONTACTS = Table(
    fields=("name", "relation", "phone", "is_transplant_center", "sort_order"),
    select=_CONTACT_COLUMNS,
    insert=bound_text(
        "insert into emergency_contacts (patient_id, client_id, name, relation, phone,"
        " is_transplant_center, sort_order) values (:p, :client_id, :name, :relation, :phone,"
        " :is_transplant_center, :sort_order) on conflict (patient_id, client_id) do nothing"
        " returning id"
    ),
    update=bound_text(
        "update emergency_contacts set name = :name, relation = :relation, phone = :phone,"
        " is_transplant_center = :is_transplant_center, sort_order = :sort_order"
        " where patient_id = :p and id = :i"
    ),
    lock=bound_text(_CONTACT_COLUMNS + " and id = :i for update"),
    by_client=bound_text(
        "select id from emergency_contacts where patient_id = :p and client_id = :c"
    ),
    delete=bound_text("delete from emergency_contacts where patient_id = :p and id = :i"),
    count=bound_text("select count(*) from emergency_contacts where patient_id = :p"),
    exists=bound_text("select 1 from emergency_contacts where patient_id = :p and id = :i"),
)
CONTACT_LIST = bound_text(_CONTACT_COLUMNS + " order by sort_order, created_at limit :n")
CONTACT_ONE = bound_text(_CONTACT_COLUMNS + " and id = :i")

_APPOINTMENT_COLUMNS = (
    "select id, kind, title, scheduled_at, place, notes, reminder_offsets_min, status,"
    " created_at, updated_at from appointments where patient_id = :p"
)
APPOINTMENTS = Table(
    fields=("kind", "title", "scheduled_at", "place", "notes", "reminder_offsets_min", "status"),
    select=_APPOINTMENT_COLUMNS,
    insert=bound_text(
        "insert into appointments (patient_id, client_id, kind, title, scheduled_at, place,"
        " notes, reminder_offsets_min, status) values (:p, :client_id, :kind, :title,"
        " :scheduled_at, :place, :notes, :reminder_offsets_min, :status)"
        " on conflict (patient_id, client_id) do nothing returning id"
    ),
    update=bound_text(
        "update appointments set kind = :kind, title = :title, scheduled_at = :scheduled_at,"
        " place = :place, notes = :notes, reminder_offsets_min = :reminder_offsets_min,"
        " status = :status where patient_id = :p and id = :i"
    ),
    lock=bound_text(_APPOINTMENT_COLUMNS + " and id = :i for update"),
    by_client=bound_text("select id from appointments where patient_id = :p and client_id = :c"),
    delete=bound_text("delete from appointments where patient_id = :p and id = :i"),
    count=bound_text("select count(*) from appointments where patient_id = :p"),
    exists=bound_text("select 1 from appointments where patient_id = :p and id = :i"),
)
APPOINTMENT_LIST = bound_text(
    _APPOINTMENT_COLUMNS + " and scheduled_at >= :since order by scheduled_at limit :n"
)
APPOINTMENT_ONE = bound_text(_APPOINTMENT_COLUMNS + " and id = :i")

_QUESTION_COLUMNS = (
    "select id, text, answer, appointment_id, status, created_at, updated_at"
    " from doctor_questions where patient_id = :p"
)
QUESTIONS = Table(
    fields=("text", "answer", "appointment_id", "status"),
    select=_QUESTION_COLUMNS,
    insert=bound_text(
        "insert into doctor_questions (patient_id, client_id, text, answer, appointment_id,"
        " status) values (:p, :client_id, :text, :answer, :appointment_id, :status)"
        " on conflict (patient_id, client_id) do nothing returning id"
    ),
    update=bound_text(
        "update doctor_questions set text = :text, answer = :answer,"
        " appointment_id = :appointment_id, status = :status where patient_id = :p and id = :i"
    ),
    lock=bound_text(_QUESTION_COLUMNS + " and id = :i for update"),
    by_client=bound_text(
        "select id from doctor_questions where patient_id = :p and client_id = :c"
    ),
    delete=bound_text("delete from doctor_questions where patient_id = :p and id = :i"),
    count=bound_text("select count(*) from doctor_questions where patient_id = :p"),
    exists=bound_text("select 1 from doctor_questions where patient_id = :p and id = :i"),
)
QUESTION_LIST = bound_text(
    _QUESTION_COLUMNS + " order by (status = 'open') desc, created_at desc limit :n"
)
QUESTION_ONE = bound_text(_QUESTION_COLUMNS + " and id = :i")


async def rows(
    db: AsyncSession, sql: TextClause, patient_id: UUID, **params: object
) -> Sequence[Row[Any]]:
    return (await db.execute(sql, {"p": patient_id, **params})).all()


async def insert(
    db: AsyncSession, table: Table, patient_id: UUID, client_id: UUID, values: Mapping[str, object]
) -> UUID | None:
    """The new id, or None when this client_id was already stored (a retried request)."""
    params = {"p": patient_id, "client_id": client_id, **values}
    new_id: UUID | None = (await db.execute(table.insert, params)).scalar_one_or_none()
    return new_id


async def update(
    db: AsyncSession, table: Table, patient_id: UUID, row_id: UUID, values: Mapping[str, object]
) -> int:
    params = {"p": patient_id, "i": row_id, **values}
    return (await db.execute(table.update, params)).rowcount  # type: ignore[attr-defined, no-any-return]


async def lock(db: AsyncSession, table: Table, patient_id: UUID, row_id: UUID) -> Row[Any] | None:
    return (await db.execute(table.lock, {"p": patient_id, "i": row_id})).one_or_none()


async def by_client(
    db: AsyncSession, table: Table, patient_id: UUID, client_id: UUID
) -> UUID | None:
    found: UUID | None = (
        await db.execute(table.by_client, {"p": patient_id, "c": client_id})
    ).scalar_one_or_none()
    return found


async def delete(db: AsyncSession, table: Table, patient_id: UUID, row_id: UUID) -> int:
    return (await db.execute(table.delete, {"p": patient_id, "i": row_id})).rowcount  # type: ignore[attr-defined, no-any-return]


async def exists(db: AsyncSession, table: Table, patient_id: UUID, row_id: UUID) -> bool:
    found = (await db.execute(table.exists, {"p": patient_id, "i": row_id})).first()
    return found is not None


_KIND_LOCK = bound_text(
    "select pg_advisory_xact_lock(hashtextextended("
    "'health:' || cast(:k as text) || ':' || cast(cast(:p as uuid) as text), 0))"
)


async def lock_kind(db: AsyncSession, patient_id: UUID, kind: str) -> None:
    """One create at a time per profile and kind: the caps hold under parallel requests."""
    await db.execute(_KIND_LOCK, {"p": patient_id, "k": kind})


async def count(db: AsyncSession, table: Table, patient_id: UUID) -> int:
    n: int = (await db.execute(table.count, {"p": patient_id})).scalar_one()
    return n


# --- vitals (entered or deleted, never edited) -----------------------------------------------

_VITAL_COLUMNS = (
    "select id, kind, value, unit, measured_at, group_id, source, note, created_at"
    " from vitals where patient_id = :p"
)
VITAL_PAGE = 2000
_VITALS_RANGE = bound_text(
    _VITAL_COLUMNS + " and measured_at >= :since and measured_at < :until"
    " and (cast(:kind as vital_kind) is null or kind = cast(:kind as vital_kind))"
    " order by measured_at desc, kind limit :n"
)
_VITALS_LATEST = bound_text(
    "select distinct on (kind) id, kind, value, unit, measured_at, group_id, source, note,"
    " created_at from vitals where patient_id = :p order by kind, measured_at desc, created_at desc"
)
_VITAL_INSERT = bound_text(
    "insert into vitals (patient_id, client_id, kind, value, unit, measured_at, group_id, note)"
    " values (:p, :c, cast(:kind as vital_kind), :value, :unit, :measured_at, :group_id, :note)"
    " on conflict (patient_id, client_id) do nothing returning id"
)
_VITAL_BY_CLIENTS = bound_text(
    _VITAL_COLUMNS + " and client_id = any(cast(:cs as uuid[])) order by kind"
)
_VITAL_DELETE = bound_text("delete from vitals where patient_id = :p and id = :i")
_VITAL_EXISTS = bound_text("select 1 from vitals where patient_id = :p and id = :i")
# a reading's client_id is its group id (several kinds) - or one row's derived client_id
_VITAL_GROUP = bound_text("select kind from vitals where patient_id = :p and group_id = :g")
_VITAL_COUNT_RECENT = bound_text(
    "select count(*) from vitals where patient_id = :p and created_at > now() - interval '1 day'"
)


async def vitals(
    db: AsyncSession, patient_id: UUID, since: datetime, until: datetime, kind: str | None
) -> Sequence[Row[Any]]:
    params = {"p": patient_id, "since": since, "until": until, "kind": kind, "n": VITAL_PAGE + 1}
    return (await db.execute(_VITALS_RANGE, params)).all()


async def latest_vitals(db: AsyncSession, patient_id: UUID) -> Sequence[Row[Any]]:
    return (await db.execute(_VITALS_LATEST, {"p": patient_id})).all()


async def insert_vital(
    db: AsyncSession, patient_id: UUID, client_id: UUID, values: Mapping[str, object]
) -> UUID | None:
    params = {"p": patient_id, "c": client_id, **values}
    new_id: UUID | None = (await db.execute(_VITAL_INSERT, params)).scalar_one_or_none()
    return new_id


async def vitals_by_clients(
    db: AsyncSession, patient_id: UUID, client_ids: Sequence[UUID]
) -> Sequence[Row[Any]]:
    return (await db.execute(_VITAL_BY_CLIENTS, {"p": patient_id, "cs": list(client_ids)})).all()


async def delete_vital(db: AsyncSession, patient_id: UUID, vital_id: UUID) -> int:
    return (await db.execute(_VITAL_DELETE, {"p": patient_id, "i": vital_id})).rowcount  # type: ignore[attr-defined, no-any-return]


async def vital_exists(db: AsyncSession, patient_id: UUID, vital_id: UUID) -> bool:
    return (await db.execute(_VITAL_EXISTS, {"p": patient_id, "i": vital_id})).first() is not None


async def vital_group_kinds(db: AsyncSession, patient_id: UUID, group_id: UUID) -> set[str]:
    rows = (await db.execute(_VITAL_GROUP, {"p": patient_id, "g": group_id})).all()
    return {str(r.kind) for r in rows}


async def recent_vitals(db: AsyncSession, patient_id: UUID) -> int:
    n: int = (await db.execute(_VITAL_COUNT_RECENT, {"p": patient_id})).scalar_one()
    return n
