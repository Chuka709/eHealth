"""Trend chart helpers (Phase 6.4; docs/06 §2, docs/08 "Эмийн түвшин ↔ тун"; H8, H24).

Bookkeeping only (rule 10, 10b): the dose steps are what the person recorded from their
doctor, laid out in time - nothing here compares a dose with a level or suggests one.

- Dose steps: one step per regimen in force (voided rows never; the latest entered wins on a
  day), from its first day until the next regimen, the stop day (the first day no longer
  taken - Q21) or the day after a planned course end. The step's amount is the recorded
  total of a dosing day (daily: every day; weekly: on its days) - None when the schedule has
  no amounts (or is "when needed"), so nothing is drawn rather than guessed. A change of unit
  starts a new series: mg and mcg never share an axis (H23).
- Days since transplant: counted from the LAST possible day of a month/year-only date, as
  `core/timeline.py`, so the axis never runs ahead (H24); `approximate` then. A day inside
  that uncertain window (on or after the earliest possible day, before the last) has no
  count - it is neither "before" nor "after" the transplant (shown as "around it").
- A step that starts after today is marked `planned` (entered ahead, not history yet).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from labtrack.core.timeline import Precision, latest_possible

ScheduleType = Literal["daily", "weekly", "prn"]


@dataclass(frozen=True)
class Regimen:
    effective_from: date
    seq: int
    voided_at: datetime | None
    schedule: dict[str, object]  # normalized (core.medications.normalize_schedule)
    dose_unit: str | None
    dose_unit_text: str | None = None  # the person's own unit when `dose_unit` is 'other'


@dataclass(frozen=True)
class Step:
    starts_on: date
    ends_before: date | None  # first day not in this step; None = still in force
    amount: Decimal | None  # a dosing day's recorded total
    schedule_type: ScheduleType
    days: tuple[int, ...] = ()  # weekly: the ISO days it is taken (1 = Monday)
    planned: bool = False  # starts after today


@dataclass(frozen=True)
class Series:
    unit: str | None
    unit_text: str | None  # with `unit` 'other': two different own units never share a series
    steps: list[Step]


def day_total(schedule: dict[str, object]) -> Decimal | None:
    """The recorded total of one dosing day, or None (no amounts, or as needed)."""
    if schedule.get("type") not in ("daily", "weekly"):
        return None
    times = schedule.get("times")
    if not isinstance(times, list) or not times:
        return None
    amounts = [t.get("amount") for t in times if isinstance(t, dict)]
    if len(amounts) != len(times) or not all(isinstance(a, str) for a in amounts):
        return None
    return sum((Decimal(str(a)) for a in amounts), Decimal(0))


def _in_force(rows: Iterable[Regimen]) -> list[Regimen]:
    """The regimen of each starting day (latest entered), voided rows left out, in order."""
    by_day: dict[date, Regimen] = {}
    for r in rows:
        if r.voided_at is not None:
            continue
        kept = by_day.get(r.effective_from)
        if kept is None or r.seq > kept.seq:
            by_day[r.effective_from] = r
    return [by_day[d] for d in sorted(by_day)]


def _end(stopped_on: date | None, planned_end_on: date | None) -> date | None:
    ends = [stopped_on] if stopped_on is not None else []
    if planned_end_on is not None:
        ends.append(planned_end_on + timedelta(days=1))
    return min(ends, default=None)


def dose_series(
    regimens: Iterable[Regimen],
    started_on: date | None,
    stopped_on: date | None,
    planned_end_on: date | None,
    today: date,
) -> list[Series]:
    """The dose steps of one medication, split where the unit changes."""
    end = _end(stopped_on, planned_end_on)
    rows = _in_force(regimens)
    series: list[Series] = []
    for i, r in enumerate(rows):
        start = max(r.effective_from, started_on) if started_on else r.effective_from
        nxt = rows[i + 1].effective_from if i + 1 < len(rows) else None
        stop = min((d for d in (nxt, end) if d is not None), default=None)
        if stop is not None and stop <= start:
            continue  # superseded or after the stop: never in force
        step = Step(
            starts_on=start,
            ends_before=stop,
            amount=day_total(r.schedule),
            schedule_type=_type(r.schedule),
            days=_weekdays(r.schedule),
            planned=start > today,
        )
        unit_text = r.dose_unit_text if r.dose_unit == "other" else None
        if series and (series[-1].unit, series[-1].unit_text) == (r.dose_unit, unit_text):
            series[-1].steps.append(step)
        else:
            series.append(Series(unit=r.dose_unit, unit_text=unit_text, steps=[step]))
    return series


def _weekdays(schedule: dict[str, object]) -> tuple[int, ...]:
    days = schedule.get("days") if schedule.get("type") == "weekly" else None
    return tuple(d for d in days if isinstance(d, int)) if isinstance(days, list) else ()


def _type(schedule: dict[str, object]) -> ScheduleType:
    kind = schedule.get("type")
    if kind == "weekly":
        return "weekly"
    if kind == "prn":
        return "prn"
    return "daily"


@dataclass(frozen=True)
class DayZero:
    """The transplant the "days since" axis counts from."""

    day: date  # the last possible day of the transplant
    earliest: date  # the first possible day (the stored date)
    approximate: bool


def day_zero(stored: date, precision: Precision) -> DayZero:
    return DayZero(
        day=latest_possible(stored, precision), earliest=stored, approximate=precision != "day"
    )


def days_since(zero: DayZero, on: date) -> int | None:
    """Whole days from the transplant to `on`: counted from its last possible day after it,
    to its first possible day before it (negative) - never more than can be true either way.
    None inside the uncertain window of a month/year-only date (around the transplant)."""
    if on >= zero.day:
        return (on - zero.day).days
    if on < zero.earliest:
        return (on - zero.earliest).days
    return None
