"""A profile's timeline (Phase 6.5; docs/08 "Цагийн хэлхээс", docs/06 §5).

`GET` - one stream, newest first: transplants (with their date's precision - a month/year-only
date is shown as such, H24), medicines started / stopped (the stop day: the first day no
longer taken - Q21) / regimen changed (dose or schedule), clinical events, and confirmed lab
reports (how many results, how many carry a low/high/critical/abnormal flag - from the
document's ranges, the lab's mark or a doctor's target - and how many had no usable range:
counts, not a judgement). An entry dated after today is `planned` (entered ahead).
Filter by kind and, for reports, by lab (a lab alone: that lab's reports); `cursor` continues
where `next` left off. `GET /labs` - the labs of the profile's confirmed reports, for the
filter. Confirmed reports only (rule 4).
"""

import base64
import binascii
from datetime import UTC, date, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from labtrack.api.deps import PatientReadDb
from labtrack.api.errors import AppError, ErrorBody
from labtrack.api.ratelimit import per_user
from labtrack.config import get_settings
from labtrack.core.lab_drafts import LOCAL_ZONE
from labtrack.timeline import repository as repo

router = APIRouter(prefix="/patients/{patient_id}/timeline", tags=["timeline"])

_ERRORS: dict[int | str, dict[str, object]] = {
    s: {"model": ErrorBody} for s in (401, 403, 404, 422, 429)
}
_LIMIT = Depends(per_user("timeline", lambda: get_settings().rate_document_read_per_minute))
Kind = Literal[
    "transplant", "medication_started", "medication_stopped", "regimen_changed", "event", "report"
]


class TimelineItem(BaseModel):
    kind: Kind
    id: UUID  # the transplant, medicine, regimen, event or report
    day: date  # in Ulaanbaatar; a transplant's first possible day
    precision: str  # 'day' | 'month' | 'year' (transplant); 'day' | 'minute' (report)
    at: datetime | None  # a report's sample time
    title: str | None  # organ / medicine's name / event's title / lab
    detail: str | None  # graft status / event kind / report source ('read' | 'typed')
    ref_id: UUID | None  # regimen_changed: the medicine; report: its document
    until: date | None  # an event's end
    results: int | None  # report: how many results
    # report: how many carry a low/high/critical/abnormal flag (document range, lab mark or a
    # doctor's target) - a count, never "all fine" when 0
    flagged: int | None
    unflagged: int | None  # report: how many had no usable range (no_reference, unknown)
    planned: bool  # dated after today (Ulaanbaatar): entered ahead, not history yet


class TimelinePage(BaseModel):
    items: list[TimelineItem]
    next: str | None  # pass as `cursor` for the older items


class LabOut(BaseModel):
    lab_name: str
    reports: int
    latest: datetime | None


def _cursor(item: TimelineItem) -> str:
    raw = f"{item.day.isoformat()}|{repo.RANK[item.kind]}|{item.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _after(cursor: str | None) -> tuple[date, int, str] | None:
    if cursor is None:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        day, rank, item = raw.split("|")
        parsed = date.fromisoformat(day), int(rank), str(UUID(item))
    except (binascii.Error, UnicodeDecodeError, ValueError):
        raise AppError(422, "timeline.bad_cursor") from None
    if parsed[1] not in repo.RANK.values():  # a forged rank (int4 overflow would be a 500)
        raise AppError(422, "timeline.bad_cursor")
    return parsed


@router.get("", response_model=TimelinePage, responses=_ERRORS, dependencies=[_LIMIT])
async def get_timeline(  # noqa: PLR0917 - path, filters and the session
    patient_id: UUID,
    db: PatientReadDb,
    kinds: Annotated[list[Kind] | None, Query(max_length=6)] = None,
    lab: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> TimelinePage:
    rows = await repo.items(
        db,
        patient_id,
        # a lab filter alone means that lab's reports
        kinds=list(kinds) if kinds else ["report"] if lab else list(repo.KINDS),
        lab=lab,
        after=_after(cursor),
        limit=limit + 1,
        today=datetime.now(UTC).astimezone(LOCAL_ZONE).date(),
    )
    items = [
        TimelineItem(
            kind=r.kind,
            id=r.id,
            day=r.day,
            precision=r.precision,
            at=r.at,
            title=r.title,
            detail=r.detail,
            ref_id=r.ref_id,
            until=r.until_day,
            results=r.results,
            flagged=r.flagged,
            unflagged=r.unflagged,
            planned=r.planned,
        )
        for r in rows[:limit]
    ]
    more = len(rows) > limit
    return TimelinePage(items=items, next=_cursor(items[-1]) if more and items else None)


@router.get("/labs", response_model=list[LabOut], responses=_ERRORS, dependencies=[_LIMIT])
async def get_labs(patient_id: UUID, db: PatientReadDb) -> list[LabOut]:
    return [LabOut(lab_name=r.lab_name, reports=r.reports, latest=r.latest)
            for r in await repo.labs(db, patient_id)]  # fmt: skip
