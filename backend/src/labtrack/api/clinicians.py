"""A doctor's targets and notes, and drug level statistics (Phase 7.4; docs/06 §8a; H15;
migration 0043; core/level_stats.py).

- everyone who reads a profile sees its doctors' targets (shown as the doctor's, apart from the
  lab's range) and notes, and the level statistics - numbers only, no threshold, no judgement;
- only a registered doctor with live doctor access writes them. Those routes live under /me
  (the profile's write gate is for owners and caregivers); the database checks the doctor.
"""

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from labtrack.api.caregivers import _pg
from labtrack.api.deps import PatientReadDb, PatientWriteDb, PhiDb
from labtrack.api.errors import AppError, ErrorBody
from labtrack.api.numbers import num
from labtrack.api.ratelimit import per_user
from labtrack.config import get_settings
from labtrack.core.level_stats import (
    LEVEL_STATS_TESTS,
    SETTLE_MONTHS,
    LevelPoint,
    collected_day,
    level_stats,
)
from labtrack.db.sql import bound_text
from labtrack.health import repository as health_repo

_UB = ZoneInfo("Asia/Ulaanbaatar")

router = APIRouter(prefix="/patients/{patient_id}", tags=["clinicians"])
me_router = APIRouter(prefix="/me/doctor", tags=["clinicians"])

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorBody},
    403: {"model": ErrorBody},
    404: {"model": ErrorBody},
    409: {"model": ErrorBody},
    422: {"model": ErrorBody},
}

TestCode = Annotated[str, StringConstraints(pattern=r"^[A-Z0-9_]{1,20}$")]
Number = Annotated[str, StringConstraints(pattern=r"^[0-9]{1,6}([.,][0-9]{1,4})?$")]
# text a person types: no NUL or control characters (line breaks and tabs are fine)
_PLAIN = r"^[^\x00-\x08\x0B\x0C\x0E-\x1F\x7F]*$"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TargetOut(BaseModel):
    id: UUID
    test_code: str
    low: str | None
    high: str | None
    unit: str
    valid_from: date
    valid_to: date | None
    note: str | None
    set_by_name: str | None


class NoteOut(BaseModel):
    id: UUID
    body: str
    created_at: datetime
    author_name: str | None
    mine: bool


class LevelValueOut(BaseModel):
    collected_on: date
    value: str
    target_low: str | None
    target_high: str | None
    lab: str | None  # the lab that printed it (Q63-6)


class LevelStatsOut(BaseModel):
    """Numbers only (H15): no threshold, colour or judgement - the app adds the reviewed text.
    The mean, SD and the values themselves go to a doctor only; everyone else gets CV% (Q63-7,
    physician 2026-11-18)."""

    test_code: str
    unit: str | None
    since: date
    n: int
    mean: str | None  # a doctor only
    sd: str | None  # a doctor only
    cv_percent: str | None
    with_target: int  # a doctor only (0 for anyone else)
    in_target: int  # a doctor only
    in_target_percent: str | None  # a doctor only
    counted_from: date | None  # the first countable day (6 months after the transplant)
    settle_months: int  # how long after the transplant counting starts (Q63-3)
    bounds_left_out: int
    not_numeric_left_out: int
    other_unit_left_out: int
    no_date_left_out: int
    early_left_out: int
    duplicates_left_out: int
    same_day_left_out: int
    reason: str | None  # no_transplant | too_few | zero_mean | no_unit: why no number
    labs: list[str]  # a doctor only: the labs of the counted values (methods may differ)
    lab_unknown: int  # a doctor only: counted values whose lab is not named
    values: list[LevelValueOut]  # a doctor only


class TargetIn(_Strict):
    patient_id: UUID
    test_code: TestCode
    low: Number | None = None
    high: Number | None = None
    valid_from: date
    note: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=500, pattern=_PLAIN)]
        | None
    ) = None

    @field_validator("low", "high")
    @classmethod
    def _comma(cls, v: str | None) -> str | None:
        return v.replace(",", ".") if v else v


class TargetEndIn(_Strict):
    target_id: UUID
    on: date


class NoteIn(_Strict):
    patient_id: UUID
    body: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=2000, pattern=_PLAIN),
    ]


class NoteRemoveIn(_Strict):
    note_id: UUID


def _dec(v: str | None) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(v)
    except InvalidOperation:
        raise AppError(422, "clinician.invalid_number") from None


# --- everyone who reads the profile ------------------------------------------------------


@router.get("/targets", response_model=list[TargetOut], responses=_ERRORS)
async def targets(patient_id: UUID, db: PatientReadDb) -> list[TargetOut]:
    rows = (
        await db.execute(bound_text("select * from profile_targets(:p)"), {"p": patient_id})
    ).all()
    return [TargetOut(**{**r._mapping, "low": num(r.low), "high": num(r.high)}) for r in rows]


@router.get("/doctor-notes", response_model=list[NoteOut], responses=_ERRORS)
async def notes(patient_id: UUID, db: PatientReadDb) -> list[NoteOut]:
    rows = (
        await db.execute(bound_text("select * from profile_doctor_notes(:p)"), {"p": patient_id})
    ).all()
    return [NoteOut(**r._mapping) for r in rows]


class SteroidCardOut(BaseModel):
    """The steroid emergency card mark (Q36): when, and whether a treating doctor or the owner
    (as their doctor told them) marked it. Never inferred from the medicines (rule 10)."""

    marked_on: date
    by_doctor: bool
    doctor_name: str | None


class SteroidCardIn(_Strict):
    on: bool


class DoctorSteroidCardIn(SteroidCardIn):
    patient_id: UUID


@router.get("/steroid-card", response_model=SteroidCardOut | None, responses=_ERRORS)
async def steroid_card(patient_id: UUID, db: PatientReadDb) -> SteroidCardOut | None:
    row = (await db.execute(health_repo.STEROID_CARD, {"p": patient_id})).first()
    return SteroidCardOut(**row._mapping) if row else None


async def _mark_steroid_card(db: AsyncSession, patient_id: UUID, on: bool) -> Response:
    try:
        await db.execute(health_repo.STEROID_CARD_SET, {"p": patient_id, "on": on})
    except DBAPIError as exc:
        if _pg(exc)[0] == "42501":
            raise AppError(403, "clinician.steroid_card_forbidden") from None
        raise
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/steroid-card", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS)
async def owner_steroid_card(patient_id: UUID, body: SteroidCardIn, db: PatientWriteDb) -> Response:
    """The owner marks it as their doctor told them, or clears it (a caregiver cannot - the
    database decides; audited)."""
    return await _mark_steroid_card(db, patient_id, body.on)


_LEVEL_ROWS = bound_text(
    "select lr.collected_at, lr.value_canonical, lr.comparator, lr.unit_canonical, r.lab_name"
    " from lab_results lr"
    " join lab_reports r on r.id = lr.report_id and r.patient_id = lr.patient_id"
    " where lr.patient_id = :p and lr.test_code = :t and r.status = 'confirmed'"
    " and lr.collected_at is not null and lr.collected_at >= :since"
)
_TRANSPLANTS = bound_text(
    "select transplant_date, date_precision from transplants where patient_id = :p"
    " and transplant_date is not null"
)
_NO_DATE = bound_text(
    "select count(*) from lab_results lr"
    " join lab_reports r on r.id = lr.report_id and r.patient_id = lr.patient_id"
    " where lr.patient_id = :p and lr.test_code = :t and r.status = 'confirmed'"
    " and lr.collected_at is null and r.created_at >= :since"  # entered within the window
)
_UNIT = bound_text("select canonical_unit from test_catalog where code = :t")
_IS_DOCTOR = bound_text(
    "select exists (select 1 from patient_access a join users u on u.id = a.user_id"
    " where a.patient_id = :p and a.user_id = app_user_id() and a.level = 'doctor'"
    " and u.role = 'doctor' and a.revoked_at is null"
    " and (a.expires_at is null or a.expires_at > now()))"
)
_TARGETS = bound_text(
    "select low, high, valid_from, valid_to from patient_targets"
    " where patient_id = :p and test_code = :t order by valid_from desc"
)


@router.get("/level-stats/{test_code}", response_model=LevelStatsOut, responses=_ERRORS)
async def stats(
    patient_id: UUID,
    test_code: TestCode,
    db: PatientReadDb,
    months: Annotated[int, Query(ge=3, le=24)] = 12,
) -> LevelStatsOut:
    """Mean, CV% and time in the doctor's target over the last `months` (6 §8a, H15).
    Tacrolimus only for now (Q63): another test answers 422, never a number."""
    if test_code not in LEVEL_STATS_TESTS:
        raise AppError(422, "clinician.not_a_level_test")
    unit = (await db.execute(_UNIT, {"t": test_code})).scalar_one_or_none()
    since = collected_day(datetime.now(UTC)) - timedelta(days=round(months * 30.44))
    txs = [
        (r.transplant_date, r.date_precision)
        for r in await db.execute(_TRANSPLANTS, {"p": patient_id})
    ]
    no_date = int(
        (
            await db.execute(
                _NO_DATE,
                {"p": patient_id, "t": test_code, "since": datetime.combine(since, time(), _UB)},
            )
        ).scalar_one()
    )
    tgts = (await db.execute(_TARGETS, {"p": patient_id, "t": test_code})).all()

    def target_on(day: date) -> tuple[Decimal | None, Decimal | None]:
        for t in tgts:
            if t.valid_from <= day and (t.valid_to is None or day <= t.valid_to):
                return t.low, t.high
        return None, None

    points = []
    for r in await db.execute(
        _LEVEL_ROWS,
        {"p": patient_id, "t": test_code, "since": datetime.combine(since, time(), _UB)},
    ):
        low, high = target_on(collected_day(r.collected_at))
        points.append(
            LevelPoint(
                r.collected_at, r.value_canonical, r.comparator, r.unit_canonical, low, high,
                r.lab_name,
            )
        )  # fmt: skip
    doctor = bool((await db.execute(_IS_DOCTOR, {"p": patient_id})).scalar_one())
    if unit is None:
        return LevelStatsOut(
            test_code=test_code, unit=None, since=since, n=0, mean=None, sd=None,
            cv_percent=None, with_target=0, in_target=0, in_target_percent=None,
            counted_from=None, settle_months=SETTLE_MONTHS, bounds_left_out=0,
            not_numeric_left_out=0, other_unit_left_out=0, no_date_left_out=no_date,
            early_left_out=0, duplicates_left_out=0, same_day_left_out=0, reason="no_unit",
            labs=[], lab_unknown=0, values=[],
        )  # fmt: skip
    s = level_stats(points, unit=unit, transplants=txs)
    return LevelStatsOut(
        test_code=test_code,
        unit=unit,
        since=since,
        n=s.n,
        mean=num(s.mean) if doctor else None,
        sd=num(s.sd) if doctor else None,
        cv_percent=num(s.cv_percent),
        with_target=s.with_target if doctor else 0,
        in_target=s.in_target if doctor else 0,
        in_target_percent=num(s.in_target_percent) if doctor else None,
        counted_from=s.counted_from,
        settle_months=SETTLE_MONTHS,
        bounds_left_out=s.bounds_left_out,
        not_numeric_left_out=s.not_numeric_left_out,
        other_unit_left_out=s.other_unit_left_out,
        no_date_left_out=no_date,
        early_left_out=s.early_left_out,
        duplicates_left_out=s.duplicates_left_out,
        same_day_left_out=s.same_day_left_out,
        reason=s.reason,
        labs=list(s.labs) if doctor else [],
        lab_unknown=s.lab_unknown if doctor else 0,
        values=[
            LevelValueOut(
                collected_on=p.collected_on,
                value=num(p.value) or "",
                target_low=num(p.target_low),
                target_high=num(p.target_high),
                lab=p.lab,
            )
            for p in (s.used if doctor else ())
        ],
    )


# --- a treating doctor -------------------------------------------------------------------


def _raise(exc: DBAPIError) -> None:
    state, _ = _pg(exc)
    if state == "42501":
        raise AppError(403, "clinician.not_treating") from None
    if state == "22023":
        raise AppError(422, "clinician.no_unit") from None
    if state == "22003":
        raise AppError(422, "clinician.target_implausible") from None
    if state == "22008":
        raise AppError(422, "clinician.target_day") from None
    if state in ("23505", "23514"):
        raise AppError(409, "clinician.target_conflict") from None
    raise exc


@me_router.post("/targets", status_code=status.HTTP_201_CREATED, responses=_ERRORS)
async def set_target(body: TargetIn, db: PhiDb) -> dict[str, UUID]:
    low, high = _dec(body.low), _dec(body.high)
    if low is None and high is None:
        raise AppError(422, "clinician.target_empty")
    if low is not None and high is not None and low > high:
        raise AppError(422, "clinician.target_order")
    try:
        tid = (
            await db.execute(
                bound_text("select set_patient_target(:p, :t, :l, :h, :f, :n)"),
                {"p": body.patient_id, "t": body.test_code, "l": low, "h": high,
                 "f": body.valid_from, "n": body.note},
            )
        ).scalar_one()  # fmt: skip
    except DBAPIError as exc:
        _raise(exc)
        raise
    return {"id": tid}


@me_router.post("/targets/end", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS)
async def end_target(body: TargetEndIn, db: PhiDb) -> Response:
    done = (
        await db.execute(
            bound_text("select end_patient_target(:t, :o)"), {"t": body.target_id, "o": body.on}
        )
    ).scalar_one()
    if not done:
        raise AppError(404, "clinician.target_not_found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@me_router.post(
    "/notes",
    status_code=status.HTTP_201_CREATED,
    responses=_ERRORS,
    dependencies=[
        Depends(per_user("doctor_note", lambda: get_settings().rate_caregiver_invite_per_minute))
    ],
)
async def add_note(body: NoteIn, db: PhiDb) -> dict[str, UUID]:
    try:
        nid = (
            await db.execute(
                bound_text("select add_doctor_note(:p, :b)"), {"p": body.patient_id, "b": body.body}
            )
        ).scalar_one()
    except DBAPIError as exc:
        _raise(exc)
        raise
    return {"id": nid}


@me_router.post("/notes/remove", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS)
async def remove_note(body: NoteRemoveIn, db: PhiDb) -> Response:
    done = (
        await db.execute(bound_text("select remove_doctor_note(:n)"), {"n": body.note_id})
    ).scalar_one()
    if not done:
        raise AppError(404, "clinician.note_not_found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@me_router.post("/steroid-card", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS)
async def doctor_steroid_card(body: DoctorSteroidCardIn, db: PhiDb) -> Response:
    """A treating doctor marks it (shown the NHS 2020 threshold in the app) or clears it."""
    return await _mark_steroid_card(db, body.patient_id, body.on)
