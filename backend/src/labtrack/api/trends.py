"""One test's trend chart (Phase 6.4; docs/06 §2, docs/08 "Хандлага", "Эмийн түвшин ↔ тун").

Every confirmed value with the reference and critical ranges ITS document printed (a lab
change shows as a change of the band - rule 5), the server's flag and the source document;
the recorded doses of the medicines linked to the test through the catalog (steps; never a
suggestion - rule 10); transplants and clinical events for the event lines; and the "days
since transplant" of each point, never running ahead of a month/year-only date (H24).
Confirmed values only (rule 4); numbers are strings (rule 7).
"""

from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel, Field

from labtrack.api.deps import PatientReadDb
from labtrack.api.errors import AppError, ErrorBody
from labtrack.api.numbers import num
from labtrack.api.ratelimit import per_user
from labtrack.config import get_settings
from labtrack.trends import repository, service

router = APIRouter(prefix="/patients/{patient_id}/trends", tags=["trends"])

_ERRORS: dict[int | str, dict[str, object]] = {
    s: {"model": ErrorBody} for s in (401, 403, 404, 422, 429)
}
_LIMIT = Depends(per_user("trend", lambda: get_settings().rate_document_read_per_minute))


class TrendTestOut(BaseModel):
    code: str
    name_mn: str
    name_en: str
    unit: str | None
    decimals: int
    kind: str
    category: str


class TrendPointOut(BaseModel):
    result_id: UUID
    report_id: UUID
    document_id: UUID | None  # the source document, when there is one (typed in: none)
    lab_name: str | None
    # the name as printed on the result (e.g. "eGFR (MDRD)"): the catalog name never says
    # which equation a lab used (Q69/Q70)
    raw_name: str
    collected_at: datetime
    collected_precision: str  # 'day': only the day was printed
    days_since_transplant: int | None
    # a month/year-only transplant date: the point falls in that window ("around it")
    around_transplant: bool
    raw_value: str
    raw_unit: str | None
    comparator: str | None
    value_text: str | None
    qualitative: str | None
    value: str | None  # in the catalog unit
    unit: str | None
    ref_text: str | None
    ref_low: str | None
    ref_high: str | None
    critical_text: str | None
    critical_low: str | None
    critical_high: str | None
    flag: str
    possibly_critical: bool = Field(
        description="The lab marked it critical, or its printed critical range could not be"
        " used: shown as 'check the document', never called critical (Q60)."
    )


class DoseStepOut(BaseModel):
    starts_on: date
    ends_before: date | None  # first day not in this step; null = still in force
    amount: str | None  # a dosing day's recorded total; null = none recorded (not drawn)
    schedule_type: str
    days: list[int]  # weekly: the ISO days it is taken (1 = Monday) - "on dosing days" only
    planned: bool  # starts after today: entered ahead, not history yet


class DoseSeriesOut(BaseModel):
    unit: str | None
    unit_text: str | None  # the person's own unit when `unit` is 'other'
    steps: list[DoseStepOut]


class DoseOut(BaseModel):
    medication_id: UUID
    name: str
    series: list[DoseSeriesOut]  # a change of unit starts a new series (H23)


class TrendTransplantOut(BaseModel):
    id: UUID
    organ: str
    transplant_date: date
    date_precision: str
    graft_status: str


class TrendEventOut(BaseModel):
    id: UUID
    kind: str
    title: str
    started_on: date
    ended_on: date | None


class TrendAxisOut(BaseModel):
    transplant_id: UUID
    day_zero: date  # the last possible day of the transplant
    approximate: bool


class TrendOut(BaseModel):
    test: TrendTestOut
    points: list[TrendPointOut]  # oldest first
    truncated: bool
    doses: list[DoseOut]
    transplants: list[TrendTransplantOut]
    events: list[TrendEventOut]
    axis: TrendAxisOut | None


class TestedOut(BaseModel):
    test_code: str
    name_mn: str
    name_en: str
    category: str
    results: int  # confirmed values
    latest: datetime


@router.get("", response_model=list[TestedOut], responses=_ERRORS, dependencies=[_LIMIT])
async def list_tested(patient_id: UUID, db: PatientReadDb) -> list[TestedOut]:
    """The tests the profile has confirmed values of, most recent first (rule 4)."""
    return [
        TestedOut(
            test_code=r.test_code,
            name_mn=r.name_mn,
            name_en=r.name_en,
            category=r.category,
            results=r.results,
            latest=r.latest,
        )
        for r in await repository.tested(db, patient_id)
    ]


@router.get("/{test_code}", response_model=TrendOut, responses=_ERRORS, dependencies=[_LIMIT])
async def get_trend(  # noqa: PLR0917 - path, filters and the session
    patient_id: UUID,
    test_code: Annotated[str, Path(pattern=r"^[A-Z0-9_]{1,32}$")],
    db: PatientReadDb,
    since: datetime | None = None,
    until: datetime | None = None,
    transplant_id: Annotated[UUID | None, Query()] = None,
) -> TrendOut:
    for moment in (since, until):
        if moment is not None and moment.tzinfo is None:
            raise AppError(422, "trend.naive_time")
    if since is not None and until is not None and since >= until:
        raise AppError(422, "trend.bad_range")
    try:
        found = await service.trend(
            db, patient_id, test_code, since=since, until=until, transplant_id=transplant_id
        )
    except service.UnknownTestError:
        raise AppError(404, "trend.unknown_test") from None
    except service.UnknownTransplantError:
        raise AppError(404, "trend.unknown_transplant") from None
    t = found.test
    return TrendOut(
        test=TrendTestOut(
            code=t.code,
            name_mn=t.name_mn,
            name_en=t.name_en,
            unit=t.canonical_unit,
            decimals=t.decimals,
            kind=t.kind,
            category=t.category,
        ),
        points=[
            TrendPointOut(
                result_id=p.row.id,
                report_id=p.row.report_id,
                document_id=p.row.document_id,
                lab_name=p.row.lab_name,
                raw_name=p.row.raw_name,
                collected_at=p.row.collected_at,
                collected_precision=p.row.collected_precision,
                days_since_transplant=p.days_since,
                around_transplant=p.around_transplant,
                raw_value=p.row.raw_value,
                raw_unit=p.row.raw_unit,
                comparator=p.row.comparator,
                value_text=p.row.value_text,
                qualitative=p.row.qualitative,
                value=num(p.row.value_canonical),
                unit=p.row.unit_canonical,
                ref_text=p.row.ref_text,
                ref_low=num(p.row.ref_low_canonical),
                ref_high=num(p.row.ref_high_canonical),
                critical_text=p.row.critical_text,
                critical_low=num(p.row.critical_low_canonical),
                critical_high=num(p.row.critical_high_canonical),
                flag=p.row.flag,
                possibly_critical=p.possibly_critical,
            )
            for p in found.points
        ],
        truncated=found.truncated,
        doses=[
            DoseOut(
                medication_id=d.medication_id,
                name=d.name,
                series=[
                    DoseSeriesOut(
                        unit=s.unit,
                        unit_text=s.unit_text,
                        steps=[
                            DoseStepOut(
                                starts_on=st.starts_on,
                                ends_before=st.ends_before,
                                amount=num(st.amount),
                                schedule_type=st.schedule_type,
                                days=list(st.days),
                                planned=st.planned,
                            )
                            for st in s.steps
                        ],
                    )
                    for s in d.series
                ],
            )
            for d in found.doses
        ],
        transplants=[
            TrendTransplantOut(
                id=x.id,
                organ=x.organ,
                transplant_date=x.transplant_date,
                date_precision=x.date_precision,
                graft_status=x.graft_status,
            )
            for x in found.transplants
        ],
        events=[
            TrendEventOut(
                id=e.id, kind=e.kind, title=e.title, started_on=e.started_on, ended_on=e.ended_on
            )
            for e in found.events
        ],
        axis=(
            TrendAxisOut(
                transplant_id=found.axis.transplant_id,
                day_zero=found.axis.day_zero,
                approximate=found.axis.approximate,
            )
            if found.axis is not None
            else None
        ),
    )
