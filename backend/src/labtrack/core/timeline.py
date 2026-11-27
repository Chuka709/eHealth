"""Time since a transplant (docs/03 "Шилжүүлэн суулгалт ба эмийн тэмдэглэл"; timeline axis).

A transplant date may be known only to the month or the year (`date_precision`); it is stored
as the first day of that month/year. The time since is then counted from the LAST possible
day of that month/year, so it never overstates (the first months and the first year after a
transplant matter clinically - "1 year" must not be shown before it can be true).
`approximate` tells the app to show "≈" / "2015 онд" rather than an exact figure. Dates are
calendar dates in Mongolia (the caller passes the Ulaanbaatar "today").
"""

import calendar
from dataclasses import dataclass
from datetime import date
from typing import Literal

Precision = Literal["day", "month", "year"]


@dataclass(frozen=True)
class Elapsed:
    days: int  # whole days completed (at least)
    months: int  # whole calendar months completed (at least)
    years: int  # whole years completed (at least)
    approximate: bool  # the date is known only to the month or year


def latest_possible(stored: date, precision: Precision) -> date:
    """The last day the transplant can have been on."""
    if precision == "year":
        return date(stored.year, 12, 31)
    if precision == "month":
        return date(stored.year, stored.month, calendar.monthrange(stored.year, stored.month)[1])
    return stored


def _whole_months(start: date, end: date) -> int:
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return max(months, 0)


def elapsed_since(stored: date, precision: Precision, today: date) -> Elapsed | None:
    """Time since the transplant, never more than can be true; None if even the earliest
    possible day is still ahead (a mistyped date)."""
    if stored > today:
        return None
    start = min(latest_possible(stored, precision), today)
    months = _whole_months(start, today)
    return Elapsed(
        days=(today - start).days,
        months=months,
        years=months // 12,
        approximate=precision != "day",
    )
