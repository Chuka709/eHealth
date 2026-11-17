"""Drug level statistics for the doctor and the patient (docs/06 §8a; hazard H15; Phase 7.4).

For a level test (tacrolimus and the like): the mean, the coefficient of variation (CV%) and
the share of values inside the doctor's target - numbers only. No threshold, no colour, no
"good/bad", never a dose suggestion (CLAUDE.md rule 10b). Computed only from:

- confirmed values with an exact number, in the test's catalog unit; whatever is left out is
  counted by its reason (a bound like "< 2", text, another unit, the early weeks, a value
  entered twice, a second value on the same day - only the day's first counts, Q63);
- taken at least 3 months after the latest transplant - on the latest day it may have been
  when only its month or year is known (the early weeks are expected to swing);
- at least 5 such values; fewer, and the reason is given instead of a number;
- for tacrolimus only, for now (LEVEL_STATS_TESTS): which level tests and which samples
  (trough) a doctor decides (Q63).

CV% = sample standard deviation / mean x 100. "In target" uses the target in force on each
value's day and the same reading of a printed value as the flags (`outside_target`).
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from labtrack.core.flags import outside_target
from labtrack.core.lab_values import Value

_UB = ZoneInfo("Asia/Ulaanbaatar")
MIN_VALUES = 5
LEVEL_STATS_TESTS: tuple[str, ...] = ("TAC",)
SETTLE_DAYS = 90  # "≥ 3 сарын дараах"

Reason = Literal["no_transplant", "too_few", "zero_mean"]


@dataclass(frozen=True, slots=True)
class LevelPoint:
    collected_at: datetime  # when the sample was taken
    value: Decimal | None  # in the catalog unit; None when not a plain number
    comparator: str | None  # "<", ">" ... : a bound, not a value
    unit: str | None
    target_low: Decimal | None = None  # the doctor's target in force that day
    target_high: Decimal | None = None

    @property
    def collected_on(self) -> date:
        return collected_day(self.collected_at)


@dataclass(frozen=True, slots=True)
class LevelStats:
    n: int
    mean: Decimal | None
    sd: Decimal | None
    cv_percent: Decimal | None
    with_target: int  # values that had a target in force
    in_target: int
    in_target_percent: Decimal | None
    counted_from: date | None  # the first day that could count (3 months after the transplant)
    bounds_left_out: int  # "< x" / "> x" values
    not_numeric_left_out: int  # printed text that is not a number
    other_unit_left_out: int  # not in the catalog unit
    early_left_out: int  # within 3 months of the transplant
    duplicates_left_out: int  # the same value at the same time (entered twice)
    same_day_left_out: int  # a second value on one day: only the day's first counts (Q63)
    used: tuple[LevelPoint, ...]
    reason: Reason | None  # why no number is given


def settled_from(transplant_day: date, precision: str) -> date:
    """The first day counted: 3 months after the latest day the transplant may have been."""
    if precision == "year":
        latest = date(transplant_day.year, 12, 31)
    elif precision == "month":
        nxt = date(
            transplant_day.year + transplant_day.month // 12, transplant_day.month % 12 + 1, 1
        )
        latest = nxt - timedelta(days=1)
    else:
        latest = transplant_day
    return latest + timedelta(days=SETTLE_DAYS)


def _round(x: Decimal, places: str = "0.1") -> Decimal:
    return x.quantize(Decimal(places), rounding=ROUND_HALF_UP)


def level_stats(
    points: list[LevelPoint],
    *,
    unit: str,
    transplants: list[tuple[date, str]],
) -> LevelStats:
    """The numbers for these points (any order); `unit` is the catalog unit. Counting starts 3
    months after the latest transplant (the one whose first countable day is latest)."""
    if not transplants:
        return LevelStats(
            n=0, mean=None, sd=None, cv_percent=None, with_target=0, in_target=0,
            in_target_percent=None, counted_from=None, bounds_left_out=0,
            not_numeric_left_out=0, other_unit_left_out=0, early_left_out=0,
            duplicates_left_out=0, same_day_left_out=0, used=(), reason="no_transplant",
        )  # fmt: skip
    start = max(settled_from(d, p) for d, p in transplants)
    other_unit = [p for p in points if p.unit != unit]
    in_unit = [p for p in points if p.unit == unit]
    early = [p for p in in_unit if p.collected_on < start]
    late = [p for p in in_unit if p.collected_on >= start]
    bounds = [p for p in late if p.comparator is not None]
    text = [p for p in late if p.comparator is None and p.value is None]
    exact = sorted(
        (p for p in late if p.comparator is None and p.value is not None),
        key=lambda p: p.collected_at,
    )
    seen: set[tuple[datetime, Decimal | None]] = set()
    days: set[date] = set()
    used_list: list[LevelPoint] = []
    duplicates = same_day = 0
    for p in exact:
        if (p.collected_at, p.value) in seen:
            duplicates += 1
            continue
        seen.add((p.collected_at, p.value))
        if p.collected_on in days:
            same_day += 1
            continue
        days.add(p.collected_on)
        used_list.append(p)
    used = tuple(used_list)
    counts = {
        "bounds_left_out": len(bounds), "not_numeric_left_out": len(text),
        "other_unit_left_out": len(other_unit), "early_left_out": len(early),
        "duplicates_left_out": duplicates, "same_day_left_out": same_day,
    }  # fmt: skip
    values = [p.value for p in used if p.value is not None]
    if len(values) < MIN_VALUES:
        return LevelStats(
            n=len(values), mean=None, sd=None, cv_percent=None, with_target=0, in_target=0,
            in_target_percent=None, counted_from=start, used=used, reason="too_few", **counts,
        )  # fmt: skip
    n = Decimal(len(values))
    mean = sum(values, Decimal(0)) / n
    if mean <= 0:
        return LevelStats(
            n=len(values), mean=_round(mean, "0.01"), sd=None, cv_percent=None, with_target=0,
            in_target=0, in_target_percent=None, counted_from=start, used=used,
            reason="zero_mean", **counts,
        )  # fmt: skip
    variance = sum(((v - mean) ** 2 for v in values), Decimal(0)) / (n - 1)
    sd = variance.sqrt()
    judged = [
        outside_target(Value(numeric=p.value), p.target_low, p.target_high)
        for p in used
        if p.target_low is not None or p.target_high is not None
    ]
    told = [j for j in judged if j is not None]
    inside = sum(1 for j in told if j is False)
    return LevelStats(
        n=len(values),
        mean=_round(mean, "0.01"),
        sd=_round(sd, "0.01"),
        cv_percent=_round(sd / mean * 100),
        with_target=len(told),
        in_target=inside,
        in_target_percent=_round(Decimal(inside) / len(told) * 100) if told else None,
        counted_from=start,
        used=used,
        reason=None,
        **counts,
    )


def collected_day(at: datetime) -> date:
    """The Ulaanbaatar day of a collection time."""
    return at.astimezone(_UB).date()
