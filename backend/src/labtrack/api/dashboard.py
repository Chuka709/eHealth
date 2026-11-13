"""Home dashboard (Phase 6.3; docs/06 §1, docs/08 "Нүүр").

`GET` - the profile's cards (its writers' own list, else the organ's), each with the latest
confirmed value as printed and in the catalog unit, the document's range, the server's flag,
a small spark and the change from the previous value (a plain number; none for viral loads);
and the latest values flagged by the document's ranges or the lab's critical mark, critical
first (rule 4: confirmed values only).
`PUT /cards` keeps the profile's own list (writers); `DELETE /cards` goes back to the organ's.
Numbers are strings (rule 7). Nothing here judges a value (rule 10b).
"""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field

from labtrack.api.deps import PatientReadDb, PatientWriteDb
from labtrack.api.errors import AppError, ErrorBody
from labtrack.api.numbers import num
from labtrack.api.ratelimit import per_user
from labtrack.config import get_settings
from labtrack.core import dashboard as core
from labtrack.dashboard import service

router = APIRouter(prefix="/patients/{patient_id}/dashboard", tags=["dashboard"])

_ERRORS: dict[int | str, dict[str, object]] = {
    s: {"model": ErrorBody} for s in (401, 403, 404, 422, 429)
}
_LIMIT = Depends(per_user("dashboard", lambda: get_settings().rate_document_read_per_minute))
# changes are audited: a lower limit of their own
_WRITE_LIMIT = Depends(
    per_user("dashboard_write", lambda: get_settings().rate_lab_review_per_minute)
)
TestCode = Annotated[str, Field(pattern=r"^[A-Z0-9_]{1,32}$")]


class ValueOut(BaseModel):
    result_id: UUID
    report_id: UUID
    collected_at: datetime
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
    flag: str
    possibly_critical: bool = Field(
        description="The lab marked it critical, or its printed critical range could not be"
        " used: shown as 'check the document', never called critical (Q60)."
    )


class SparkPoint(BaseModel):
    collected_at: datetime
    value: str
    comparator: str | None


class ChangeOut(BaseModel):
    percent: str  # whole percent, signed
    previous_value: str
    previous_collected_at: datetime


class CardOut(BaseModel):
    test_code: str
    name_mn: str
    name_en: str
    latest: ValueOut | None
    change: ChangeOut | None
    spark: list[SparkPoint]
    spark_unit: str | None  # every spark point is in this unit (it may differ from latest's)


class AttentionOut(BaseModel):
    test_code: str
    name_mn: str
    name_en: str
    latest: ValueOut


class DashboardOut(BaseModel):
    custom: bool
    cards: list[CardOut]
    attention: list[AttentionOut]


class CardsIn(BaseModel):
    test_codes: list[TestCode] = Field(max_length=core.MAX_CARDS)


def _value_out(v: service.Value) -> ValueOut:
    return ValueOut(
        result_id=v.result_id,
        report_id=v.report_id,
        collected_at=v.collected_at,
        raw_value=v.raw_value,
        raw_unit=v.raw_unit,
        comparator=v.comparator,
        value_text=v.value_text,
        qualitative=v.qualitative,
        value=num(v.value),
        unit=v.unit,
        ref_text=v.ref_text,
        ref_low=num(v.ref_low),
        ref_high=num(v.ref_high),
        flag=v.flag,
        possibly_critical=v.possibly_critical,
    )


def _change_out(c: core.Change | None) -> ChangeOut | None:
    if c is None or c.previous.value is None:
        return None
    return ChangeOut(
        percent=num(c.percent) or "0",
        previous_value=num(c.previous.value) or "0",
        previous_collected_at=c.previous.collected_at,
    )


@router.get("", response_model=DashboardOut, responses=_ERRORS, dependencies=[_LIMIT])
async def get_dashboard(patient_id: UUID, db: PatientReadDb) -> DashboardOut:
    found = await service.dashboard(db, patient_id, datetime.now(UTC))
    return DashboardOut(
        custom=found.custom,
        cards=[
            CardOut(
                test_code=c.test_code,
                name_mn=c.name_mn,
                name_en=c.name_en,
                latest=_value_out(c.latest) if c.latest is not None else None,
                change=_change_out(c.change),
                spark_unit=c.spark_unit,
                spark=[
                    SparkPoint(
                        collected_at=p.collected_at,
                        value=num(p.value) or "0",
                        comparator=p.comparator,
                    )
                    for p in c.spark
                    if p.value is not None
                ],
            )
            for c in found.cards
        ],
        attention=[
            AttentionOut(
                test_code=a.test_code,
                name_mn=a.name_mn,
                name_en=a.name_en,
                latest=_value_out(a.latest),
            )
            for a in found.attention
        ],
    )


@router.put(
    "/cards",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_ERRORS,
    dependencies=[_WRITE_LIMIT],
)
async def put_cards(patient_id: UUID, body: CardsIn, db: PatientWriteDb) -> Response:
    """The profile's own cards, in order (an empty list: none)."""
    try:
        await service.set_cards(db, patient_id, body.test_codes)
    except service.BadCardsError:
        raise AppError(422, "dashboard.bad_cards") from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/cards",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_ERRORS,
    dependencies=[_WRITE_LIMIT],
)
async def reset_cards(patient_id: UUID, db: PatientWriteDb) -> Response:
    """Back to the organ's cards."""
    await service.reset_cards(db, patient_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
