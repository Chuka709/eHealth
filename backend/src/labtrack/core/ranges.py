"""Which printed range applies to this person, and what printed critical limits mean (rule 5).

Ranges come only from the document (or the person, or a doctor's target) - never the catalog.
- `reference_for`: a single printed range is used as printed. Several ranges by sex
  ("Эр: 62-115 / Эм: 44-97", "M 62-115; F 44-97") are used only when exactly one range is
  labelled for each sex and the profile's sex is known; ranges by age, or anything else with
  several numbers, are left as text for the person (none is picked).
- `critical_limits`: printed critical limits say when a value is critical, the other way round
  from a reference range: "< 2.5" means critical below 2.5 (a low limit), "> 6.5" critical
  above 6.5 (a high limit), "<2.5 / >6.5" (or ";", "или", "or") both, and "2.5 - 6.5"
  critical outside it (whether its ends are critical is not printed - `ends_unclear`).
  "≤"/"≥" make a value at the limit critical. Critical text that cannot be read is kept as
  `unreadable` (possibly critical), never dropped.
"""

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from typing import Final, Literal

from labtrack.core.lab_values import Range, parse_range, parse_value

Sex = Literal["male", "female", "unknown"]
Source = Literal["printed", "printed_for_sex"]

# longer words first: "эмэгтэй" before "эм", "эрэгтэй" before "эр"
_MALE: Final = r"эрэгтэй|эр|male|муж(?:чины|ской|\.)?|m"
_FEMALE: Final = r"эмэгтэй|эм|female|жен(?:щины|ский|\.)?|f|w"
_LABELLED: Final = re.compile(
    rf"^\s*(?:(?P<male>{_MALE})|(?P<female>{_FEMALE}))\s*[:.]?\s*(?P<range>.+?)\s*$",
    re.IGNORECASE,
)
_SEGMENTS: Final = re.compile(r"[/;\n|]")
_TWO_SEXES: Final = 2


@dataclass(frozen=True, slots=True)
class Reference:
    low: Decimal | None
    high: Decimal | None
    source: Source

    @property
    def is_set(self) -> bool:
        return self.low is not None or self.high is not None


def _numeric(found: Range) -> bool:
    return found.kind in {"interval", "upper", "lower"}


def _by_sex(ref_text: str) -> dict[str, Range] | None:
    """{'male': .., 'female': ..} when the text is exactly one range for each sex."""
    text = unicodedata.normalize("NFKC", ref_text)
    segments = [s for s in _SEGMENTS.split(text) if s.strip()]
    if len(segments) != _TWO_SEXES:
        return None
    found: dict[str, Range] = {}
    for segment in segments:
        match = _LABELLED.match(segment)
        if match is None:
            return None
        sex = "male" if match.group("male") else "female"
        printed = parse_range(match.group("range"))
        if sex in found or not _numeric(printed):
            return None
        found[sex] = printed
    return found if len(found) == _TWO_SEXES else None


def reference_for(ref_text: str | None, sex: Sex) -> Reference | None:
    """The printed reference range for this person, or None (none printed, or none to pick)."""
    printed = parse_range(ref_text)
    if _numeric(printed):
        return Reference(printed.low, printed.high, "printed")
    # "M 62-115 / F 44-97" (no colon) reads as text, "Эр: 62-115 / Эм: 44-97" as several
    if printed.kind not in {"multiple", "text"} or ref_text is None or sex == "unknown":
        return None
    ranges = _by_sex(ref_text)
    if ranges is None:
        return None
    mine = ranges[sex]
    return Reference(mine.low, mine.high, "printed_for_sex")


@dataclass(frozen=True, slots=True)
class Critical:
    """When a value is critical, as printed. `*_inclusive`: a value at the limit is critical
    ("≤ 2.5"); `ends_unclear`: a bare interval ("2.5 - 6.5") does not say whether its ends
    are critical - a value at an end is only possibly critical. `unreadable`: critical text is
    printed but cannot be read - the person must look (it is never dropped)."""

    low: Decimal | None  # critical below this
    high: Decimal | None  # critical above this
    low_inclusive: bool = False
    high_inclusive: bool = False
    ends_unclear: bool = False
    unreadable: bool = False


_BOTH_SIDES: Final = re.compile(r"\s*(?:/|;|\bили\b|\bor\b|,(?=\s*[<>≤≥]))\s*", re.IGNORECASE)


def _one_side(text: str) -> tuple[str, Decimal, bool] | None:
    """("low"|"high", limit, inclusive) for "< 2.5" / "≥ 6.5"; None otherwise."""
    value = parse_value(text)
    if value.numeric is None or value.comparator is None:
        return None
    side = "low" if value.comparator in {"<", "<="} else "high"
    return side, value.numeric, value.comparator in {"<=", ">="}


def critical_limits(critical_text: str | None) -> Critical | None:
    """Printed critical limits ("< 2.5" -> below 2.5 is critical), or None when none printed."""
    text = unicodedata.normalize("NFKC", critical_text or "").strip()
    if not text or text in {"-", "*"}:
        return None
    parts = [p for p in _BOTH_SIDES.split(text) if p.strip()]
    sides = [_one_side(p) for p in parts]
    if parts and all(s is not None for s in sides) and len(parts) <= _TWO_SEXES:
        found = {s[0]: s for s in sides if s is not None}
        if len(found) == len(parts):  # one limit for each side at most
            low, high = found.get("low"), found.get("high")
            if low is None or high is None or low[1] < high[1]:
                return Critical(
                    low[1] if low else None,
                    high[1] if high else None,
                    low_inclusive=bool(low and low[2]),
                    high_inclusive=bool(high and high[2]),
                )
    printed = parse_range(text)
    if printed.kind == "interval":
        return Critical(printed.low, printed.high, ends_unclear=True)
    return Critical(None, None, unreadable=True)
