"""A profile's clinical events, vitals, allergies, emergency contacts, appointments and
questions for the doctor (Phase 2.6; docs/08).

Routes hang under /patients/{patient_id} and take PatientReadDb / PatientWriteDb, as the
records routes. Nothing here judges a value: vitals are checked only for being a plain
number in a plausible range for their kind (core/vitals.py), never against a normal range.
"""

import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Response, status
from pydantic import AfterValidator, BaseModel, Field, PlainSerializer, model_validator
from sqlalchemy.exc import DBAPIError

from labtrack.api.caregivers import _pg
from labtrack.api.deps import PatientReadDb, PatientWriteDb
from labtrack.api.errors import AppError, ErrorBody
from labtrack.api.records import Long, OptionalPastDate, PastDate, Short, _Strict
from labtrack.core.vitals import RULES, VitalError, VitalKind, check_reading, parse_vital
from labtrack.health import repository as repo
from labtrack.health import service

router = APIRouter(prefix="/patients/{patient_id}", tags=["health"])

_ERRORS: dict[int | str, dict[str, object]] = {
    s: {"model": ErrorBody} for s in (401, 403, 404, 409, 422, 429)
}
_LIST_MAX = 1000  # every kind's cap is at or below it (health/service.KINDS)

Number = Annotated[
    Decimal, PlainSerializer(lambda d: format(d, "f"), return_type=str, when_used="json")
]


def _since_1900(value: date | None) -> date | None:
    if value is not None and value < date(1900, 1, 1):
        raise ValueError("date")
    return value


def _created(response: Response, saved: service.Saved) -> None:
    if not saved.created:
        response.status_code = status.HTTP_200_OK  # a retry: the stored record


# --- clinical events ------------------------------------------------------------------------

EventKind = Literal[
    "biopsy",
    "rejection",
    "infection",
    "hospitalization",
    "dialysis",
    "plasmapheresis",
    "ivig",
    "surgery",
    "procedure",
    "vaccination",
    "complication",
    "other",
]


class EventIn(_Strict):
    transplant_id: UUID | None = None
    kind: EventKind
    title: Short
    started_on: PastDate
    ended_on: OptionalPastDate = None
    place: Short | None = None
    description: Long | None = None
    outcome: Long | None = None

    @model_validator(mode="after")
    def _dates(self) -> "EventIn":
        if self.ended_on is not None and self.ended_on < self.started_on:
            raise ValueError("ended_on")
        return self


class EventCreate(EventIn):
    client_id: UUID


class EventOut(BaseModel):
    id: UUID
    transplant_id: UUID | None
    kind: str
    title: str
    started_on: date
    ended_on: date | None
    place: str | None
    description: str | None
    outcome: str | None
    created_at: datetime
    updated_at: datetime | None


@router.get("/events", response_model=list[EventOut], responses=_ERRORS)
async def list_events(patient_id: UUID, db: PatientReadDb) -> list[EventOut]:
    """Newest first."""
    rows = await repo.rows(db, repo.EVENT_LIST, patient_id, n=_LIST_MAX)
    return [EventOut.model_validate(r._mapping) for r in rows]


async def _event(db: PatientReadDb, patient_id: UUID, event_id: UUID) -> EventOut:
    rows = await repo.rows(db, repo.EVENT_ONE, patient_id, i=event_id)
    if not rows:
        raise AppError(404, "event.not_found")
    return EventOut.model_validate(rows[0]._mapping)


@router.post(
    "/events",
    response_model=EventOut,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"model": EventOut}, **_ERRORS},
)
async def create_event(
    patient_id: UUID, body: EventCreate, db: PatientWriteDb, response: Response
) -> EventOut:
    saved = await service.create(
        db, "events", patient_id, body.client_id, body.model_dump(exclude={"client_id"})
    )
    _created(response, saved)
    return await _event(db, patient_id, saved.id)


@router.put("/events/{event_id}", response_model=EventOut, responses=_ERRORS)
async def replace_event(
    patient_id: UUID, event_id: UUID, body: EventIn, db: PatientWriteDb
) -> EventOut:
    await service.update(db, "events", patient_id, event_id, body.model_dump())
    return await _event(db, patient_id, event_id)


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS)
async def delete_event(patient_id: UUID, event_id: UUID, db: PatientWriteDb) -> Response:
    await service.delete(db, "events", patient_id, event_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- allergies ------------------------------------------------------------------------------


class AllergyIn(_Strict):
    substance: Short
    reaction: Short | None = None
    severity: Literal["mild", "moderate", "severe", "unknown"] | None = None
    noted_on: Annotated[date | None, AfterValidator(_since_1900)] = None

    @model_validator(mode="after")
    def _not_future(self) -> "AllergyIn":
        if self.noted_on is not None and self.noted_on > datetime.now(UTC).date() + timedelta(
            days=1
        ):
            raise ValueError("noted_on")
        return self


class AllergyCreate(AllergyIn):
    client_id: UUID


class AllergyOut(BaseModel):
    id: UUID
    substance: str
    reaction: str | None
    severity: str | None
    noted_on: date | None
    created_at: datetime
    updated_at: datetime | None


async def _allergy(db: PatientReadDb, patient_id: UUID, allergy_id: UUID) -> AllergyOut:
    rows = await repo.rows(db, repo.ALLERGY_ONE, patient_id, i=allergy_id)
    if not rows:
        raise AppError(404, "allergy.not_found")
    return AllergyOut.model_validate(rows[0]._mapping)


@router.get("/allergies", response_model=list[AllergyOut], responses=_ERRORS)
async def list_allergies(patient_id: UUID, db: PatientReadDb) -> list[AllergyOut]:
    rows = await repo.rows(db, repo.ALLERGY_LIST, patient_id, n=_LIST_MAX)
    return [AllergyOut.model_validate(r._mapping) for r in rows]


@router.post(
    "/allergies",
    response_model=AllergyOut,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"model": AllergyOut}, **_ERRORS},
)
async def create_allergy(
    patient_id: UUID, body: AllergyCreate, db: PatientWriteDb, response: Response
) -> AllergyOut:
    saved = await service.create(
        db, "allergies", patient_id, body.client_id, body.model_dump(exclude={"client_id"})
    )
    _created(response, saved)
    return await _allergy(db, patient_id, saved.id)


@router.put("/allergies/{allergy_id}", response_model=AllergyOut, responses=_ERRORS)
async def replace_allergy(
    patient_id: UUID, allergy_id: UUID, body: AllergyIn, db: PatientWriteDb
) -> AllergyOut:
    await service.update(db, "allergies", patient_id, allergy_id, body.model_dump())
    return await _allergy(db, patient_id, allergy_id)


@router.delete("/allergies/{allergy_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS)
async def delete_allergy(patient_id: UUID, allergy_id: UUID, db: PatientWriteDb) -> Response:
    await service.delete(db, "allergies", patient_id, allergy_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class NoKnownAllergiesOut(BaseModel):
    """A dated "no known allergies" (Q39). Null: not confirmed - which is not the same as no
    allergy (H17); the app says "none recorded" then."""

    confirmed_on: date | None


@router.get("/no-known-allergies", response_model=NoKnownAllergiesOut, responses=_ERRORS)
async def get_no_known_allergies(patient_id: UUID, db: PatientReadDb) -> NoKnownAllergiesOut:
    rows = await repo.rows(db, repo.NO_KNOWN_ALLERGIES, patient_id)
    return NoKnownAllergiesOut(confirmed_on=rows[0].confirmed_on if rows else None)


@router.put("/no-known-allergies", response_model=NoKnownAllergiesOut, responses=_ERRORS)
async def confirm_no_known_allergies(patient_id: UUID, db: PatientWriteDb) -> NoKnownAllergiesOut:
    """Confirmed today (again). 409 while an allergy is recorded; adding one later ends it."""
    try:
        day = (await db.execute(repo.NKA_CONFIRM, {"p": patient_id})).scalar_one()
    except DBAPIError as exc:
        state, _ = _pg(exc)
        if state == "23514":
            raise AppError(409, "allergy.recorded") from None
        if state == "42501":
            raise AppError(403, "patient.read_only") from None
        raise
    return NoKnownAllergiesOut(confirmed_on=day)


@router.delete("/no-known-allergies", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS)
async def clear_no_known_allergies(patient_id: UUID, db: PatientWriteDb) -> Response:
    try:
        await db.execute(repo.NKA_CLEAR, {"p": patient_id})  # nothing to clear is fine
    except DBAPIError as exc:
        if _pg(exc)[0] == "42501":
            raise AppError(403, "patient.read_only") from None
        raise
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- emergency contacts ---------------------------------------------------------------------

# as written, dialled as written: digits, an optional leading +, spaces, dashes, brackets
_PHONE = re.compile(r"^\+?[0-9][0-9 ()-]{3,22}[0-9]$")


def _phone(value: str) -> str:
    value = value.strip()
    if not _PHONE.match(value):
        raise ValueError("phone")
    return value


Phone = Annotated[str, AfterValidator(_phone)]


class ContactIn(_Strict):
    name: Short
    relation: Short | None = None
    phone: Phone
    is_transplant_center: bool = False
    sort_order: Annotated[int, Field(ge=0, le=100)] = 0


class ContactCreate(ContactIn):
    client_id: UUID


class ContactOut(BaseModel):
    id: UUID
    name: str
    relation: str | None
    phone: str
    is_transplant_center: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime | None


async def _contact(db: PatientReadDb, patient_id: UUID, contact_id: UUID) -> ContactOut:
    rows = await repo.rows(db, repo.CONTACT_ONE, patient_id, i=contact_id)
    if not rows:
        raise AppError(404, "contact.not_found")
    return ContactOut.model_validate(rows[0]._mapping)


@router.get("/contacts", response_model=list[ContactOut], responses=_ERRORS)
async def list_contacts(patient_id: UUID, db: PatientReadDb) -> list[ContactOut]:
    rows = await repo.rows(db, repo.CONTACT_LIST, patient_id, n=_LIST_MAX)
    return [ContactOut.model_validate(r._mapping) for r in rows]


@router.post(
    "/contacts",
    response_model=ContactOut,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"model": ContactOut}, **_ERRORS},
)
async def create_contact(
    patient_id: UUID, body: ContactCreate, db: PatientWriteDb, response: Response
) -> ContactOut:
    saved = await service.create(
        db, "contacts", patient_id, body.client_id, body.model_dump(exclude={"client_id"})
    )
    _created(response, saved)
    return await _contact(db, patient_id, saved.id)


@router.put("/contacts/{contact_id}", response_model=ContactOut, responses=_ERRORS)
async def replace_contact(
    patient_id: UUID, contact_id: UUID, body: ContactIn, db: PatientWriteDb
) -> ContactOut:
    await service.update(db, "contacts", patient_id, contact_id, body.model_dump())
    return await _contact(db, patient_id, contact_id)


@router.delete("/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS)
async def delete_contact(patient_id: UUID, contact_id: UUID, db: PatientWriteDb) -> Response:
    await service.delete(db, "contacts", patient_id, contact_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- appointments ---------------------------------------------------------------------------

_APPOINTMENT_PAST = timedelta(days=5 * 366)
_APPOINTMENT_AHEAD = timedelta(days=2 * 366)


class AppointmentIn(_Strict):
    kind: Literal["lab", "clinic_visit", "biopsy", "imaging", "other"]
    title: Short
    scheduled_at: datetime
    place: Short | None = None
    notes: Long | None = None
    # minutes before: 1 day and 2 hours unless the user chooses; at most 4, at most 7 days
    reminder_offsets_min: Annotated[
        list[Annotated[int, Field(ge=0, le=10080)]], Field(max_length=4)
    ] = Field(default_factory=lambda: [1440, 120])
    status: Literal["planned", "done", "cancelled"] = "planned"

    @model_validator(mode="after")
    def _when(self) -> "AppointmentIn":
        if self.scheduled_at.tzinfo is None:
            raise ValueError("timezone")
        now = datetime.now(UTC)
        if not now - _APPOINTMENT_PAST <= self.scheduled_at <= now + _APPOINTMENT_AHEAD:
            raise ValueError("scheduled_at")
        if len(set(self.reminder_offsets_min)) != len(self.reminder_offsets_min):
            raise ValueError("reminder_offsets_min")
        self.scheduled_at = self.scheduled_at.astimezone(UTC).replace(second=0, microsecond=0)
        self.reminder_offsets_min = sorted(self.reminder_offsets_min, reverse=True)
        return self


class AppointmentCreate(AppointmentIn):
    client_id: UUID


class AppointmentOut(BaseModel):
    id: UUID
    kind: str
    title: str
    scheduled_at: datetime
    place: str | None
    notes: str | None
    reminder_offsets_min: list[int]
    status: str
    created_at: datetime
    updated_at: datetime | None


async def _appointment(db: PatientReadDb, patient_id: UUID, appointment_id: UUID) -> AppointmentOut:
    rows = await repo.rows(db, repo.APPOINTMENT_ONE, patient_id, i=appointment_id)
    if not rows:
        raise AppError(404, "appointment.not_found")
    return AppointmentOut.model_validate(rows[0]._mapping)


@router.get("/appointments", response_model=list[AppointmentOut], responses=_ERRORS)
async def list_appointments(
    patient_id: UUID,
    db: PatientReadDb,
    since: Annotated[datetime | None, Query(alias="from")] = None,
) -> list[AppointmentOut]:
    """In time order, from `from` (default: 30 days ago)."""
    start = since or datetime.now(UTC) - timedelta(days=30)
    if start.tzinfo is None:
        raise AppError(422, "validation")
    rows = await repo.rows(db, repo.APPOINTMENT_LIST, patient_id, since=start, n=_LIST_MAX)
    return [AppointmentOut.model_validate(r._mapping) for r in rows]


@router.post(
    "/appointments",
    response_model=AppointmentOut,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"model": AppointmentOut}, **_ERRORS},
)
async def create_appointment(
    patient_id: UUID, body: AppointmentCreate, db: PatientWriteDb, response: Response
) -> AppointmentOut:
    saved = await service.create(
        db, "appointments", patient_id, body.client_id, body.model_dump(exclude={"client_id"})
    )
    _created(response, saved)
    return await _appointment(db, patient_id, saved.id)


@router.put("/appointments/{appointment_id}", response_model=AppointmentOut, responses=_ERRORS)
async def replace_appointment(
    patient_id: UUID, appointment_id: UUID, body: AppointmentIn, db: PatientWriteDb
) -> AppointmentOut:
    await service.update(db, "appointments", patient_id, appointment_id, body.model_dump())
    return await _appointment(db, patient_id, appointment_id)


@router.delete(
    "/appointments/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS
)
async def delete_appointment(
    patient_id: UUID, appointment_id: UUID, db: PatientWriteDb
) -> Response:
    await service.delete(db, "appointments", patient_id, appointment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- questions for the doctor ---------------------------------------------------------------


class QuestionIn(_Strict):
    text: Long
    answer: Long | None = None
    appointment_id: UUID | None = None
    status: Literal["open", "answered", "dropped"] = "open"


class QuestionCreate(QuestionIn):
    client_id: UUID


class QuestionOut(BaseModel):
    id: UUID
    text: str
    answer: str | None
    appointment_id: UUID | None
    status: str
    created_at: datetime
    updated_at: datetime | None


async def _question(db: PatientReadDb, patient_id: UUID, question_id: UUID) -> QuestionOut:
    rows = await repo.rows(db, repo.QUESTION_ONE, patient_id, i=question_id)
    if not rows:
        raise AppError(404, "question.not_found")
    return QuestionOut.model_validate(rows[0]._mapping)


@router.get("/questions", response_model=list[QuestionOut], responses=_ERRORS)
async def list_questions(patient_id: UUID, db: PatientReadDb) -> list[QuestionOut]:
    """Open ones first, newest first."""
    rows = await repo.rows(db, repo.QUESTION_LIST, patient_id, n=_LIST_MAX)
    return [QuestionOut.model_validate(r._mapping) for r in rows]


@router.post(
    "/questions",
    response_model=QuestionOut,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"model": QuestionOut}, **_ERRORS},
)
async def create_question(
    patient_id: UUID, body: QuestionCreate, db: PatientWriteDb, response: Response
) -> QuestionOut:
    saved = await service.create(
        db, "questions", patient_id, body.client_id, body.model_dump(exclude={"client_id"})
    )
    _created(response, saved)
    return await _question(db, patient_id, saved.id)


@router.put("/questions/{question_id}", response_model=QuestionOut, responses=_ERRORS)
async def replace_question(
    patient_id: UUID, question_id: UUID, body: QuestionIn, db: PatientWriteDb
) -> QuestionOut:
    await service.update(db, "questions", patient_id, question_id, body.model_dump())
    return await _question(db, patient_id, question_id)


@router.delete(
    "/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS
)
async def delete_question(patient_id: UUID, question_id: UUID, db: PatientWriteDb) -> Response:
    await service.delete(db, "questions", patient_id, question_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- vitals ---------------------------------------------------------------------------------

_VITAL_WINDOW = timedelta(days=400)
_BP = {"bp_systolic", "bp_diastolic", "pulse"}


class VitalItemIn(_Strict):
    kind: VitalKind
    value: Annotated[str, Field(min_length=1, max_length=10)]  # an exact number as written


class VitalsIn(_Strict):
    """One reading: a single kind, or blood pressure (systolic + diastolic, pulse optional)
    measured together."""

    client_id: UUID
    measured_at: datetime
    note: Short | None = None
    items: Annotated[list[VitalItemIn], Field(min_length=1, max_length=3)]

    @model_validator(mode="after")
    def _shape(self) -> "VitalsIn":
        if self.measured_at.tzinfo is None:
            raise ValueError("timezone")
        now = datetime.now(UTC)
        if not datetime(2000, 1, 1, tzinfo=UTC) <= self.measured_at <= now + timedelta(minutes=5):
            raise ValueError("measured_at")
        kinds = [i.kind for i in self.items]
        if len(set(kinds)) != len(kinds):
            raise ValueError("items")
        if len(kinds) > 1 and not (
            set(kinds) <= _BP and {"bp_systolic", "bp_diastolic"} <= set(kinds)
        ):
            raise ValueError("items")  # several kinds only as one blood-pressure reading
        if set(kinds) & {"bp_systolic", "bp_diastolic"} and len(kinds) == 1:
            raise ValueError("items")  # systolic and diastolic come together
        return self


class VitalOut(BaseModel):
    id: UUID
    kind: str
    value: Number
    unit: str
    measured_at: datetime
    group_id: UUID | None
    source: str
    note: str | None
    created_at: datetime


def _values(body: VitalsIn) -> list[dict[str, Any]]:
    """Each item as stored, or the reason it is refused (never a normal range)."""
    out = []
    parsed: dict[str, Decimal] = {}
    for item in body.items:
        try:
            value = parse_vital(item.kind, item.value)
        except VitalError as exc:
            if exc.reason == "format":
                raise AppError(422, "vital.format") from None
            if item.kind == "glucose":
                # out of range is most often a mg/dL meter: say which unit is meant
                raise AppError(422, "vital.glucose_unit") from None
            raise AppError(422, "vital.implausible") from None
        parsed[item.kind] = value
        out.append({"kind": item.kind, "value": value, "unit": RULES[item.kind].unit})
    try:
        check_reading(parsed)
    except VitalError:
        raise AppError(422, "vital.bp_order") from None
    return out


@router.get("/vitals", response_model=list[VitalOut], responses=_ERRORS)
async def list_vitals(
    patient_id: UUID,
    db: PatientReadDb,
    since: Annotated[datetime, Query(alias="from")],
    until: Annotated[datetime, Query(alias="to")],
    kind: VitalKind | None = None,
) -> list[VitalOut]:
    """Readings in [from, to), newest first: at most 400 days and 5000 rows (more is 422
    `vital.too_many` - ask for a shorter range; never cut short silently)."""
    if since.tzinfo is None or until.tzinfo is None or not since < until <= since + _VITAL_WINDOW:
        raise AppError(422, "validation")
    rows = await repo.vitals(db, patient_id, since, until, kind)
    if len(rows) > repo.VITAL_PAGE:
        raise AppError(422, "vital.too_many")
    return [VitalOut.model_validate(r._mapping) for r in rows]


@router.get("/vitals/latest", response_model=list[VitalOut], responses=_ERRORS)
async def latest_vitals(patient_id: UUID, db: PatientReadDb) -> list[VitalOut]:
    """The last reading of each kind."""
    return [VitalOut.model_validate(r._mapping) for r in await repo.latest_vitals(db, patient_id)]


@router.post(
    "/vitals",
    response_model=list[VitalOut],
    status_code=status.HTTP_201_CREATED,
    responses={200: {"model": list[VitalOut]}, **_ERRORS},
)
async def record_vitals(
    patient_id: UUID, body: VitalsIn, db: PatientWriteDb, response: Response
) -> list[VitalOut]:
    rows, created = await service.record_vitals(
        db,
        patient_id,
        body.client_id,
        _values(body),
        {"measured_at": body.measured_at, "note": body.note},
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return [VitalOut.model_validate(r._mapping) for r in rows]


@router.delete("/vitals/{vital_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS)
async def delete_vital(patient_id: UUID, vital_id: UUID, db: PatientWriteDb) -> Response:
    """A wrong reading is deleted and entered again (never edited)."""
    await service.delete_vital(db, patient_id, vital_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
