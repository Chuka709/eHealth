"""A result's flag from what the document printed (docs/05 "Flag"; rules 4-5).

In this order, and only from the document:
1. critical limits printed for the row (`core.ranges.critical_limits`) -> critical_low/high;
2. a numeric reference range printed for the row (`core.ranges.reference_for`) -> low, high or
   normal; a qualitative reference ("Сөрөг") -> normal when the value agrees, abnormal when
   it is the opposite;
3. no usable reference but a printed lab mark (H, L, ↑, ↓, HH, LL, *) -> that mark, with
   `flag_source = lab_flag` (a mark that is not known -> unknown);
4. a range printed that cannot be used (by sex with the sex unknown, by age, text)
   -> unknown; nothing printed -> no_reference.
A value with a comparator is a range of values: "<0.5" against a high limit of 5 is normal,
">1000" against 200 is high, "<5" against a low limit of 2 cannot be told -> unknown (never
guessed). A value at a reference limit is inside the range ("< 5" with 5 -> normal: the
printed number is the limit). At a critical limit it is critical only when "≤"/"≥" is printed.
`possibly_critical` - the critical banner shows for it as for a critical flag (H5): a critical
limit the value may cross but cannot be told; a value at the end of a bare critical interval;
critical text that cannot be read; or the lab's own critical mark (HH, LL, H*, L*) on a value
the printed limits do not call critical (the flag stays as computed).
`mismatch`: the lab's mark points another way than the printed range (H on a value in range).
`critical_inside_reference`: printed critical limits inside the reference range (a misread
column, likely) - for the person to check; the flag stays as computed.
`outside_target` is a separate label for a doctor's target (it never changes the flag).
The comparisons are made in the printed unit - limits and value were printed in one unit.
"""

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from typing import Final, Literal

from labtrack.core.lab_values import Value, parse_range, parse_value
from labtrack.core.ranges import Critical, Reference

Flag = Literal[
    "normal",
    "low",
    "high",
    "critical_low",
    "critical_high",
    "abnormal",
    "no_reference",
    "unknown",
]
FlagSource = Literal["computed_document_range", "lab_flag", "none"]
Mark = Literal["low", "high", "critical_low", "critical_high", "abnormal", "unknown"]

# Latin only: a Cyrillic "Н" looks like H but may be "низкий" (low) - it stays an unknown mark
_MARKS: Final[dict[str, Mark]] = {
    "H": "high",
    "HI": "high",
    "HIGH": "high",
    "↑": "high",
    "L": "low",
    "LO": "low",
    "LOW": "low",
    "↓": "low",
    "HH": "critical_high",
    "↑↑": "critical_high",
    "LL": "critical_low",
    "↓↓": "critical_low",
    # "*" may mean critical or only "abnormal" next to H/L: high/low, possibly critical
    "H*": "high",
    "L*": "low",
    "*": "abnormal",
    "!": "abnormal",
    "A": "abnormal",
    "ABN": "abnormal",
}
_CRITICAL_MARKS: Final = frozenset({"HH", "↑↑", "LL", "↓↓", "H*", "L*"})
# printed in an empty flag cell, or a value's sign - not a mark
_NO_MARK: Final = frozenset({"-", "+", "N", "NORMAL"})
_MARK_SPACES: Final = re.compile(r"[\s()\[\]]+")
_HIGH_SIDE: Final = frozenset({"high", "critical_high"})
_LOW_SIDE: Final = frozenset({"low", "critical_low"})


@dataclass(frozen=True, slots=True)
class FlagResult:
    flag: Flag
    source: FlagSource
    mismatch: bool = False
    possibly_critical: bool = False
    critical_inside_reference: bool = False


@dataclass(frozen=True, slots=True)
class _Span:
    """The values a printed value may be: [low, high], each end open or closed."""

    low: Decimal | None
    low_open: bool
    high: Decimal | None
    high_open: bool

    def below(self, bound: Decimal, *, inclusive: bool = False) -> bool | None:
        """Is every value < bound (<= when inclusive) - True, none - False, or not told - None?"""
        if self.high is not None and (
            self.high < bound or (self.high == bound and (inclusive or self.high_open))
        ):
            return True
        if self.low is not None and (
            self.low > bound or (self.low == bound and not (inclusive and not self.low_open))
        ):
            return False
        return None

    def above(self, bound: Decimal, *, inclusive: bool = False) -> bool | None:
        if self.low is not None and (
            self.low > bound or (self.low == bound and (inclusive or self.low_open))
        ):
            return True
        if self.high is not None and (
            self.high < bound or (self.high == bound and not (inclusive and not self.high_open))
        ):
            return False
        return None


def _span(value: Value) -> _Span | None:
    n = value.numeric
    if n is None:
        return None
    match value.comparator:
        case "<":
            return _Span(None, False, n, True)
        case "<=":
            return _Span(None, False, n, False)
        case ">":
            return _Span(n, True, None, False)
        case ">=":
            return _Span(n, False, None, False)
        case None:
            return _Span(n, False, n, False)


def _mark_key(lab_flag: str | None) -> str | None:
    if lab_flag is None:
        return None
    key = _MARK_SPACES.sub("", unicodedata.normalize("NFKC", lab_flag)).upper()
    return None if not key or key in _NO_MARK else key


def lab_mark(lab_flag: str | None) -> Mark | None:
    """What a printed lab mark says: H/↑ high, L/↓ low, HH/LL critical, * abnormal; another
    mark (a Cyrillic "Н": high or "низкий"?) -> unknown."""
    key = _mark_key(lab_flag)
    return None if key is None else _MARKS.get(key, "unknown")


def _critical(span: _Span, critical: Critical) -> tuple[Flag | None, bool]:
    """(critical flag or None, whether the value is possibly critical)."""
    below = (
        span.below(critical.low, inclusive=critical.low_inclusive)
        if critical.low is not None
        else False
    )
    above = (
        span.above(critical.high, inclusive=critical.high_inclusive)
        if critical.high is not None
        else False
    )
    if below:
        return "critical_low", False
    if above:
        return "critical_high", False
    at_end = critical.ends_unclear and bool(
        (critical.low is not None and span.below(critical.low, inclusive=True))
        or (critical.high is not None and span.above(critical.high, inclusive=True))
    )
    return None, below is None or above is None or at_end


def _inside_reference(critical: Critical | None, reference: Reference | None) -> bool:
    if critical is None or reference is None:
        return False
    low_inside = (
        critical.low is not None and reference.low is not None and critical.low > reference.low
    )
    high_inside = (
        critical.high is not None and reference.high is not None and critical.high < reference.high
    )
    return low_inside or high_inside


def _against_range(span: _Span, reference: Reference) -> Flag:
    below = span.below(reference.low) if reference.low is not None else False
    above = span.above(reference.high) if reference.high is not None else False
    if below:
        return "low"
    if above:
        return "high"
    if below is False and above is False:
        return "normal"
    return "unknown"


def _against_text(value: Value, ref_text: str | None) -> Flag | None:
    """A qualitative value against a printed qualitative reference ("Сөрөг")."""
    if value.qualitative is None or ref_text is None:
        return None
    expected = parse_value(ref_text).qualitative
    if expected not in {"negative", "positive"}:
        return None
    if value.qualitative == expected:
        return "normal"
    if value.qualitative == "equivocal":
        return "unknown"
    return "abnormal"


def _mismatch(flag: Flag, mark: Mark | None) -> bool:
    if mark in {None, "unknown"} or flag in {"unknown", "no_reference"}:
        return False
    if flag == "abnormal":  # a qualitative result: H or L says nothing more
        return False
    if mark in _HIGH_SIDE:
        return flag not in _HIGH_SIDE
    if mark in _LOW_SIDE:
        return flag not in _LOW_SIDE
    return flag == "normal"  # another mark ("*") on a value the range calls normal


def compute_flag(
    value: Value,
    *,
    reference: Reference | None,
    ref_text: str | None,
    critical: Critical | None,
    lab_flag: str | None,
) -> FlagResult:
    """The flag from the document only (see the module docstring for the order)."""
    span = _span(value)
    mark = lab_mark(lab_flag)
    inside = _inside_reference(critical, reference)
    possibly = False
    if critical is not None and critical.unreadable:
        possibly = span is not None or value.qualitative is not None or value.text is not None
    elif span is not None and critical is not None:
        flag, possibly = _critical(span, critical)
        if flag is not None:
            return FlagResult(flag, "computed_document_range", _mismatch(flag, mark), False, inside)
    computed: Flag | None
    if reference is not None and reference.is_set:
        computed = _against_range(span, reference) if span is not None else "unknown"
    else:
        computed = _against_text(value, ref_text)
    lab_says_critical = _mark_key(lab_flag) in _CRITICAL_MARKS
    if computed is not None:
        # the lab's own critical mark is never lost to a range that does not call it critical
        mismatch = _mismatch(computed, mark) or (lab_says_critical and computed != "unknown")
        return FlagResult(
            computed, "computed_document_range", mismatch, possibly or lab_says_critical, inside
        )
    if mark is not None:
        marked_critical = mark in {"critical_low", "critical_high"}
        return FlagResult(
            mark,
            "lab_flag",
            possibly_critical=possibly or (lab_says_critical and not marked_critical),
        )
    # a range is printed but none can be used (by sex with no sex known, by age, text):
    # "unknown", never "no reference" - the person reads the printed text
    printed = parse_range(ref_text).kind not in {"none"}
    fallback: Flag = "unknown" if printed else "no_reference"
    return FlagResult(fallback, "none", possibly_critical=possibly)


def outside_target(value: Value, low: Decimal | None, high: Decimal | None) -> bool | None:
    """Outside a doctor's target (True / False), or cannot be told (None). A label only."""
    span = _span(value)
    if span is None or (low is None and high is None):
        return None
    below = span.below(low) if low is not None else False
    above = span.above(high) if high is not None else False
    if below or above:
        return True
    if below is False and above is False:
        return False
    return None
