"""/patients: the health profiles a user can open - their own and their minor children's
(docs/04 §2, Q9; Phase 2.0). RLS decides what is visible (can_read_patient) and who edits
(owner); profiles are created only through create_patient(), which makes the caller the owner.

Health-data routes for a profile (transplants, medications, ...) hang under
/patients/{patient_id}/... and take PatientReadDb / PatientWriteDb (access, then a minor's
profile consents).
"""

import json
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, status
from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints, model_validator
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from labtrack.api.deps import PatientReadDb, PatientWriteDb, PhiDb
from labtrack.api.errors import AppError, ErrorBody
from labtrack.core.text import valid_display_name
from labtrack.db.sql import bound_text

router = APIRouter(prefix="/patients", tags=["patients"])

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorBody},
    403: {"model": ErrorBody},
    404: {"model": ErrorBody},
    409: {"model": ErrorBody},
    422: {"model": ErrorBody},
}

_LOCAL = ZoneInfo("Asia/Ulaanbaatar")
_ADULT_YEARS = 18


def _today() -> date:
    return datetime.now(_LOCAL).date()


def _name(value: str) -> str:
    if not valid_display_name(value):
        raise ValueError("full_name")
    return value


FullName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
    AfterValidator(_name),
]
Sex = Literal["male", "female", "unknown"]


def _years_before(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:  # 29 February
        return day.replace(year=day.year - years, day=28)


def _check_birth_date(value: date | None) -> date | None:
    if value is not None and not (date(1900, 1, 1) <= value <= _today()):
        raise ValueError("birth_date")
    return value


BirthDate = Annotated[date | None, AfterValidator(_check_birth_date)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PatientOut(BaseModel):
    id: UUID
    full_name: str
    relation: str | None
    birth_date: date | None
    sex: Sex
    access_level: Literal["owner", "caregiver", "doctor", "viewer"]
    is_minor: bool
    created_at: datetime


class PatientCreate(_Strict):
    full_name: FullName
    relation: Literal["self", "child"]
    birth_date: BirthDate = None
    sex: Sex = "unknown"

    @model_validator(mode="after")
    def _age_fits_relation(self) -> "PatientCreate":
        # A child's profile is a minor's (an adult keeps their own account and shares it);
        # one's own profile is an adult's (a minor's profile belongs to a parent).
        adult_from = _years_before(_today(), _ADULT_YEARS)
        born = self.birth_date
        if self.relation == "child" and (born is None or born <= adult_from):
            raise ValueError("birth_date")
        if self.relation == "self" and born is not None and born > adult_from:
            raise ValueError("birth_date")
        return self


class PatientUpdate(_Strict):
    full_name: FullName | None = None
    sex: Sex | None = None
    # Only an empty birth date can be filled, and only with an adult's (database trigger).
    birth_date: BirthDate = None


_SELECT = (
    "select p.id, p.full_name, p.relation, p.birth_date, p.sex::text as sex,"
    " a.level::text as access_level, is_minor_patient(p.id) as is_minor, p.created_at"
    " from patients p join patient_access a"
    " on a.patient_id = p.id and a.user_id = app_user_id()"
    " where can_read_patient(p.id)"
)


def _pg(exc: DBAPIError) -> object:
    return getattr(exc.orig, "__cause__", None) or exc.orig


def _sqlstate(exc: DBAPIError) -> str | None:
    return getattr(_pg(exc), "sqlstate", None)


def _second_self(exc: DBAPIError) -> bool:
    """create_patient's own check or the partial unique index behind it - no other 23505."""
    pg = _pg(exc)
    return _sqlstate(exc) == "23505" and (
        getattr(pg, "constraint_name", None) == "patients_one_self"
        or getattr(pg, "message", None) == "own profile exists"
    )


async def _one(db: AsyncSession, patient_id: UUID) -> PatientOut:
    row = (
        await db.execute(bound_text(_SELECT + " and p.id = :p"), {"p": patient_id})
    ).one_or_none()
    if row is None:
        # not there and not shared with the user look the same
        raise AppError(404, "patient.not_found")
    return PatientOut(**row._mapping)


@router.get("", response_model=list[PatientOut], responses=_ERRORS)
async def list_patients(db: PhiDb) -> list[PatientOut]:
    rows = await db.execute(
        bound_text(_SELECT + " order by (p.relation = 'self') desc, p.created_at")
    )
    return [PatientOut(**r._mapping) for r in rows]


@router.post("", response_model=PatientOut, status_code=status.HTTP_201_CREATED, responses=_ERRORS)
async def create_patient(body: PatientCreate, db: PhiDb) -> PatientOut:
    try:
        async with db.begin_nested():
            pid: UUID = (
                await db.execute(
                    bound_text("select create_patient(:n, :r, :b, cast(:s as sex))"),
                    {"n": body.full_name, "r": body.relation, "b": body.birth_date, "s": body.sex},
                )
            ).scalar_one()
    except DBAPIError as exc:
        state = _sqlstate(exc)
        if _second_self(exc):
            raise AppError(409, "patient.self_exists") from None
        if state == "54000":
            raise AppError(409, "patient.limit_reached") from None
        if state == "22023":
            raise AppError(422, "validation") from None
        raise
    await db.execute(
        bound_text("select audit_write('patient.create', 'patient', cast(:p as text), :pid, null)"),
        {"p": str(pid), "pid": pid},
    )
    return await _one(db, pid)


@router.get("/{patient_id}", response_model=PatientOut, responses=_ERRORS)
async def get_patient(patient_id: UUID, db: PatientReadDb) -> PatientOut:
    return await _one(db, patient_id)


@router.patch("/{patient_id}", response_model=PatientOut, responses=_ERRORS)
async def update_patient(patient_id: UUID, body: PatientUpdate, db: PatientWriteDb) -> PatientOut:
    current = await _one(db, patient_id)
    if current.access_level != "owner":
        raise AppError(403, "patient.not_owner")
    fields = sorted(body.model_dump(exclude_none=True))
    if not fields:
        return current
    try:
        async with db.begin_nested():
            await db.execute(
                bound_text(
                    "update patients set full_name = coalesce(:n, full_name),"
                    " sex = coalesce(cast(:s as sex), sex),"
                    " birth_date = coalesce(:b, birth_date) where id = :p"
                ),
                {"n": body.full_name, "s": body.sex, "b": body.birth_date, "p": patient_id},
            )
    except DBAPIError as exc:
        state = _sqlstate(exc)
        # patients_birth_date_once: a set birth date stays (a minor's cannot be aged); an empty
        # one is filled only with an adult's
        if state == "42501":
            raise AppError(409, "patient.birth_date_locked") from None
        if state == "22023":
            raise AppError(422, "validation") from None
        raise
    # which fields changed, never their values
    await db.execute(
        bound_text(
            "select audit_write('patient.update', 'patient', cast(:p as text), :pid,"
            " jsonb_build_object('fields', cast(:f as jsonb)))"
        ),
        {"p": str(patient_id), "pid": patient_id, "f": json.dumps(fields)},
    )
    return await _one(db, patient_id)
