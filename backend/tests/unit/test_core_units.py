"""Units and one-factor conversion (core/units.py; rule 7, Q52)."""

import json
from decimal import Decimal
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from labtrack.core.text import normalize_unit
from labtrack.core.units import Limits, UnitSpec, convert, factor_for, implausible, known_unit

SEED = Path(__file__).resolve().parents[3] / "seed" / "lab_tests.json"
CATALOG = json.loads(SEED.read_text(encoding="utf-8"))
ALIASES = {normalize_unit(k): v for k, v in CATALOG["unit_aliases"].items()}


def _test(code: str) -> UnitSpec:
    t = next(t for t in CATALOG["tests"] if t["code"] == code)
    return UnitSpec(
        t["canonical_unit"],
        {c["from_unit"]: Decimal(str(c["factor"])) for c in t["unit_conversions"]},
        Decimal(str(t["physio_min"])) if t["physio_min"] is not None else None,
        Decimal(str(t["physio_max"])) if t["physio_max"] is not None else None,
    )


def test_every_conversion_goes_to_the_catalog_unit() -> None:
    for t in CATALOG["tests"]:
        for c in t["unit_conversions"]:
            assert c["to_unit"] == t["canonical_unit"], t["code"]
            assert Decimal(str(c["factor"])) > 0


def test_aliases() -> None:
    assert known_unit("мкмоль/л", ALIASES) == "µmol/L"
    assert known_unit(" MG/DL ", ALIASES) == "mg/dL"
    assert known_unit("μmol/l", ALIASES) == "µmol/L"  # Greek mu
    assert known_unit("бар/л", ALIASES) is None
    assert known_unit(None, ALIASES) is None


def test_creatinine_mg_dl_converts_value_and_limits_by_one_factor() -> None:
    out = convert(
        "мг/дл",
        _test("CREA"),
        ALIASES,
        value=Decimal("1.2"),
        reference=Limits(Decimal("0.7"), Decimal("1.3")),
        critical=Limits(None, Decimal("10")),
    )
    assert not isinstance(out, str)
    assert out.unit == "µmol/L"
    assert out.value == Decimal("106.08")
    assert out.reference == Limits(Decimal("61.88"), Decimal("114.92"))
    assert out.critical == Limits(None, Decimal("884.0"))


def test_catalog_unit_needs_no_conversion() -> None:
    out = convert("ммоль/л", _test("K"), ALIASES, value=Decimal("4.1"), reference=Limits(),
                  critical=Limits())  # fmt: skip
    assert not isinstance(out, str)
    assert out.factor == 1
    assert out.value == Decimal("4.1")


def test_reasons_when_not_converted() -> None:
    crea = _test("CREA")
    none = Limits()
    assert convert(None, crea, ALIASES, value=Decimal(1), reference=none, critical=none) == (
        "unit_missing"
    )
    assert convert("бар", crea, ALIASES, value=Decimal(1), reference=none, critical=none) == (
        "unknown_unit"
    )
    # a known unit with no factor for this test
    assert convert("г/л", crea, ALIASES, value=Decimal(1), reference=none, critical=none) == (
        "no_conversion"
    )


def test_urea_mg_dl_is_never_converted() -> None:
    """Urea or urea nitrogen? 2.14 times apart (Q52): only a labelled print converts."""
    assert factor_for("мг/дл", _test("UREA"), ALIASES) == "no_conversion"
    assert factor_for("mg/dL", _test("UREA"), ALIASES) == "no_conversion"


def test_implausible_only_outside_bounds() -> None:
    crea = _test("CREA")
    assert implausible(Decimal("3001"), crea)
    assert implausible(Decimal("4"), crea)
    assert not implausible(Decimal("90"), crea)
    assert not implausible(None, crea)


factors = st.decimals(min_value=Decimal("0.001"), max_value=1000, places=4)
numbers = st.decimals(min_value=0, max_value=100000, places=3)


@given(factors, numbers, numbers, numbers)
def test_one_factor_keeps_the_order_of_value_and_limits(
    factor: Decimal, value: Decimal, a: Decimal, b: Decimal
) -> None:
    low, high = min(a, b), max(a, b)
    test = UnitSpec("X", {"mg/dL": factor})
    out = convert("mg/dL", test, {"mg/dl": "mg/dL"}, value=value, reference=Limits(low, high),
                  critical=Limits(low, high))  # fmt: skip
    assert not isinstance(out, str)
    assert out.value == value * factor
    assert out.value is not None
    assert out.reference.low is not None
    assert out.reference.high is not None
    assert out.reference.low <= out.reference.high
    assert (value < low) == (out.value < out.reference.low)
    assert (value > high) == (out.value > out.reference.high)
    assert out.critical == out.reference
