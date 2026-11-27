"""Printed values and reference ranges as numbers (core/lab_values.py; rules 5, 7)."""

import json
from decimal import Decimal
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from labtrack.core.lab_values import (
    NEGATIVE,
    POSITIVE,
    Range,
    Value,
    parse_decimal,
    parse_range,
    parse_value,
)

SEED = Path(__file__).resolve().parents[3] / "seed" / "lab_tests.json"
decimals = st.decimals(min_value=-10000, max_value=100000, places=3, allow_nan=False)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("5.37", Value(numeric=Decimal("5.37"))),
        ("12,4", Value(numeric=Decimal("12.4"))),
        ("1.410", Value(numeric=Decimal("1.410"))),  # trailing zero kept as printed
        ("<0.5", Value(numeric=Decimal("0.5"), comparator="<")),
        ("> 1000", Value(numeric=Decimal("1000"), comparator=">")),
        ("≤ 20", Value(numeric=Decimal("20"), comparator="<=")),
        ("1.2x10^3", Value(numeric=Decimal("1.2E+3"))),
        ("<2.5E+02", Value(numeric=Decimal("2.5E+2"), comparator="<")),
        ("(-)", Value(qualitative="negative", text="(-)")),
        ("-", Value(text="-")),  # "not done" as often as negative: not decided here
        ("Сөрөг (-)", Value(qualitative="negative", text="Сөрөг (-)")),
        ("not detected", Value(qualitative="negative", text="not detected")),
        ("2+", Value(qualitative="positive", text="2+")),
        ("+/-", Value(qualitative="equivocal", text="+/-")),
        ("trace", Value(text="trace")),
        ("1.2E+06", Value(numeric=Decimal("1.2E+6"))),
        ("1.2х10^5", Value(numeric=Decimal("1.2E+5"))),  # Cyrillic х
        ("−5", Value(numeric=Decimal("-5"))),  # minus sign
        ("0,123", Value(numeric=Decimal("0.123"))),  # 0,ddd can only be a decimal
        ("Neg", Value(qualitative="negative", text="Neg")),
        ("Сөрөг", Value(qualitative="negative", text="Сөрөг")),
        ("++", Value(qualitative="positive", text="++")),
        ("(+)", Value(qualitative="positive", text="(+)")),
        ("normal", Value(text="normal")),
        ("STRAW 02", Value(text="STRAW 02")),
        ("1,234", Value(text="1,234")),  # thousands mark or decimal comma? not guessed
        ("", Value()),
    ],
)
def test_printed_values(raw: str, expected: Value) -> None:
    assert parse_value(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("4.11 - 6.38", Range("interval", Decimal("4.11"), Decimal("6.38"))),
        ("3,5–5,1", Range("interval", Decimal("3.5"), Decimal("5.1"))),
        ("0 - 0", Range("interval", Decimal("0"), Decimal("0"))),
        ("-5 - 5", Range("interval", Decimal("-5"), Decimal("5"))),
        ("< 5", Range("upper", high=Decimal("5"))),
        ("<=5", Range("upper", high=Decimal("5"))),
        ("> 1.0", Range("lower", low=Decimal("1.0"))),
        ("<1.0 Normal -", Range("upper", high=Decimal("1.0"))),
        ("Эр: 62–115 / Эм: 44–97", Range("multiple")),
        ("M 62-115; F 44-97", Range("multiple")),
        ("(-) Normal -", Range("text")),
        ("(-) Clear - *", Range("text")),
        ("normal -", Range("text")),
        ("Neg -", Range("text")),
        ("-", Range("none")),
        ("", Range("none")),
        (None, Range("none")),
        ("9 - 3", Range("suspicious")),  # low above high: not used
        ("3 - 15 ng/ml", Range("interval", Decimal("3"), Decimal("15"))),  # unit set aside
        ("0-30 mg/g", Range("interval", Decimal("0"), Decimal("30"))),
        ("< 5 %", Range("upper", high=Decimal("5"))),
        ("62-115 Эр", Range("multiple")),  # a word, not a unit: not set aside
        ("1,000 - 5,000", Range("text")),  # thousands marks? not guessed
    ],
)
def test_printed_ranges(raw: str | None, expected: Range) -> None:
    assert parse_range(raw) == expected


@given(decimals)
def test_a_printed_number_reads_back_exactly_with_a_dot_or_a_comma(number: Decimal) -> None:
    text = f"{number:f}"
    assert parse_value(text).numeric == number
    if "." in text and len(text.split(".")[1]) != 3:
        assert parse_value(text.replace(".", ",")).numeric == number


@given(decimals, decimals, st.sampled_from([" - ", "-", " – ", "—"]))
def test_an_interval_reads_back_in_order_or_not_at_all(a: Decimal, b: Decimal, dash: str) -> None:
    low, high = sorted((a, b))
    assert parse_range(f"{low:f}{dash}{high:f}") == Range("interval", low, high)
    if low != high:
        assert parse_range(f"{high:f}{dash}{low:f}").kind == "suspicious"


@given(st.text(max_size=60))
def test_any_text_is_read_without_error_and_numbers_are_decimal(text: str) -> None:
    value = parse_value(text)
    assert value.numeric is None or isinstance(value.numeric, Decimal)
    printed = parse_range(text)
    assert printed.low is None or printed.high is None or printed.low <= printed.high


def test_qualitative_words_agree_with_the_seed_catalog() -> None:
    meta = json.loads(SEED.read_text(encoding="utf-8"))["_meta"]["qualitative_values"]
    assert set(meta["positive"]) <= POSITIVE
    assert set(meta["negative"]) - {"-"} <= NEGATIVE  # the lone dash: see lab_values
    assert "-" not in NEGATIVE


def test_thousands_or_decimal_comma_is_never_guessed() -> None:
    assert parse_decimal("1,234") is None
    assert parse_decimal("1,23") == Decimal("1.23")
