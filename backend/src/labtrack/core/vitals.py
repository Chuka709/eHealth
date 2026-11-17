"""Vitals as the user enters them (docs/08 "Амин үзүүлэлт"; user decision 2026-11-04).

One fixed unit per kind (no conversion: glucose in mmol/L only) and a plausibility range per
kind that catches a typo - 1200 mmHg, 120 "mmol/L" that was mg/dL. These are never a normal
range: the app shows no flag, colour or judgement of a value (CLAUDE.md rules 5, 10). The same
numbers are a CHECK in migration 0018.

A value is an exact decimal string ("128", "36,6" with a decimal comma); a thousands separator
is never guessed ("1,000" is refused - write 1000).
"""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal

VitalKind = Literal[
    "bp_systolic",
    "bp_diastolic",
    "pulse",
    "weight",
    "temperature",
    "glucose",
    "spo2",
    "urine_output",
    "fluid_intake",
]


@dataclass(frozen=True)
class VitalRule:
    unit: str
    low: Decimal
    high: Decimal
    decimals: int


RULES: dict[str, VitalRule] = {
    "bp_systolic": VitalRule("mmHg", Decimal(40), Decimal(300), 0),
    "bp_diastolic": VitalRule("mmHg", Decimal(20), Decimal(200), 0),
    "pulse": VitalRule("bpm", Decimal(20), Decimal(300), 0),  # infant SVT
    "weight": VitalRule("kg", Decimal(1), Decimal(400), 2),  # infants: 10 g steps
    "temperature": VitalRule("C", Decimal(30), Decimal(45), 1),
    # home meters read up to ~33.3 mmol/L; above 35 is most often mg/dL (Q47, migration 0045)
    "glucose": VitalRule("mmol_L", Decimal("0.5"), Decimal(35), 1),
    "spo2": VitalRule("percent", Decimal(50), Decimal(100), 0),
    "urine_output": VitalRule("ml", Decimal(0), Decimal(20000), 0),  # early diuresis
    "fluid_intake": VitalRule("ml", Decimal(0), Decimal(20000), 0),
}

# ASCII digits, up to 5 before and 3 after a point or comma - nothing else (no sign,
# exponent); trailing zeros ("36.60" from a device) do not count as decimals
_NUMBER = re.compile(r"^[0-9]{1,5}([.,][0-9]{1,3})?$")
# "1,000" / "1.500": a thousands separator or a decimal mark? never guessed (as dose amounts, H23)
_AMBIGUOUS = re.compile(r"^[1-9][0-9]{0,2}[.,][0-9]{3}$")


class VitalError(ValueError):
    """`reason`: "format" (not a plain number), "range" (implausible for the kind) or "order"
    (a blood-pressure reading with its numbers swapped)."""

    def __init__(self, reason: Literal["format", "range", "order"]) -> None:
        super().__init__(reason)
        self.reason = reason


def parse_vital(kind: str, text: str) -> Decimal:
    """The value as stored, or VitalError."""
    rule = RULES[kind]
    value = text.strip()
    if not _NUMBER.match(value) or _AMBIGUOUS.match(value):
        raise VitalError("format")
    try:
        number = Decimal(value.replace(",", "."))
    except InvalidOperation as exc:  # pragma: no cover - the pattern already rules it out
        raise VitalError("format") from exc
    exponent = number.normalize().as_tuple().exponent if number else 0
    decimals = -exponent if isinstance(exponent, int) and exponent < 0 else 0
    if decimals > rule.decimals:
        raise VitalError("format")
    if not rule.low <= number <= rule.high:
        raise VitalError("range")
    return Decimal(vital_text(number))  # stored without trailing zeros (the DB checks scale)


def check_reading(values: dict[str, Decimal]) -> None:
    """A blood-pressure reading whose upper number is not above the lower one is a typo
    (fields swapped): VitalError("order"). The same check for every source (manual entry and
    a future Apple Health / Health Connect import)."""
    systolic, diastolic = values.get("bp_systolic"), values.get("bp_diastolic")
    if systolic is not None and diastolic is not None and systolic <= diastolic:
        raise VitalError("order")


def vital_text(value: Decimal) -> str:
    """Canonical text: "36.6", "128" - no exponent, no trailing zeros."""
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text
