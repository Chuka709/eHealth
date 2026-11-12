"""A printed result value and reference range, as numbers (docs/05 "Нормчлол"; rules 5, 7).

Only what is printed is turned into numbers - nothing is guessed or filled in:
- `parse_value("12,4")` -> 12.4; "<0.5" keeps its comparator; "(-)", "Neg", "Сөрөг (-)" are
  negative, "+", "2+", "++", "Эерэг" positive; anything else ("normal", "STRAW 02") stays text.
  A lone "-" is not read as negative here: in a number column it means "not done" as often
  as "negative" - only a qualitative test may take it as negative (Phase 5, medical review).
- `parse_range("3.5 - 5.1")` -> low 3.5, high 5.1; "< 5" -> high 5; "> 1.0" -> low 1.0; a unit
  printed after the range ("3-15 ng/ml") is set aside. Ranges by sex or age ("Эр: 62-115 /
  Эм: 44-97") are several ranges: none is picked (the text is kept for the person to read),
  and a range with low above high is not used.
- A comma before exactly three digits ("1,234") may be a thousands mark or a decimal comma:
  it is not read as a number at all (the reviewer types it); "0,123" can only be a decimal.
Numbers are `Decimal`s built from the printed digits (rule 7), never floats.
"""

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Final, Literal

Comparator = Literal["<", "<=", ">", ">="]
Qualitative = Literal["positive", "negative", "equivocal"]
RangeKind = Literal["interval", "upper", "lower", "text", "multiple", "suspicious", "none"]

# as in seed/lab_tests.json `_meta.qualitative_values` (a test keeps them in step) - except the
# lone "-" (see above) - plus printed forms seen on reports.
POSITIVE: Final = frozenset(
    {
        "эерэг",
        "positive",
        "pos",
        "+",
        "реактив",
        "reactive",
        "обнаружено",
        "илэрсэн",
        "detected",
    }
)
NEGATIVE: Final = frozenset(
    {
        "сөрөг",
        "negative",
        "neg",
        "(-)",
        "нереактив",
        "non-reactive",
        "non reactive",
        "nonreactive",
        "не обнаружено",
        "илрээгүй",
        "not detected",
    }
)
EQUIVOCAL: Final = frozenset({"equivocal", "borderline", "сомнительно", "эргэлзээтэй", "±", "+/-"})
LONE_DASH: Final = "-"

_NUM: Final = r"[+-]?\d+(?:[.,]\d+)?"
_CMP: Final = r"(<=|>=|≤|≥|<|>)"
_CMP_NAMES: Final[dict[str, Comparator]] = {
    "<": "<",
    "<=": "<=",
    "≤": "<=",
    ">": ">",
    ">=": ">=",
    "≥": ">=",
}
_VALUE: Final = re.compile(rf"^{_CMP}?\s*({_NUM})$")
# "1.2x10^3", "1.2×10^3", "1.2х10^3" (Cyrillic х), "1.2*10^3", "1.2E+03"
_SCIENTIFIC: Final = re.compile(
    rf"^{_CMP}?\s*({_NUM})\s*(?:[xх×*]\s*10\^|[eE])\s*([+-]?\d{{1,2}})$"
)
_GRADED: Final = re.compile(r"^(\+{2,4}|[1-4]\+)$")
_DASH: Final = r"[-–—]"
_INTERVAL: Final = re.compile(rf"^({_NUM})\s*{_DASH}\s*({_NUM})$")
_BOUND: Final = re.compile(rf"^{_CMP}\s*({_NUM})$")
# words printed after a bound ("<1.0 Normal") that say nothing more about it
_TRAILING_WORDS: Final = re.compile(r"\s+(normal|norm|норм|норма|хэвийн)$", re.IGNORECASE)
# a lone dash or star printed in an empty range cell ("(-) Normal -", "Clear - *")
_TRAILING_MARKS: Final = re.compile(r"(\s+[-*])+$")
# a unit printed after the range: a token with "/" or "%" ("ng/ml", "mg/g", "%")
_TRAILING_UNIT: Final = re.compile(r"^(.*\d)\s+(\S*[/%]\S*)$")
_NUMBERS_IN_TWO_RANGES: Final = 2  # "Эр: 62-115 / Эм: 44-97" has several; one is a bound
_MANY: Final = re.compile(r"[:;\n]|\b(эр|эм|male|female|муж|жен)\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Value:
    numeric: Decimal | None = None
    comparator: Comparator | None = None
    qualitative: Qualitative | None = None
    text: str | None = None  # printed text that is not a number


@dataclass(frozen=True, slots=True)
class Range:
    kind: RangeKind
    low: Decimal | None = None
    high: Decimal | None = None


def _clean(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("−", "-")  # minus sign
    return re.sub(r"\s+", " ", text).strip()


def parse_decimal(text: str) -> Decimal | None:
    """'12,4' -> 12.4, '1.410' -> 1.410, '0,123' -> 0.123; None for '1,234' (which is it?)."""
    if re.fullmatch(r"[+-]?[1-9]\d*,\d{3}", text):
        return None
    try:
        return Decimal(text.replace(",", "."))
    except InvalidOperation:
        return None


def _one_qualitative(word: str) -> Qualitative | None:
    if word in NEGATIVE:
        return "negative"
    if word in POSITIVE or _GRADED.match(word):
        return "positive"
    if word in EQUIVOCAL:
        return "equivocal"
    bare = word[1:-1].strip() if word.startswith("(") and word.endswith(")") else None
    if bare and bare != LONE_DASH:
        return _one_qualitative(bare)
    return None


def _qualitative(text: str) -> Qualitative | None:
    """The whole text, or every word of it agreeing ("Сөрөг (-)")."""
    key = text.casefold()
    whole = _one_qualitative(key)
    if whole is not None or " " not in key:
        return whole
    found: set[Qualitative | None] = {_one_qualitative(word) for word in key.split()}
    return found.pop() if len(found) == 1 else None


def parse_value(raw: str) -> Value:
    text = _clean(raw)
    if not text:
        return Value()
    if match := _VALUE.match(text):
        number = parse_decimal(match.group(2))
        if number is not None:
            cmp = _CMP_NAMES[match.group(1)] if match.group(1) else None
            return Value(numeric=number, comparator=cmp)
    if match := _SCIENTIFIC.match(text):
        mantissa = parse_decimal(match.group(2))
        if mantissa is not None:
            cmp = _CMP_NAMES[match.group(1)] if match.group(1) else None
            return Value(numeric=mantissa.scaleb(int(match.group(3))), comparator=cmp)
    return Value(qualitative=_qualitative(text), text=text)


def _interval(match: re.Match[str]) -> Range:
    low, high = parse_decimal(match.group(1)), parse_decimal(match.group(2))
    if low is None or high is None:
        return Range("text")
    return Range("interval", low, high) if low <= high else Range("suspicious")


def _bound(match: re.Match[str]) -> Range:
    bound = parse_decimal(match.group(2))
    if bound is None:
        return Range("text")
    if _CMP_NAMES[match.group(1)] in {"<", "<="}:
        return Range("upper", high=bound)
    return Range("lower", low=bound)


def _numbers(text: str) -> Range | None:
    if match := _INTERVAL.match(text):
        return _interval(match)
    if match := _BOUND.match(text):
        return _bound(match)
    return None


def parse_range(ref_text: str | None) -> Range:
    text = _TRAILING_WORDS.sub("", _TRAILING_MARKS.sub("", _clean(ref_text or ""))).strip()
    if not text or text in {"-", "*"}:
        return Range("none")
    found = _numbers(text)
    if found is None and (unit := _TRAILING_UNIT.match(text)):
        found = _numbers(unit.group(1))
    if found is not None:
        return found
    several = len(re.findall(_NUM, text)) >= _NUMBERS_IN_TWO_RANGES and _MANY.search(text)
    return Range("multiple" if several else "text")
