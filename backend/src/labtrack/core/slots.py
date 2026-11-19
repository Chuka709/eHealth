"""Scheduled dose instants and the monthly intake summary (docs/08 "Эм"; H7, Q22, Q23).

Bookkeeping only (CLAUDE.md rule 10): which doses the user's own schedule planned, and how
many of them the user recorded as taken or skipped. No threshold, no "good/bad", no advice.

Time zones (Q22): a medication in "home" mode is always on Ulaanbaatar time; in "local" mode
on the profile's time zone in force (`patient_timezones`, append-only). The phone's reminder
planner implements the same rules (mobile `planReminders`); both are checked against
`packages/shared/fixtures/dose-slots.json`, so a reminder, a recorded dose and the summary
meet on the same minute.

One dose per (day, "HH:MM") - never two, never none - and a switch never moves a dose that
was already due before it (medical review H1): starting from Ulaanbaatar, switches are applied
oldest first, and a switch at T moves a dose only when the dose falls at or after T both before
and after the move. Travelling east (UB -> Seoul at 07:30 UB) the 08:00 dose stays at 08:00 UB
(09:00 Seoul) rather than vanishing; travelling west (Seoul -> UB, landing 19:30 UB) the 20:00
dose already reminded at 20:00 Seoul is not reminded again at 20:00 UB.

A large eastward shift can bring two times of one day onto the same minute (08:00 kept on UB
time, 09:00 Seoul): both stay as separate doses with their own amounts (one record covers that
minute - OPEN_QUESTIONS Q26).
"""

import re
from bisect import bisect_left, bisect_right
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Literal, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from labtrack.core.medications import Dated, IntakeRecord, is_taken, merged_all

HOME_TIMEZONE = "Asia/Ulaanbaatar"
HOME = ZoneInfo(HOME_TIMEZONE)
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

Mode = Literal["home", "local"]


@dataclass(frozen=True)
class ZoneSwitch:
    timezone: str
    effective_at: datetime  # aware
    seq: int = 0


class Regimen(Dated, Protocol):
    @property
    def schedule(self) -> Mapping[str, object]: ...


@dataclass(frozen=True)
class RegimenPlan:
    effective_from: date
    seq: int
    schedule: Mapping[str, object]
    voided_at: datetime | None = None


@dataclass(frozen=True)
class MedicationPlan:
    mode: Mode
    started_on: date | None
    stopped_on: date | None
    planned_end_on: date | None
    regimens: Sequence[Regimen]


@dataclass(frozen=True)
class Slot:
    scheduled_at: datetime  # UTC, a whole minute
    local_day: date
    at: str  # "HH:MM" as written in the schedule
    amount: Decimal | None


def taken_on(plan: MedicationPlan, day: date) -> bool:
    """The medication is taken on this calendar day: started, not stopped, course not over.

    `stopped_on` is the first day it is no longer taken (Q21, as in `is_current`)."""
    return (
        (plan.started_on is None or plan.started_on <= day)
        and (plan.stopped_on is None or day < plan.stopped_on)
        and (plan.planned_end_on is None or day <= plan.planned_end_on)
    )


def order_zones(zones: Iterable[ZoneSwitch]) -> list[tuple[datetime, ZoneInfo]]:
    """Latest switch first (effective_at, then the database's insertion order)."""
    items = sorted(zones, key=lambda z: (z.effective_at, z.seq), reverse=True)
    out = []
    for z in items:
        try:
            out.append((z.effective_at, ZoneInfo(z.timezone)))
        except (ZoneInfoNotFoundError, ValueError):
            # a stored name the zone database no longer knows (the API accepts only known
            # ones): that switch is left out, the one before it stays in force
            continue
    return out


def _instant(day: date, at: str, zone: ZoneInfo) -> datetime:
    hour, minute = (int(p) for p in at.split(":"))
    # fold=0: a repeated wall time (clocks back) is its first occurrence; a skipped one (clocks
    # forward) takes the offset before the gap - a well-defined instant either way
    local = datetime.combine(day, time(hour, minute), tzinfo=zone)
    return local.astimezone(UTC).replace(second=0, microsecond=0)


def place(day: date, at: str, mode: Mode, zones: Sequence[tuple[datetime, ZoneInfo]]) -> datetime:
    """The instant of the dose written "HH:MM" on `day` (`zones` latest first, as
    `order_zones` gives them) - one, always, never moved back over a switch (module doc)."""
    moment = _instant(day, at, HOME)
    if mode == "home":
        return moment
    for effective_at, zone in reversed(zones):  # oldest first
        if moment >= effective_at:
            moved = _instant(day, at, zone)
            if moved >= effective_at:
                moment = moved
    return moment


def _times(schedule: Mapping[str, object], day: date) -> list[Mapping[str, object]]:
    kind = schedule.get("type")
    if kind not in ("daily", "weekly"):
        return []  # prn: no planned doses
    if kind == "weekly":
        days = schedule.get("days")
        if not isinstance(days, list) or day.isoweekday() not in days:
            return []
    times = schedule.get("times")
    return [t for t in times if isinstance(t, dict)] if isinstance(times, list) else []


def dose_slots(
    plan: MedicationPlan, zones: Iterable[ZoneSwitch], start: datetime, end: datetime
) -> list[Slot]:
    """Planned doses with start <= scheduled_at < end, in time order (aware datetimes)."""
    oldest_first = order_zones(zones)[::-1]
    starts = [eff for eff, _ in oldest_first]
    # every calendar day that can hold an instant of the window, in any zone (UTC-12..+14)
    first = (start - timedelta(days=1)).date()
    last = (end + timedelta(days=1)).date()
    out: list[Slot] = []
    # the dose history sorted once (as regimen_on orders it); walked forward day by day
    history = sorted(
        (r for r in plan.regimens if r.voided_at is None), key=lambda r: (r.effective_from, r.seq)
    )
    i, in_force = 0, None
    day = first
    while day <= last:
        while i < len(history) and history[i].effective_from <= day:
            in_force, i = history[i], i + 1
        if in_force is not None and taken_on(plan, day):
            near = _near(oldest_first, starts, day)
            for item in _times(in_force.schedule, day):
                slot = _slot(item, day, plan.mode, near)
                if slot is not None and start <= slot.scheduled_at < end:
                    out.append(slot)
        day += timedelta(days=1)
    return sorted(out, key=lambda s: (s.scheduled_at, s.at))


def _near(
    oldest_first: list[tuple[datetime, ZoneInfo]], starts: list[datetime], day: date
) -> list[tuple[datetime, ZoneInfo]]:
    """The switches that can place a dose of `day` (latest first, as `place` takes them).

    Every instant of a calendar day lies within [day 00:00 UTC - 14 h, day 24:00 UTC + 12 h]:
    a switch after that never moves it, and of the switches before it only the latest
    matters (each older one is overridden by it - the causal walk applies them all)."""
    first = datetime.combine(day, time(0), tzinfo=UTC) - timedelta(hours=14)
    last = datetime.combine(day, time(0), tzinfo=UTC) + timedelta(hours=36)
    lo = bisect_left(starts, first)
    hi = bisect_right(starts, last)
    return oldest_first[max(lo - 1, 0) : hi][::-1]


def _slot(
    item: Mapping[str, object], day: date, mode: Mode, zones: Sequence[tuple[datetime, ZoneInfo]]
) -> Slot | None:
    """One planned dose; None for a malformed stored item (one odd row never breaks a list -
    stored schedules are normalized on write, so this is a guard, not a path)."""
    at, amount = item.get("at"), item.get("amount")
    if not isinstance(at, str) or not _HHMM.match(at):
        return None
    try:
        value = Decimal(amount) if isinstance(amount, str) else None
    except InvalidOperation:
        return None
    if amount is not None and value is None:
        return None
    return Slot(place(day, at, mode, zones), day, at, value)


# --- monthly summary --------------------------------------------------------------------------


# A dose may still be recorded up to 24 hours after its time (api/records.py, Q25): until then
# it is "open", not "not recorded" - the existing recording window, not a new threshold.
RECORDING_WINDOW = timedelta(hours=24)


@dataclass(frozen=True)
class Summary:
    """Counts only (Q23: no "on time" threshold, no colour, no judgement)."""

    planned: int  # planned doses up to now
    taken: int  # recorded taken (on time or "late" - the user's own word)
    skipped: int
    unrecorded: int  # not recorded, and the recording window has passed
    open: int  # not recorded yet, still within the recording window

    @property
    def percent_taken(self) -> Decimal | None:
        """Share of closed planned doses (open ones left out) recorded taken, whole percent
        rounded down; None when none is closed."""
        closed = self.planned - self.open
        if closed <= 0:
            return None
        return Decimal(self.taken * 100 // closed)


def month_window(year: int, month: int) -> tuple[datetime, datetime]:
    """A calendar month in Ulaanbaatar (the profile's home), as an aware [start, end)."""
    start = datetime(year, month, 1, tzinfo=HOME)
    end = datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=HOME)  # noqa: PLR2004
    return start.astimezone(UTC), end.astimezone(UTC)


def summarize(
    slots: Sequence[Slot], records: Iterable[tuple[datetime, IntakeRecord]], now: datetime
) -> Summary:
    """Planned doses against recorded ones. A record whose time is no planned dose (a schedule
    changed after it was written, an as-needed dose) is not counted; two doses on one minute
    (Q26) share that minute's record."""
    by_minute: dict[datetime, list[IntakeRecord]] = {}
    for scheduled_at, record in records:
        key = scheduled_at.astimezone(UTC).replace(second=0, microsecond=0)
        by_minute.setdefault(key, []).append(record)
    taken = skipped = still_open = 0
    for slot in slots:
        found = by_minute.get(slot.scheduled_at)
        if not found:
            if slot.scheduled_at >= now - RECORDING_WINDOW:
                still_open += 1
            continue
        if is_taken(merged_all(found)):
            taken += 1
        else:
            skipped += 1
    unrecorded = len(slots) - taken - skipped - still_open
    return Summary(len(slots), taken, skipped, unrecorded, still_open)
