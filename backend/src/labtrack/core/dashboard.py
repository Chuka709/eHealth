"""Home dashboard: which cards a profile shows, what is worth a look, and the small numbers on
each card (docs/06 §1, docs/08 "Нүүр"; rule 4, 5, 10b).

Bookkeeping only - nothing here judges a value. A value is "worth a look" only when the
document's own ranges flagged it (the flag `core/flags.py` computed at review); there is no
threshold of our own for "a big change" (that would be interpretation). The change from the
previous value is a plain number, shown with both values and dates.

- Default cards follow the organ(s) (docs/06 §1). The drug-level card is the level of the
  calcineurin/mTOR inhibitor the person takes (tacrolimus, cyclosporine, everolimus,
  sirolimus - several if several); with none recorded, a level the person already has results
  for; otherwise none (we do not presume a drug).
- The person's own list (`dashboard_cards`) replaces the defaults; an empty list is kept.
- Callers pass only CONFIRMED values (`latest_results`, confirmed history) and only the
  organs of transplants still in place (a lost graft does not choose cards).
- No percent change for viral loads (compared on a log scale clinically: 500 -> 5000 is one
  log, not "+900 %") - the two values and dates are shown instead (Q60).
- "Worth a look" is limited to values from the last `ATTENTION_DAYS` before the newest
  value, so an old critical result does not stand for the present (Q60; H32).
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from labtrack.core.flags import Flag

Organ = Literal[
    "kidney",
    "liver",
    "heart",
    "lung",
    "pancreas",
    "kidney_pancreas",
    "intestine",
    "cornea",
    "hsct",
    "other",
]
Comparator = Literal["<", "<=", ">", ">="]

LEVEL = "@level"  # placeholder in a default list: the drug-level card(s)
# the inhibitor levels a default card may show, in this order (docs/06 §1; MPA is not
# routinely followed, so it is a card only when the person pins it)
LEVEL_TESTS: tuple[str, ...] = ("TAC", "CSA", "EVR", "SIR")
MAX_CARDS = 24  # as the database checks (0038)
SPARK_POINTS = 10
MAX_ATTENTION = 5
ATTENTION_DAYS = 90
NO_PERCENT_CATEGORIES = frozenset({"virology"})

_KIDNEY = ("CREA", LEVEL, "HGB", "K", "UPCR", "BKV_DNA")
_LIVER = ("ALT", "AST", "TBIL", "GGT", "INR", LEVEL, "HBV_DNA", "HDV_RNA")
_THORACIC = (LEVEL, "CREA", "HGB", "CMV_DNA")
_GENERAL = (LEVEL, "CREA", "HGB")
DEFAULT_CARDS: dict[Organ, tuple[str, ...]] = {
    "kidney": _KIDNEY,
    "liver": _LIVER,
    "heart": _THORACIC,
    "lung": _THORACIC,
    "pancreas": (*_GENERAL, "GLU", "HBA1C"),
    "kidney_pancreas": (*_KIDNEY, "GLU", "HBA1C"),
    "intestine": _GENERAL,
    "cornea": (),  # usually no systemic immunosuppression: nothing presumed
    "hsct": _GENERAL,
    "other": _GENERAL,
}

_CRITICAL: frozenset[Flag] = frozenset({"critical_low", "critical_high"})
_NOT_ATTENTION: frozenset[Flag] = frozenset({"normal", "no_reference", "unknown"})


def default_cards(
    organs: Sequence[Organ], taken_levels: Iterable[str], has_results: Iterable[str]
) -> list[str]:
    """The cards for the organ(s) - `organs` most recent transplant first - with the level
    slot filled in. `taken_levels`: the level tests of the medications the person takes now;
    `has_results`: test codes with a confirmed value."""
    taken = {c for c in taken_levels if c in LEVEL_TESTS}
    have = set(has_results)
    levels = [c for c in LEVEL_TESTS if c in taken] or [c for c in LEVEL_TESTS if c in have]
    cards: list[str] = []
    for organ in organs:
        for code in DEFAULT_CARDS[organ]:
            for c in levels if code == LEVEL else (code,):
                if c not in cards:
                    cards.append(c)
    return cards


def card_codes(
    pinned: Sequence[str] | None,
    organs: Sequence[Organ],
    taken_levels: Iterable[str],
    has_results: Iterable[str],
) -> list[str]:
    """The person's own list when they made one (even empty), else the organ's."""
    if pinned is not None:
        return list(pinned)
    return default_cards(organs, taken_levels, has_results)


@dataclass(frozen=True)
class Point:
    """One confirmed value of a test, in the catalog unit."""

    result_id: str
    collected_at: datetime
    value: Decimal | None  # value_canonical; None when not numeric
    comparator: Comparator | None
    unit: str | None
    flag: Flag
    # the lab marked it critical, or its printed critical range could not be used
    # (`possible_critical`/`critical_unreadable` issues): sorted with the critical ones
    possibly_critical: bool = False


def _order(p: Point) -> tuple[datetime, str]:
    return (p.collected_at, p.result_id)


def spark(history: Sequence[Point], n: int = SPARK_POINTS) -> list[Point]:
    """The last `n` numeric points in the unit of the newest one, oldest first (a "< 0.5"
    keeps its comparator - the app draws it as a bound, not as a value). Points in another
    unit (a test without a conversion) never share the line."""
    numeric = sorted((p for p in history if p.value is not None), key=_order)
    if not numeric or n <= 0:
        return []
    unit = numeric[-1].unit
    return [p for p in numeric if p.unit == unit][-n:]


@dataclass(frozen=True)
class Change:
    previous: Point
    percent: Decimal  # whole percent, signed; plain arithmetic, no judgement


def change(latest: Point, history: Sequence[Point], category: str | None = None) -> Change | None:
    """The change from the value before `latest` (strictly earlier). Only when both are exact
    numbers in the same unit and the previous is not zero - a "< 0.5" has no exact value -
    and never for a viral load (`category` of the catalog test)."""
    if category in NO_PERCENT_CATEGORIES:
        return None
    if latest.value is None or latest.comparator is not None:
        return None
    earlier = [p for p in history if p.collected_at < latest.collected_at]
    if not earlier:
        return None
    previous = max(earlier, key=_order)
    if (
        previous.value is None
        or previous.comparator is not None
        or previous.unit != latest.unit
        or previous.value == 0
    ):
        return None
    pct = (latest.value - previous.value) / abs(previous.value) * 100
    return Change(previous=previous, percent=pct.quantize(Decimal(1), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class Latest:
    """A test's latest confirmed value (a `latest_results` row)."""

    test_code: str
    point: Point


def _critical_like(p: Point) -> bool:
    return p.flag in _CRITICAL or p.possibly_critical


def attention(
    latest: Iterable[Latest], limit: int = MAX_ATTENTION, days: int = ATTENTION_DAYS
) -> list[Latest]:
    """Latest values the document's ranges (or the lab's critical mark) flagged, from the last
    `days` before the newest value: critical first, then the newest. A test whose latest value
    is normal again is not listed, however it was before."""
    rows = list(latest)
    if not rows:
        return []
    since = max(x.point.collected_at for x in rows) - timedelta(days=days)
    flagged = [
        x
        for x in rows
        if x.point.collected_at >= since
        and (x.point.flag not in _NOT_ATTENTION or x.point.possibly_critical)
    ]
    flagged.sort(
        key=lambda x: (
            not _critical_like(x.point),
            -x.point.collected_at.timestamp(),
            x.test_code,
        )
    )
    return flagged[:limit]
