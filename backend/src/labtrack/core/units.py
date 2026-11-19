"""A printed unit, and a value with its printed limits in the catalog unit (docs/05; rule 7).

- The printed unit is looked up in `unit_aliases` (normalised: case, spaces, µ/μ); a unit
  that is not listed is unknown - never guessed from its look.
- A value goes to the catalog unit only by the test's own listed factor (`unit_conversions`),
  and the value, the reference and the critical limits all by the same factor: they then stay
  in the same order to each other. No factor listed -> nothing is converted (the printed
  numbers stay; the trend shows only rows in the catalog unit).
- Products are exact `Decimal`s (no rounding here: display rounds by the catalog's decimals).
- A test whose unit is ambiguous in print has no plain alias for that print: urea "мг/дл" may
  be urea or urea nitrogen (2.14 times apart - Q52), so the catalog lists only
  "mg/dL (urea)", which no printed unit normalises to.
- `implausible`: a converted value outside the catalog's physiological bounds - a misread
  comma or unit, not a clinical judgement.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from labtrack.core.text import normalize_unit

UnitIssue = Literal["unit_missing", "unknown_unit", "no_conversion"]


@dataclass(frozen=True, slots=True)
class UnitSpec:
    canonical_unit: str | None
    factors: Mapping[str, Decimal]  # known unit -> factor to the canonical unit
    physio_min: Decimal | None = None
    physio_max: Decimal | None = None


@dataclass(frozen=True, slots=True)
class Limits:
    low: Decimal | None = None
    high: Decimal | None = None


@dataclass(frozen=True, slots=True)
class Converted:
    unit: str
    factor: Decimal
    value: Decimal | None
    reference: Limits
    critical: Limits


def known_unit(raw_unit: str | None, aliases: Mapping[str, str]) -> str | None:
    """The unit a printed unit names, or None when it is not listed."""
    if raw_unit is None or not raw_unit.strip():
        return None
    return aliases.get(normalize_unit(raw_unit))


def factor_for(
    raw_unit: str | None, test: UnitSpec, aliases: Mapping[str, str]
) -> Decimal | UnitIssue:
    """The factor from the printed unit to the test's catalog unit, or why there is none."""
    if test.canonical_unit is None:
        return "no_conversion"
    if raw_unit is None or not raw_unit.strip():
        return "unit_missing"
    unit = known_unit(raw_unit, aliases)
    if unit is None:
        # the catalog unit printed exactly as the catalog spells it is known without an alias
        if raw_unit.strip() == test.canonical_unit:
            return Decimal(1)
        return "unknown_unit"
    if unit == test.canonical_unit:
        return Decimal(1)
    factor = test.factors.get(unit)
    return factor if factor is not None else "no_conversion"


def _scale(number: Decimal | None, factor: Decimal) -> Decimal | None:
    return None if number is None else number * factor


def convert(
    raw_unit: str | None,
    test: UnitSpec,
    aliases: Mapping[str, str],
    *,
    value: Decimal | None,
    reference: Limits,
    critical: Limits,
) -> Converted | UnitIssue:
    """Value, reference and critical limits in the catalog unit, by one factor (rule 7)."""
    factor = factor_for(raw_unit, test, aliases)
    if not isinstance(factor, Decimal):
        return factor
    assert test.canonical_unit is not None  # noqa: S101 - factor_for checked it
    return Converted(
        unit=test.canonical_unit,
        factor=factor,
        value=_scale(value, factor),
        reference=Limits(_scale(reference.low, factor), _scale(reference.high, factor)),
        critical=Limits(_scale(critical.low, factor), _scale(critical.high, factor)),
    )


def implausible(value: Decimal | None, test: UnitSpec) -> bool:
    """Outside the physiological bounds - for a value in the catalog unit only."""
    if value is None:
        return False
    low, high = test.physio_min, test.physio_max
    return (low is not None and value < low) or (high is not None and value > high)
