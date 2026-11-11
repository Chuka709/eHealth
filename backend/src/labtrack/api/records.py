"""A profile's transplants, medications, dose history and intakes (Phase 2.2; docs/08 "Эм").

Routes hang under /patients/{patient_id} and take PatientReadDb / PatientWriteDb (profile
access, then a minor's profile consents). Amounts travel as exact strings (CLAUDE.md rule 7);
dates are validated against the Ulaanbaatar calendar. Nothing here suggests or checks a dose:
the amounts, units and schedules are the doctor's instruction as the user enters it.

Input models validate; output models only describe (a stored row is never re-judged, so one
odd row cannot break a whole list).
"""

import re
import unicodedata
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from functools import cache
from typing import Annotated, Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, available_timezones

from fastapi import APIRouter, Query, Response, status
from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    StringConstraints,
    model_validator,
)

from labtrack.api.deps import PatientReadDb, PatientWriteDb, PhiDb
from labtrack.api.errors import AppError, ErrorBody
from labtrack.core.medications import (
    AmountError,
    ScheduleError,
    has_amounts,
    is_current,
    next_regimen,
    normalize_schedule,
    parse_amount,
    regimen_on,
)
from labtrack.core.slots import HOME_TIMEZONE, RECORDING_WINDOW, Summary
from labtrack.core.timeline import elapsed_since
from labtrack.records import repository as repo
from labtrack.records import service

router = APIRouter(prefix="/patients/{patient_id}", tags=["records"])
catalog_router = APIRouter(prefix="/medication-catalog", tags=["records"])

_ERRORS: dict[int | str, dict[str, object]] = {
    s: {"model": ErrorBody} for s in (401, 403, 404, 409, 422)
}
_LOCAL = ZoneInfo("Asia/Ulaanbaatar")
_YEAR_AHEAD = timedelta(days=366)


def _today() -> date:
    return datetime.now(_LOCAL).date()


# --- field types --------------------------------------------------------------------------------

# control, format (bidi, zero-width), lone surrogates, private use, unassigned, and the
# line/paragraph separators U+2028/U+2029 (an invisible line break in one-line text)
_REFUSED_CATEGORIES = {"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"}


def _plain_text(multiline: bool) -> Callable[[str], str]:
    allowed = {chr(10)} if multiline else set()  # newline

    def check(value: str) -> str:
        for ch in value:
            if unicodedata.category(ch) in _REFUSED_CATEGORIES and ch not in allowed:
                raise ValueError("text")
        return value

    return check


Short = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
    AfterValidator(_plain_text(multiline=False)),
]
Long = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=4000),
    AfterValidator(_plain_text(multiline=True)),
]
Serostatus = Literal["pos", "neg", "unknown"]
BloodType = Literal["O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-", "unknown"]
# one spelling per unit: no µg / мкг / mcg mix-up (a 1000-fold error); "other" + the user's text
DoseUnit = Literal[
    "mg",
    "mcg",
    "g",
    "ml",
    "iu",
    "unit",
    "tablet",
    "capsule",
    "drop",
    "puff",
    "sachet",
    "patch",
    "other",
]


def _not_future(value: date | None) -> date | None:
    if value is not None and not (date(1950, 1, 1) <= value <= _today()):
        raise ValueError("date")
    return value


def _within_a_year(value: date | None) -> date | None:
    if value is not None and not (date(1950, 1, 1) <= value <= _today() + _YEAR_AHEAD):
        raise ValueError("date")
    return value


PastDate = Annotated[date, AfterValidator(_not_future)]
OptionalPastDate = Annotated[date | None, AfterValidator(_not_future)]
OptionalPlanDate = Annotated[date | None, AfterValidator(_within_a_year)]


def _amount(value: object) -> Decimal:
    # an exact string only: a JSON number (2.4999999) never becomes a dose
    if not isinstance(value, str):
        raise ValueError("amount as string")  # noqa: TRY004 - pydantic reports ValueError
    try:
        return parse_amount(value)
    except AmountError as exc:
        raise ValueError("amount") from exc


DoseAmount = Annotated[
    Decimal,
    BeforeValidator(_amount),
    PlainSerializer(str, return_type=str, when_used="json"),
]
DoseOut = Annotated[
    Decimal, PlainSerializer(lambda d: format(d, "f"), return_type=str, when_used="json")
]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _fields(body: BaseModel, names: tuple[str, ...]) -> dict[str, object]:
    return {name: getattr(body, name) for name in names}


# --- transplants --------------------------------------------------------------------------------

Organ = Literal[
    "kidney",
    "liver",
    "heart",
    "lung",
    "pancreas",
    "kidney_pancreas",
    "intestine",
    "cornea",
    "hsct",
    "other",
]
DonorType = Literal["living_related", "living_unrelated", "deceased_dbd", "deceased_dcd", "unknown"]
GraftStatus = Literal["functioning", "failed", "removed", "unknown"]
Precision = Literal["day", "month", "year"]


class TransplantIn(_Strict):
    organ: Organ
    organ_detail: Short | None = None
    transplant_date: PastDate
    date_precision: Precision = "day"
    country: Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")]
    city: Short | None = None
    hospital: Short
    surgeon: Short | None = None
    transplant_number: Annotated[int, Field(ge=1, le=20)] = 1
    donor_type: DonorType = "unknown"
    donor_relation: Short | None = None
    recipient_blood_type: BloodType | None = None
    donor_blood_type: BloodType | None = None
    abo_incompatible: bool | None = None
    cmv_donor: Serostatus | None = None
    cmv_recipient: Serostatus | None = None
    ebv_donor: Serostatus | None = None
    ebv_recipient: Serostatus | None = None
    hla_mismatch: Short | None = None
    primary_disease: Short | None = None
    pre_transplant_dialysis: Short | None = None
    induction_therapy: Short | None = None
    graft_status: GraftStatus = "functioning"
    graft_status_date: OptionalPastDate = None
    graft_failure_reason: Short | None = None
    follow_up_center: Short | None = None
    follow_up_doctor: Short | None = None
    notes: Long | None = None

    @model_validator(mode="after")
    def _partial_date(self) -> "TransplantIn":
        # "only the month/year" is stored as its first day (docs/03; date_precision)
        if self.date_precision == "month":
            self.transplant_date = self.transplant_date.replace(day=1)
        elif self.date_precision == "year":
            self.transplant_date = self.transplant_date.replace(month=1, day=1)
        if self.graft_status_date is not None and self.graft_status_date < self.transplant_date:
            raise ValueError("graft_status_date")
        return self


class TransplantCreate(TransplantIn):
    client_id: UUID


class Elapsed(BaseModel):
    """Time since the transplant, never more than can be true (counted from the last possible
    day of a month/year-only date); `approximate`: show "≈" or the year, not a day count."""

    days: int
    months: int
    years: int
    approximate: bool


class TransplantOut(BaseModel):
    id: UUID
    organ: str
    organ_detail: str | None
    transplant_date: date
    date_precision: str
    country: str
    city: str | None
    hospital: str
    surgeon: str | None
    transplant_number: int
    donor_type: str
    donor_relation: str | None
    recipient_blood_type: str | None
    donor_blood_type: str | None
    abo_incompatible: bool | None
    cmv_donor: str | None
    cmv_recipient: str | None
    ebv_donor: str | None
    ebv_recipient: str | None
    hla_mismatch: str | None
    primary_disease: str | None
    pre_transplant_dialysis: str | None
    induction_therapy: str | None
    graft_status: str
    graft_status_date: date | None
    graft_failure_reason: str | None
    follow_up_center: str | None
    follow_up_doctor: str | None
    notes: str | None
    elapsed: Elapsed | None
    created_at: datetime
    updated_at: datetime | None


def _transplant_out(row: Any) -> TransplantOut:
    data = dict(row._mapping)
    e = elapsed_since(data["transplant_date"], data["date_precision"], _today())
    return TransplantOut(**data, elapsed=Elapsed(**e.__dict__) if e is not None else None)


async def _transplant(db: PhiDb, patient_id: UUID, transplant_id: UUID) -> TransplantOut:
    rows = await repo.transplants(db, patient_id, transplant_id)
    if not rows:
        raise AppError(404, "transplant.not_found")
    return _transplant_out(rows[0])


@router.get("/transplants", response_model=list[TransplantOut], responses=_ERRORS)
async def list_transplants(patient_id: UUID, db: PatientReadDb) -> list[TransplantOut]:
    return [_transplant_out(r) for r in await repo.transplants(db, patient_id)]


@router.post(
    "/transplants",
    response_model=TransplantOut,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"model": TransplantOut}, **_ERRORS},
)
async def create_transplant(
    patient_id: UUID, body: TransplantCreate, db: PatientWriteDb, response: Response
) -> TransplantOut:
    saved = await service.create_transplant(
        db, patient_id, body.client_id, _fields(body, repo.TRANSPLANT_FIELDS)
    )
    if not saved.created:
        response.status_code = status.HTTP_200_OK  # a retry: the stored record
    return await _transplant(db, patient_id, saved.id)


@router.get("/transplants/{transplant_id}", response_model=TransplantOut, responses=_ERRORS)
async def get_transplant(patient_id: UUID, transplant_id: UUID, db: PatientReadDb) -> TransplantOut:
    return await _transplant(db, patient_id, transplant_id)


@router.put("/transplants/{transplant_id}", response_model=TransplantOut, responses=_ERRORS)
async def replace_transplant(
    patient_id: UUID, transplant_id: UUID, body: TransplantIn, db: PatientWriteDb
) -> TransplantOut:
    """The whole record as edited (fields left out are cleared)."""
    await service.update_transplant(
        db, patient_id, transplant_id, _fields(body, repo.TRANSPLANT_FIELDS)
    )
    return await _transplant(db, patient_id, transplant_id)


@router.delete(
    "/transplants/{transplant_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS
)
async def delete_transplant(patient_id: UUID, transplant_id: UUID, db: PatientWriteDb) -> Response:
    """The profile's owner only (it is part of the record's history)."""
    await service.delete(
        db,
        "transplants",
        patient_id,
        transplant_id,
        missing=AppError(404, "transplant.not_found"),
        refused=AppError(403, "record.delete_not_allowed"),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- medications ----------------------------------------------------------------------------------


class RegimenIn(_Strict):
    """A dose and schedule from `effective_from` on, as the doctor instructed.

    daily/weekly: amounts per time (`schedule.times[].amount`, e.g. 2 mg at 08:00 and 1.5 mg
    at 20:00) with one `dose_unit`, or no amounts at all. prn: `dose_amount` + `dose_unit`
    (or neither). `dose_unit` "other" needs `dose_unit_text`.
    """

    client_id: UUID
    # a doctor may set the change from a coming day; never more than a year ahead
    effective_from: date
    dose_amount: DoseAmount | None = None
    dose_unit: DoseUnit | None = None
    dose_unit_text: Short | None = None
    schedule: dict[str, object]
    instructions: Long | None = None
    changed_by_note: Long | None = None

    @model_validator(mode="after")
    def _shape(self) -> "RegimenIn":
        if not date(1950, 1, 1) <= self.effective_from <= _today() + _YEAR_AHEAD:
            raise ValueError("effective_from")
        try:
            self.schedule = normalize_schedule(self.schedule)
        except ScheduleError as exc:
            raise ValueError("schedule") from exc
        prn = self.schedule["type"] == "prn"
        if self.dose_amount is not None and not prn:
            raise ValueError("dose_amount")  # amounts go on the times
        amounts = has_amounts(self.schedule) or self.dose_amount is not None
        if amounts != (self.dose_unit is not None):
            raise ValueError("dose_unit")
        if (self.dose_unit == "other") != (self.dose_unit_text is not None):
            raise ValueError("dose_unit_text")
        return self


class RegimenOut(BaseModel):
    id: UUID
    effective_from: date
    dose_amount: DoseOut | None
    dose_unit: str | None
    dose_unit_text: str | None
    schedule: dict[str, object]
    instructions: str | None
    changed_by_note: str | None
    voided_at: datetime | None  # entered by mistake: kept in the history, never in force
    void_reason: str | None
    created_at: datetime


class MedicationIn(_Strict):
    catalog_code: Annotated[str, StringConstraints(pattern=r"^[A-Z0-9_]{1,40}$")] | None = None
    name: Short
    brand: Short | None = None
    form: Short | None = None
    strength: Short | None = None
    route: Short = "oral"
    purpose: Short | None = None
    prescribed_by: Short | None = None
    transplant_id: UUID | None = None
    started_on: OptionalPastDate = None
    stopped_on: OptionalPastDate = None
    stop_reason: Short | None = None
    # a course's planned last day (valganciclovir, co-trimoxazole, a taper): reminders stop after
    planned_end_on: OptionalPlanDate = None
    is_long_term: bool = True
    reminders_enabled: bool = False
    reminder_timezone_mode: Literal["home", "local"] = "home"
    notes: Long | None = None

    @model_validator(mode="after")
    def _dates(self) -> "MedicationIn":
        start = self.started_on
        if start and self.stopped_on and self.stopped_on < start:
            raise ValueError("stopped_on")
        if start and self.planned_end_on and self.planned_end_on < start:
            raise ValueError("planned_end_on")
        if self.stop_reason is not None and self.stopped_on is None:
            raise ValueError("stop_reason")
        return self


class MedicationCreate(MedicationIn):
    client_id: UUID
    regimen: RegimenIn | None = None


class MedicationOut(BaseModel):
    id: UUID
    catalog_code: str | None
    category: str | None
    name: str
    brand: str | None
    form: str | None
    strength: str | None
    route: str
    purpose: str | None
    prescribed_by: str | None
    transplant_id: UUID | None
    started_on: date | None
    stopped_on: date | None
    stop_reason: str | None
    planned_end_on: date | None
    is_long_term: bool
    reminders_enabled: bool
    reminder_timezone_mode: str
    notes: str | None
    # taken today (not stopped, course not over) - Ulaanbaatar date
    is_current: bool
    # in force today; None when the medication is not current
    current_regimen: RegimenOut | None
    # the next scheduled change, so reminders planned days ahead switch on its first day
    next_regimen: RegimenOut | None
    created_at: datetime
    updated_at: datetime | None


class MedicationDetail(MedicationOut):
    regimens: list[RegimenOut]  # the dose history, newest first - never edited (H8)


def _regimen_out(row: Any) -> RegimenOut:
    return RegimenOut.model_validate(row._mapping)


async def _medications(
    db: PhiDb, patient_id: UUID, medication_id: UUID | None = None
) -> list[MedicationDetail]:
    rows = await repo.medications(db, patient_id, medication_id)
    history = await repo.regimens(db, patient_id, [r.id for r in rows])
    today = _today()
    out = []
    by_medication: dict[UUID, list[Any]] = {}
    for r in history:
        by_medication.setdefault(r.medication_id, []).append(r)
    for row in rows:
        own = by_medication.get(row.id, [])
        current = is_current(row.stopped_on, row.planned_end_on, today)
        in_force = regimen_on(own, today) if current else None
        upcoming = next_regimen(own, today) if current else None
        if (
            upcoming is not None
            and row.planned_end_on
            and upcoming.effective_from > row.planned_end_on
        ):
            upcoming = None  # starts after the course ends: never in force
        out.append(
            MedicationDetail(
                **row._mapping,
                is_current=current,
                current_regimen=_regimen_out(in_force) if in_force is not None else None,
                next_regimen=_regimen_out(upcoming) if upcoming is not None else None,
                regimens=[_regimen_out(r) for r in own],
            )
        )
    return out


async def _medication(db: PhiDb, patient_id: UUID, medication_id: UUID) -> MedicationDetail:
    found = await _medications(db, patient_id, medication_id)
    if not found:
        raise AppError(404, "medication.not_found")
    return found[0]


def _regimen_values(body: RegimenIn) -> dict[str, object]:
    return body.model_dump(exclude={"client_id"})


@router.get("/medications", response_model=list[MedicationDetail], responses=_ERRORS)
async def list_medications(patient_id: UUID, db: PatientReadDb) -> list[MedicationDetail]:
    """Current first (immunosuppressants first among them), then those stopped - each with
    its dose history: the phone plans reminders and today's doses from it offline (every
    scheduled change, not only the next)."""
    return await _medications(db, patient_id)


@router.post(
    "/medications",
    response_model=MedicationDetail,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"model": MedicationDetail}, **_ERRORS},
)
async def create_medication(
    patient_id: UUID, body: MedicationCreate, db: PatientWriteDb, response: Response
) -> MedicationDetail:
    regimen = (
        (body.regimen.client_id, _regimen_values(body.regimen))
        if body.regimen is not None
        else None
    )
    saved = await service.create_medication(
        db, patient_id, body.client_id, _fields(body, repo.MEDICATION_FIELDS), regimen
    )
    if not saved.created:
        response.status_code = status.HTTP_200_OK
    return await _medication(db, patient_id, saved.id)


@router.get("/medications/{medication_id}", response_model=MedicationDetail, responses=_ERRORS)
async def get_medication(
    patient_id: UUID, medication_id: UUID, db: PatientReadDb
) -> MedicationDetail:
    return await _medication(db, patient_id, medication_id)


@router.put("/medications/{medication_id}", response_model=MedicationDetail, responses=_ERRORS)
async def replace_medication(
    patient_id: UUID, medication_id: UUID, body: MedicationIn, db: PatientWriteDb
) -> MedicationDetail:
    """Name, strength, dates ... - not the dose: a dose change is POST .../regimens."""
    await service.update_medication(
        db, patient_id, medication_id, _fields(body, repo.MEDICATION_FIELDS)
    )
    return await _medication(db, patient_id, medication_id)


@router.post(
    "/medications/{medication_id}/regimens",
    response_model=MedicationDetail,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"model": MedicationDetail}, **_ERRORS},
)
async def change_dose(
    patient_id: UUID,
    medication_id: UUID,
    body: RegimenIn,
    db: PatientWriteDb,
    response: Response,
) -> MedicationDetail:
    """A new dose or schedule from `effective_from` on; the previous one stays in the history
    (H8). The values are the doctor's instruction as the user enters it."""
    saved = await service.add_regimen(
        db, patient_id, medication_id, body.client_id, _regimen_values(body)
    )
    if not saved.created:
        response.status_code = status.HTTP_200_OK
    return await _medication(db, patient_id, medication_id)


class VoidIn(_Strict):
    reason: Short


@router.post(
    "/medications/{medication_id}/regimens/{regimen_id}/void",
    response_model=MedicationDetail,
    responses=_ERRORS,
)
async def void_dose_change(
    patient_id: UUID, medication_id: UUID, regimen_id: UUID, body: VoidIn, db: PatientWriteDb
) -> MedicationDetail:
    """Mark a scheduled change that has not started as entered by mistake. It stays in the
    history, marked, and never comes into force. A started dose cannot be voided (409): enter
    the correct one as a new change instead."""
    await service.void_regimen(db, patient_id, medication_id, regimen_id, body.reason)
    return await _medication(db, patient_id, medication_id)


@router.delete(
    "/medications/{medication_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS
)
async def delete_medication(patient_id: UUID, medication_id: UUID, db: PatientWriteDb) -> Response:
    """Erases the medication with its dose history and intakes - the owner only."""
    await service.delete(
        db,
        "medications",
        patient_id,
        medication_id,
        missing=AppError(404, "medication.not_found"),
        refused=AppError(403, "record.delete_not_allowed"),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- intakes --------------------------------------------------------------------------------------

# A taken dose is recorded near its slot: at most 3 hours early (a dose taken before its
# reminder), within a day after. Tomorrow's dose cannot be marked taken tonight by a slip -
# "taken" always wins (H20), so such a slip would silence that dose's reminder.
_EARLY = timedelta(hours=3)
_LATE = RECORDING_WINDOW  # the summary's "open" uses the same window


class IntakeIn(_Strict):
    client_id: UUID
    medication_id: UUID
    scheduled_at: datetime | None = None  # none = an as-needed (prn) dose
    taken_at: datetime | None = None
    status: Literal["taken", "late", "skipped"]
    note: Long | None = None

    @model_validator(mode="after")
    def _consistent(self) -> "IntakeIn":
        for moment in (self.scheduled_at, self.taken_at):
            if moment is not None and moment.tzinfo is None:
                raise ValueError("timezone")
        if self.scheduled_at is not None:
            # slots are HH:MM: two devices' records of one dose meet on the same minute (H20)
            self.scheduled_at = self.scheduled_at.replace(second=0, microsecond=0)
        if (self.status == "skipped") != (self.taken_at is None):
            raise ValueError("taken_at")
        if self.scheduled_at is None and self.status != "taken":
            raise ValueError("status")
        now = datetime.now(UTC)
        floor = datetime(2000, 1, 1, tzinfo=UTC)
        if self.taken_at is not None and not floor <= self.taken_at <= now + timedelta(minutes=5):
            raise ValueError("taken_at")
        if self.scheduled_at is not None:
            # skipped up to 2 days ahead (a planned skip); taken at most 3 hours ahead
            ahead = timedelta(days=2) if self.status == "skipped" else _EARLY
            if not floor <= self.scheduled_at <= now + ahead:
                raise ValueError("scheduled_at")
            if self.taken_at is not None and not (
                self.scheduled_at - _EARLY <= self.taken_at <= self.scheduled_at + _LATE
            ):
                raise ValueError("taken_at")
        return self


class IntakeExtraOut(BaseModel):
    status: str
    taken_at: datetime
    by: Literal["you", "owner", "caregiver"] | None


class IntakeOut(BaseModel):
    id: UUID
    medication_id: UUID
    scheduled_at: datetime | None
    taken_at: datetime | None
    status: str
    note: str | None
    created_at: datetime
    updated_at: datetime | None
    # Q24: who recorded the dose as taken (relative to the caller, never a name) and any
    # other "taken" record of the same dose - facts only
    recorded_by: Literal["you", "owner", "caregiver"] | None = None
    also_recorded: list[IntakeExtraOut] = []


def _intake_out(row: Any, extras: dict[UUID, list[Any]]) -> IntakeOut:
    return IntakeOut(
        **{k: v for k, v in row._mapping.items() if k not in {"taken_by", "recorded_by_role"}},
        recorded_by=row.recorded_by_role,
        also_recorded=[
            IntakeExtraOut(status=x.status, taken_at=x.taken_at, by=x.by_role)
            for x in extras.get(row.id, [])
        ],
    )


@router.get("/intakes", response_model=list[IntakeOut], responses=_ERRORS)
async def list_intakes(
    patient_id: UUID,
    db: PatientReadDb,
    since: Annotated[datetime, Query(alias="from")],
    until: Annotated[datetime, Query(alias="to")],
    medication_id: UUID | None = None,
) -> list[IntakeOut]:
    """Recorded doses in [from, to): at most 93 days and 2000 records per request (never cut
    short silently: more is 422 `intake.too_many`, ask for a shorter range)."""
    if since.tzinfo is None or until.tzinfo is None or not service.window_ok(since, until):
        raise AppError(422, "validation")
    rows = await repo.intakes(db, patient_id, since, until, medication_id)
    if len(rows) > repo.INTAKE_PAGE:
        raise AppError(422, "intake.too_many")
    extras = await repo.intake_extras(db, patient_id, [r.id for r in rows])
    return [_intake_out(r, extras) for r in rows]


@router.post(
    "/intakes",
    response_model=IntakeOut,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"model": IntakeOut}, **_ERRORS},
)
async def record_intake(
    patient_id: UUID, body: IntakeIn, db: PatientWriteDb, response: Response
) -> IntakeOut:
    """Record a dose as taken, late or skipped. Idempotent by client_id; a second record of
    the same scheduled dose merges - "taken" always wins (H20) - and answers with the stored
    result (200)."""
    saved = await service.record_intake(
        db, patient_id, body.client_id, body.model_dump(exclude={"client_id"})
    )
    if not saved.created:
        response.status_code = status.HTTP_200_OK
    row = await repo.intake(db, patient_id, saved.id)
    if row is None:
        raise AppError(404, "intake.not_found")
    return _intake_out(row, await repo.intake_extras(db, patient_id, [row.id]))


@router.delete(
    "/intakes/{intake_id}/mine", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS
)
async def delete_my_extra_intake(patient_id: UUID, intake_id: UUID, db: PatientWriteDb) -> Response:
    """Undo one's own extra "taken" record of a dose someone else logged first (Q24)."""
    if not await repo.delete_my_extras(db, patient_id, intake_id):
        raise AppError(404, "intake.not_found")
    await repo.audit(db, "intake.extra_delete", "medication_intake", intake_id, patient_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/intakes/{intake_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS)
async def delete_intake(patient_id: UUID, intake_id: UUID, db: PatientWriteDb) -> Response:
    """Undo a record ("Буцаах"). A taken dose only by whoever recorded it, or the owner."""
    await service.delete(
        db,
        "medication_intakes",
        patient_id,
        intake_id,
        missing=AppError(404, "intake.not_found"),
        refused=AppError(403, "intake.delete_not_allowed"),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- reminder time zone (Q22) ------------------------------------------------------------------

# A switch accepted on a phone offline arrives later: at most a week late, never ahead
_SWITCH_LATE = timedelta(days=7)
_ZONE_SHAPE = re.compile(r"^[A-Za-z][A-Za-z0-9_+-]*(/[A-Za-z0-9_+-]+){0,2}$")


@cache
def _zone_names() -> frozenset[str]:
    return frozenset(available_timezones())


def _zone(value: str) -> str:
    if len(value) > 64 or not _ZONE_SHAPE.match(value) or value not in _zone_names():  # noqa: PLR2004
        raise ValueError("timezone")
    return value


ZoneName = Annotated[str, AfterValidator(_zone)]


class ZoneSwitchIn(_Strict):
    client_id: UUID
    timezone: ZoneName
    effective_at: datetime

    @model_validator(mode="after")
    def _aware(self) -> "ZoneSwitchIn":
        if self.effective_at.tzinfo is None:
            raise ValueError("timezone")
        self.effective_at = self.effective_at.astimezone(UTC).replace(microsecond=0)
        return self


class ZoneSwitchOut(BaseModel):
    id: UUID
    timezone: str
    effective_at: datetime
    seq: int
    created_at: datetime


class ZonesOut(BaseModel):
    home: str  # "home" mode medications: always this zone
    current: str  # "local" mode medications: this zone now (home until the first switch)
    # newest first: only the switches that can still place a planned dose (the one in force
    # two days ago and any since) - not a travel history
    switches: list[ZoneSwitchOut]


@router.get("/timezone", response_model=ZonesOut, responses=_ERRORS)
async def get_timezone(patient_id: UUID, db: PatientReadDb) -> ZonesOut:
    """The profile's reminder time zone, and the switches a phone needs to plan reminders."""
    now = datetime.now(UTC)
    rows = await repo.zones(db, patient_id, now, now + timedelta(days=1))
    switches = [ZoneSwitchOut.model_validate(r._mapping) for r in rows[: repo.ZONE_WINDOW_MAX]]
    current = next((z.timezone for z in switches if z.effective_at <= now), HOME_TIMEZONE)
    return ZonesOut(home=HOME_TIMEZONE, current=current, switches=switches)


@router.post(
    "/timezone",
    response_model=ZoneSwitchOut,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"model": ZoneSwitchOut}, 429: {"model": ErrorBody}, **_ERRORS},
)
async def switch_timezone(
    patient_id: UUID, body: ZoneSwitchIn, db: PatientWriteDb, response: Response
) -> ZoneSwitchOut:
    """Switch the zone of "local" medications (the user said yes on the phone). Idempotent by
    client_id; a past switch is never edited - a new one replaces it from its time on.
    `effective_at`: at most a week ago (a switch accepted offline), never ahead."""
    now = datetime.now(UTC)
    if not now - _SWITCH_LATE <= body.effective_at <= now + timedelta(minutes=5):
        # a queued retry of a switch already stored is still that switch, however late
        stored = await service.stored_switch(
            db, patient_id, body.client_id, body.timezone, body.effective_at
        )
        if stored is None:
            raise AppError(422, "validation")
        response.status_code = status.HTTP_200_OK
        return ZoneSwitchOut.model_validate(stored._mapping)
    row, created = await service.switch_zone(
        db, patient_id, body.client_id, body.timezone, body.effective_at
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return ZoneSwitchOut.model_validate(row._mapping)


# --- monthly summary (Q23) ---------------------------------------------------------------------


# a whole percent as a string ("96"), like every number in the API (CLAUDE.md rule 7)
Percent = Annotated[
    Decimal, PlainSerializer(lambda d: format(d, "f"), return_type=str, when_used="json")
]


class SummaryOut(BaseModel):
    """Counts only: no "on time" threshold, no colour, no judgement (Q23, rule 10)."""

    planned: int  # planned doses up to now (from when the medication was entered)
    taken: int  # recorded taken, including the user's own "late"
    skipped: int
    unrecorded: int  # not recorded, past the 24-hour recording window
    open: int  # not recorded yet, still within the recording window
    # of the closed doses (planned - open): whole percent rounded down; none when none closed
    percent_taken: Percent | None


class MedicationSummaryOut(SummaryOut):
    medication_id: UUID


class AdherenceOut(BaseModel):
    month: str
    total: SummaryOut
    medications: list[MedicationSummaryOut]  # only medications with planned doses


def _summary(s: Summary) -> dict[str, object]:
    return {
        "planned": s.planned,
        "taken": s.taken,
        "skipped": s.skipped,
        "unrecorded": s.unrecorded,
        "open": s.open,
        "percent_taken": s.percent_taken,
    }


@router.get("/adherence", response_model=AdherenceOut, responses=_ERRORS)
async def get_adherence(
    patient_id: UUID,
    db: PatientReadDb,
    month: Annotated[str, Query(pattern=r"^20[0-9]{2}-(0[1-9]|1[0-2])$")],
) -> AdherenceOut:
    """Planned doses of a calendar month (Ulaanbaatar) up to now, and how many were recorded
    taken or skipped. As-needed medications plan no doses and are not counted."""
    year, mon = (int(p) for p in month.split("-"))
    if (year, mon) > (_today().year, _today().month):
        raise AppError(422, "validation")
    total, per = await service.month_summary(db, patient_id, year, mon, datetime.now(UTC))
    return AdherenceOut(
        month=month,
        total=SummaryOut.model_validate(_summary(total)),
        medications=[
            MedicationSummaryOut(medication_id=p.medication_id, **_summary(p.summary)) for p in per
        ],
    )


# --- catalog --------------------------------------------------------------------------------------


class CatalogItem(BaseModel):
    code: str
    generic_mn: str
    generic_en: str
    brands: list[str]
    category: str
    forms: list[str]


@catalog_router.get("", response_model=list[CatalogItem], responses=_ERRORS)
async def search_catalog(
    db: PhiDb, q: Annotated[str, Query(max_length=60)] = ""
) -> list[CatalogItem]:
    """Medication names (Mongolian, English, brands) for the "add a medication" search."""
    rows = await repo.search_catalog(db, q.strip())
    return [CatalogItem.model_validate(r._mapping) for r in rows]
