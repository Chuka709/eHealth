"""Which planned doses a caregiver hears about (Phase 2.8e; docs/08 "Асран хамгаалагч"; H16).

Decision (a), user 2026-11-04/10: the server finds them, so an alert comes even when the
patient's phone is off. The server only knows that nothing was recorded for a dose - a dose
taken but recorded later, or recorded offline and not yet synced, looks the same - so the
alert asks to check ("шалгана уу"), never says "not taken" (CLAUDE.md rule 10b: no judgement).

A dose is announced when:
- its time plus the caregiver's delay (15-240 minutes, their own choice) has come, and
- nothing (taken or skipped) is recorded for that medication at that minute, and
- it became due less than ALERT_WINDOW ago. Older ones are left alone (decision 1, 2026-11-11):
  after a pause of the worker, or when alerts are switched on, a caregiver does not get a
  burst of the morning's doses (H16: too many alerts get ignored).

- the schedule already held it at its time (a regimen entered later is not held against the
  patient; planned_in_time).

Each dose is announced once per caregiver (dose_alerts is unique; the caller relies on it),
and a caregiver gets at most one notification per profile and run, however many doses are
due at once (security review M2, H16).
"""

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Protocol

from labtrack.core.medications import Dated, regimen_on
from labtrack.core.slots import Slot

ALERT_WINDOW = timedelta(minutes=60)
MIN_DELAY = timedelta(minutes=15)
MAX_DELAY = timedelta(minutes=240)


def _minute(at: datetime) -> datetime:
    return at.astimezone(UTC).replace(second=0, microsecond=0)


def alert_range(now: datetime, delay: timedelta) -> tuple[datetime, datetime]:
    """The [start, end) of dose times that can be announced at `now` - due (time + delay) in
    (now - ALERT_WINDOW, now] - in the half-open form dose_slots() takes."""
    if not MIN_DELAY <= delay <= MAX_DELAY:
        raise ValueError("delay")
    tick = timedelta(microseconds=1)
    return now - delay - ALERT_WINDOW + tick, now - delay + tick


class PlannedRegimen(Dated, Protocol):
    @property
    def created_at(self) -> datetime: ...


def planned_in_time(slot: Slot, regimens: Iterable[PlannedRegimen]) -> bool:
    """The dose was in the schedule at its own time: the regimen in force on its day was
    entered before the dose time (medical review 3: a schedule changed at 13:10 to a 12:45 dose
    "from today" must not announce the 12:45 dose as unrecorded)."""
    regimen = regimen_on(regimens, slot.local_day)
    return regimen is not None and regimen.created_at <= slot.scheduled_at


def overdue_slots(
    slots: Sequence[Slot], recorded: Iterable[datetime], now: datetime, delay: timedelta
) -> list[Slot]:
    """The planned doses to announce now, in time order (one per minute)."""
    start, end = alert_range(now, delay)
    done = {_minute(at) for at in recorded}
    out: dict[datetime, Slot] = {}
    for slot in slots:
        # two times of a day on one minute (Q26) share one record and one alert
        if start <= slot.scheduled_at < end and slot.scheduled_at not in done:
            out.setdefault(slot.scheduled_at, slot)
    return [out[at] for at in sorted(out)]
