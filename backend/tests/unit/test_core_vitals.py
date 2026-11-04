"""core/vitals.py: fixed units, plausibility ranges (not normal ranges), exact numbers."""

import re
from decimal import Decimal
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from labtrack.core.vitals import RULES, VitalError, check_reading, parse_vital, vital_text


@pytest.mark.parametrize(
    ("kind", "text", "value"),
    [
        ("bp_systolic", "128", Decimal(128)),
        ("temperature", "36,6", Decimal("36.6")),
        ("temperature", "36.6", Decimal("36.6")),
        ("glucose", "0.5", Decimal("0.5")),
        ("weight", "72.4", Decimal("72.4")),
        ("urine_output", "0", Decimal(0)),
        ("spo2", "100", Decimal(100)),
        ("weight", "7.45", Decimal("7.45")),  # an infant, to 10 g
        ("temperature", "36.60", Decimal("36.6")),  # a trailing zero from a device
        ("pulse", "280", Decimal(280)),  # infant SVT
    ],
)
def test_plausible_values(kind: str, text: str, value: Decimal) -> None:
    assert parse_vital(kind, text) == value


@pytest.mark.parametrize(
    ("kind", "text", "reason"),
    [
        ("bp_systolic", "1200", "range"),  # a typo
        ("glucose", "120", "range"),  # mg/dL written as mmol/L
        ("temperature", "29.9", "range"),
        ("spo2", "101", "range"),
        ("weight", "0", "range"),
        ("pulse", "72.5", "format"),  # whole beats
        ("temperature", "36.66", "format"),
        ("weight", "7.455", "format"),
        ("urine_output", "1,000", "format"),  # a thousands separator is never guessed
        ("weight", "-70", "format"),
        ("weight", "7e1", "format"),
        ("weight", "٧٠", "format"),  # Arabic-Indic digits
        ("weight", "", "format"),
    ],
)
def test_implausible_or_unclear_values_are_refused(kind: str, text: str, reason: str) -> None:
    with pytest.raises(VitalError) as exc:
        parse_vital(kind, text)
    assert exc.value.reason == reason


@given(kind=st.sampled_from(sorted(RULES)), tenths=st.integers(0, 100_000))
def test_every_accepted_value_is_inside_its_range_and_survives_a_round_trip(
    kind: str, tenths: int
) -> None:
    rule = RULES[kind]
    number = Decimal(tenths) / 10 if rule.decimals else Decimal(tenths // 10)
    text = vital_text(number)
    try:
        value = parse_vital(kind, text)
    except VitalError:
        assert not rule.low <= number <= rule.high or len(text.split(".")[0]) > 5
        return
    assert rule.low <= value <= rule.high
    assert parse_vital(kind, vital_text(value)) == value


def test_the_migration_checks_the_same_ranges() -> None:
    """One set of numbers: the API's messages and the database CHECK (0018) agree."""
    source = (
        Path(__file__).resolve().parents[2] / "alembic/versions/0018_health_records.py"
    ).read_text(encoding="utf-8")
    for kind, rule in RULES.items():
        low = re.escape(vital_text(rule.low))
        pattern = (
            rf'\("{kind}", "{rule.unit}", "?{low}"?, {vital_text(rule.high)}, {rule.decimals}\)'
        )
        assert re.search(pattern, source), kind


@pytest.mark.parametrize("kind", sorted(RULES))
def test_each_kind_takes_exactly_its_bounds(kind: str) -> None:
    rule = RULES[kind]
    step = Decimal(1).scaleb(-rule.decimals)
    assert parse_vital(kind, vital_text(rule.low)) == rule.low
    assert parse_vital(kind, vital_text(rule.high)) == rule.high
    for outside in (rule.high + step, rule.low - step):
        if outside < 0:
            continue
        with pytest.raises(VitalError):
            parse_vital(kind, vital_text(outside))


def test_a_swapped_blood_pressure_reading_is_refused() -> None:
    check_reading({"bp_systolic": Decimal(120), "bp_diastolic": Decimal(80)})
    for systolic, diastolic in ((80, 120), (90, 90)):
        with pytest.raises(VitalError) as exc:
            check_reading({"bp_systolic": Decimal(systolic), "bp_diastolic": Decimal(diastolic)})
        assert exc.value.reason == "order"
