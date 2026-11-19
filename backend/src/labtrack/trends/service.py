"""One test's trend (Phase 6.4; docs/06 §2): its confirmed values, each with the range its own
document printed; the recorded doses of the medicines linked to it; clinical events; and the
"days since transplant" of every point - composed from `core/trends.py` (rule 6)."""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import Row
from sqlalchemy.ext.asyncio import AsyncSession

from labtrack.core import trends as core
from labtrack.core.lab_drafts import LOCAL_ZONE
from labtrack.core.timeline import Precision
from labtrack.trends import repository as repo

_POSSIBLY_CRITICAL = frozenset({"possible_critical", "critical_unreadable"})


class UnknownTestError(LookupError):
    pass


class UnknownTransplantError(LookupError):
    pass


@dataclass(frozen=True)
class Point:
    row: Row[Any]
    possibly_critical: bool
    days_since: int | None
    around_transplant: bool  # inside the uncertain window of a month/year-only date


@dataclass(frozen=True)
class Dose:
    medication_id: UUID
    name: str
    series: list[core.Series]


@dataclass(frozen=True)
class Axis:
    transplant_id: UUID
    day_zero: date
    approximate: bool


@dataclass(frozen=True)
class Trend:
    test: Row[Any]
    points: list[Point]  # oldest first
    truncated: bool  # older points left out (MAX_POINTS)
    doses: list[Dose]
    transplants: list[Row[Any]]
    events: list[Row[Any]]
    axis: Axis | None


def _days(zero: core.DayZero | None, at: datetime) -> int | None:
    return None if zero is None else core.days_since(zero, at.astimezone(LOCAL_ZONE).date())


async def trend(
    db: AsyncSession,
    patient_id: UUID,
    code: str,
    *,
    since: datetime | None,
    until: datetime | None,
    transplant_id: UUID | None,
) -> Trend:
    test = await repo.test(db, code)
    if test is None:
        raise UnknownTestError
    transplants = list(await repo.transplants(db, patient_id))
    if transplant_id is not None:
        chosen = next((t for t in transplants if t.id == transplant_id), None)
        if chosen is None:
            raise UnknownTransplantError
    else:
        chosen = transplants[0] if transplants else None
    axis = None
    zero = None
    if chosen is not None:
        zero = core.day_zero(chosen.transplant_date, cast(Precision, chosen.date_precision))
        axis = Axis(chosen.id, zero.day, zero.approximate)

    rows = list(await repo.points(db, patient_id, code, since, until))
    truncated = len(rows) > repo.MAX_POINTS
    points = [
        Point(
            row=r,
            possibly_critical=bool(_POSSIBLY_CRITICAL & set(r.issues or ())),
            days_since=(days := _days(zero, r.collected_at)),
            around_transplant=zero is not None and days is None,
        )
        for r in reversed(rows[: repo.MAX_POINTS])
    ]

    today = datetime.now(UTC).astimezone(LOCAL_ZONE).date()
    meds = list(await repo.linked_medications(db, patient_id, code))
    by_med: dict[UUID, list[core.Regimen]] = {m.id: [] for m in meds}
    for r in await repo.regimens(db, patient_id, list(by_med)):
        by_med[r.medication_id].append(
            core.Regimen(
                effective_from=r.effective_from,
                seq=r.seq,
                voided_at=r.voided_at,
                schedule=r.schedule,
                dose_unit=r.dose_unit,
                dose_unit_text=r.dose_unit_text,
            )
        )
    doses = [
        Dose(
            medication_id=m.id,
            name=m.name,
            series=core.dose_series(
                by_med[m.id], m.started_on, m.stopped_on, m.planned_end_on, today
            ),
        )
        for m in meds
    ]
    return Trend(
        test=test,
        points=points,
        truncated=truncated,
        doses=doses,
        transplants=transplants,
        events=list(await repo.events(db, patient_id)),
        axis=axis,
    )
