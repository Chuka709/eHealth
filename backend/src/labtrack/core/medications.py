"""Medication schedules, dose history and intake records (docs/08 "Эм", hazards H8, H20).

The app records what the user's doctor prescribed; nothing here suggests, checks or changes a
dose (CLAUDE.md rule 10). These are bookkeeping rules only:

- a schedule is a canonical, validated shape: times "HH:MM", each with its own amount when
  amounts are given (tacrolimus 2 mg at 08:00, 1.5 mg at 20:00), ISO weekdays 1-7;
- an amount is an exact decimal written by the user; a comma is a decimal comma ("1,5"), and
  "1,000" / "1.000" (a thousands separator or a decimal mark?) is refused as ambiguous;
- the dose in force on a day is the latest regimen row that started on or before it and was
  not voided (rows are never edited - a change or correction is a new row, ordered by the
  database's `seq`; a mistaken future row is voided, not deleted);
- two records of one scheduled dose merge so that "taken" always wins (H20).
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Protocol

ScheduleType = Literal["daily", "weekly", "prn"]
Status = Literal["taken", "late", "skipped"]

MAX_TIMES_PER_DAY = 12
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
# ASCII digits only (no other scripts, exponents, signs or underscores); 5 + 4 digits
_AMOUNT = re.compile(r"^[0-9]{1,5}([.,][0-9]{1,4})?$")
# "1,000" / "50.000" (German packs: "20.000 I.E."): a thousands separator or a decimal
# mark? never guessed - written without a separator (1000) or with fewer decimals (1.25).
# "0.125" (digoxin) is not ambiguous: a leading zero is never a thousands group.
_AMBIGUOUS = re.compile(r"^[1-9][0-9]{0,2}[.,][0-9]{3}$")


class ScheduleError(ValueError):
    """The schedule is not one the app can remind for."""


class AmountError(ValueError):
    """Not an exact, unambiguous dose amount."""


def parse_amount(text: str) -> Decimal:
    """An exact amount as the user wrote it: "2", "1.5", "1,5" (decimal comma)."""
    value = text.strip()
    if not _AMOUNT.match(value) or _AMBIGUOUS.match(value):
        raise AmountError("amount")
    amount = Decimal(value.replace(",", "."))
    if amount <= 0:
        raise AmountError("amount")
    return amount


def amount_text(amount: Decimal) -> str:
    """Canonical text of an amount: "1.5", "2" - never an exponent, no trailing zeros."""
    text = format(amount, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def normalize_schedule(raw: object) -> dict[str, object]:
    """The canonical schedule: unknown keys dropped, times sorted, amounts canonical.

    daily:  {"type": "daily", "times": [{"at": "08:00", "amount": "2"}, ...]}
    weekly: the same plus "days" (1 = Monday ... 7 = Sunday)
    prn:    {"type": "prn"} ("when needed": no times)
    Amounts are on every time or on none.
    """
    if not isinstance(raw, dict):
        raise ScheduleError("schedule")
    kind = raw.get("type")
    if kind == "prn":
        return {"type": "prn"}
    if kind not in ("daily", "weekly"):
        raise ScheduleError("type")
    times = raw.get("times")
    if not isinstance(times, list) or not 1 <= len(times) <= MAX_TIMES_PER_DAY:
        raise ScheduleError("times")
    slots: dict[str, dict[str, str]] = {}
    for item in times:
        slot = _slot(item)
        if slot["at"] in slots:
            raise ScheduleError("times")
        slots[slot["at"]] = slot
    if len({"amount" in s for s in slots.values()}) != 1:
        raise ScheduleError("amount")  # on every time or on none
    out: dict[str, object] = {"type": kind, "times": [slots[k] for k in sorted(slots)]}
    if kind == "weekly":
        out["days"] = _days(raw.get("days"))
    return out


def _slot(item: object) -> dict[str, str]:
    if not isinstance(item, dict) or not isinstance(item.get("at"), str):
        raise ScheduleError("times")
    at = item["at"]
    if not _TIME.match(at):
        raise ScheduleError("times")
    slot = {"at": at}
    if "amount" in item:
        if not isinstance(item["amount"], str):
            raise ScheduleError("amount")
        try:
            slot["amount"] = amount_text(parse_amount(item["amount"]))
        except AmountError as exc:
            raise ScheduleError("amount") from exc
    return slot


def _days(days: object) -> list[int]:
    if (
        not isinstance(days, list)
        or not days
        or not all(type(d) is int and 1 <= d <= 7 for d in days)  # noqa: PLR2004 - ISO day
        or len(set(days)) != len(days)
    ):
        raise ScheduleError("days")
    return sorted(days)


def has_amounts(schedule: dict[str, object]) -> bool:
    times = schedule.get("times")
    return isinstance(times, list) and bool(times) and "amount" in times[0]


class Dated(Protocol):
    @property
    def effective_from(self) -> date: ...
    @property
    def seq(self) -> int: ...
    @property
    def voided_at(self) -> datetime | None: ...


@dataclass(frozen=True)
class RegimenRow:
    effective_from: date
    seq: int
    voided_at: datetime | None = None


def regimen_on[R: Dated](rows: Iterable[R], day: date) -> R | None:
    """The regimen in force on `day`: the latest row (effective_from, then insertion order)
    that started on or before it and was not voided; None before the first one."""
    started = [r for r in rows if r.voided_at is None and r.effective_from <= day]
    return max(started, key=lambda r: (r.effective_from, r.seq), default=None)


def next_regimen[R: Dated](rows: Iterable[R], day: date) -> R | None:
    """The next scheduled change after `day` (not voided), so reminders planned ahead use the
    new dose from its first day - None if none is scheduled."""
    ahead = [r for r in rows if r.voided_at is None and r.effective_from > day]
    if not ahead:
        return None
    first = min(r.effective_from for r in ahead)
    return max((r for r in ahead if r.effective_from == first), key=lambda r: r.seq)


def upcoming_regimens[R: Dated](rows: Iterable[R], day: date) -> list[R]:
    """Every scheduled change after `day` (not voided), earliest first - one per starting day,
    the latest entered (as regimen_on). A steroid taper has several steps: a card kept offline
    shows them all instead of a dose that has silently gone out of date (H17)."""
    by_day: dict[date, R] = {}
    for r in rows:
        if r.voided_at is None and r.effective_from > day:
            kept = by_day.get(r.effective_from)
            if kept is None or r.seq > kept.seq:
                by_day[r.effective_from] = r
    return [by_day[d] for d in sorted(by_day)]


def is_current(stopped_on: date | None, planned_end_on: date | None, today: date) -> bool:
    """Still taken today: `stopped_on` (the first day no longer taken - Q21, as in
    `slots.taken_on`) not reached yet, and a planned course end (if any) not yet past. A stop
    entered ahead (the API takes none today; kept for safety) keeps it current (H17)."""
    return (stopped_on is None or stopped_on > today) and (
        planned_end_on is None or planned_end_on >= today
    )


@dataclass(frozen=True)
class IntakeRecord:
    status: Status
    taken_at: datetime | None


def merge_intake(stored: IntakeRecord, incoming: IntakeRecord) -> IntakeRecord:
    """Two records of the same scheduled dose (two devices, a retried tap) - H20.

    A dose recorded as taken (on time or late) stays taken: "skipped" never overwrites it.
    Between two taken records the earliest time is kept. Two "skipped" stay skipped.
    """
    if incoming.status == "skipped":
        return stored
    if stored.status == "skipped":
        return incoming
    return min(stored, incoming, key=_taken_order)


def _taken_order(record: IntakeRecord) -> tuple[datetime, bool]:
    # earliest time first; at the same instant "taken" before "late", so the result never
    # depends on which device wrote first
    if record.taken_at is None:
        raise ValueError("a taken dose has a time")
    return (record.taken_at, record.status != "taken")


def is_taken(record: IntakeRecord) -> bool:
    return record.status != "skipped"


def merged_all(records: Sequence[IntakeRecord]) -> IntakeRecord:
    """Fold any number of records of one dose (order does not matter - tested)."""
    result = records[0]
    for record in records[1:]:
        result = merge_intake(result, record)
    return result
