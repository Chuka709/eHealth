"""Drug level statistics (core/level_stats.py; docs/06 §8a, H15)."""

import statistics
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from labtrack.core.level_stats import (
    MIN_VALUES,
    LevelPoint,
    collected_day,
    level_stats,
    settled_from,
)

UNIT = "ng/mL"
TX = [(date(2025, 1, 10), "day")]


def _p(day: date, value: str | None, *, comparator: str | None = None, unit: str = UNIT,
       low: str | None = None, high: str | None = None) -> LevelPoint:  # fmt: skip
    return LevelPoint(
        datetime.combine(day, time(1, 0), UTC),
        Decimal(value) if value is not None else None,
        comparator,
        unit,
        Decimal(low) if low else None,
        Decimal(high) if high else None,
    )


def test_no_transplant_no_number() -> None:
    stats = level_stats([_p(date(2026, 1, d), "7") for d in range(1, 8)], unit=UNIT, transplants=[])
    assert stats.reason == "no_transplant"
    assert stats.cv_percent is None


def test_the_first_three_months_are_left_out_and_counted() -> None:
    early = [_p(date(2025, 2, d), "15") for d in range(1, 6)]
    late = [
        _p(date(2025, 6, d), v) for d, v in zip(range(1, 6), ["6", "7", "8", "7", "7"], strict=True)
    ]
    stats = level_stats(early + late, unit=UNIT, transplants=TX)
    assert stats.early_left_out == 5
    assert stats.n == 5
    assert stats.mean == Decimal("7.00")


def test_fewer_than_five_values_give_a_reason_not_a_number() -> None:
    stats = level_stats([_p(date(2026, 1, d), "7") for d in range(1, 5)], unit=UNIT, transplants=TX)
    assert stats.reason == "too_few"
    assert stats.cv_percent is None
    assert stats.n == 4


def test_bounds_and_other_units_are_not_values() -> None:
    points = [_p(date(2026, 1, d), "7") for d in range(1, 6)]
    points += [_p(date(2026, 2, 1), "2", comparator="<"), _p(date(2026, 2, 2), "7", unit="nmol/L")]
    stats = level_stats(points, unit=UNIT, transplants=TX)
    assert stats.n == 5
    assert stats.bounds_left_out == 1
    assert stats.cv_percent == Decimal("0.0")


def test_cv_matches_the_sample_standard_deviation() -> None:
    values = ["5.2", "7.9", "6.1", "10.4", "8.0", "6.6"]
    stats = level_stats(
        [_p(date(2026, 1, i + 1), v) for i, v in enumerate(values)], unit=UNIT, transplants=TX
    )
    nums = [float(v) for v in values]
    expected = statistics.stdev(nums) / statistics.mean(nums) * 100
    assert stats.cv_percent is not None
    assert abs(float(stats.cv_percent) - expected) < 0.06


def test_time_in_target_uses_the_target_of_each_day() -> None:
    points = [
        _p(date(2026, 1, 1), "6", low="5", high="8"),
        _p(date(2026, 1, 2), "9", low="5", high="8"),
        _p(date(2026, 1, 3), "7", low="5", high="8"),
        _p(date(2026, 1, 4), "4", low="5", high="8"),
        _p(date(2026, 1, 5), "7"),  # no target in force that day
    ]
    stats = level_stats(points, unit=UNIT, transplants=TX)
    assert (stats.with_target, stats.in_target) == (4, 2)
    assert stats.in_target_percent == Decimal("50.0")


def test_a_month_or_year_only_transplant_counts_from_its_latest_day() -> None:
    assert settled_from(date(2025, 3, 1), "month") == date(2025, 3, 31) + timedelta(days=90)
    assert settled_from(date(2025, 1, 1), "year") == date(2025, 12, 31) + timedelta(days=90)
    assert settled_from(date(2025, 12, 1), "month") == date(2025, 12, 31) + timedelta(days=90)


def test_the_day_of_a_collection_is_ulaanbaatars() -> None:
    assert collected_day(datetime(2026, 3, 1, 17, 0, tzinfo=UTC)) == date(2026, 3, 2)


@given(
    st.lists(
        st.decimals(min_value=Decimal("0.5"), max_value=Decimal("40"), places=1),
        min_size=MIN_VALUES,
        max_size=40,
    )
)
def test_numbers_are_never_negative_and_mean_lies_within_the_values(values: list[Decimal]) -> None:
    points = [_p(date(2026, 1, 1) + timedelta(days=i), str(v)) for i, v in enumerate(values)]
    stats = level_stats(points, unit=UNIT, transplants=TX)
    assert stats.reason is None
    assert stats.mean is not None
    assert min(values) - Decimal("0.01") <= stats.mean <= max(values) + Decimal("0.01")
    assert stats.cv_percent is not None
    assert stats.cv_percent >= 0
    assert stats.in_target_percent is None  # no target given


def test_a_value_entered_twice_and_a_second_value_that_day_are_counted_apart() -> None:
    points = [_p(date(2026, 1, d), "7") for d in range(1, 6)]
    points.append(_p(date(2026, 1, 1), "7"))  # the same sample, entered again
    later = LevelPoint(datetime(2026, 1, 2, 6, 0, tzinfo=UTC), Decimal("12"), None, UNIT)
    stats = level_stats([*points, later], unit=UNIT, transplants=TX)
    assert (stats.n, stats.duplicates_left_out, stats.same_day_left_out) == (5, 1, 1)
    assert stats.mean == Decimal("7.00")


def test_boundaries_count_inside_and_a_one_sided_target_works() -> None:
    points = [
        _p(date(2026, 1, 1), "5", low="5", high="8"),
        _p(date(2026, 1, 2), "8", low="5", high="8"),
        _p(date(2026, 1, 3), "9", high="8"),
        _p(date(2026, 1, 4), "3", high="8"),
        _p(date(2026, 1, 5), "7", low="5"),
    ]
    stats = level_stats(points, unit=UNIT, transplants=TX)
    assert (stats.with_target, stats.in_target) == (5, 4)


def test_the_latest_transplant_and_text_values_and_units_are_reported() -> None:
    txs = [(date(2020, 1, 1), "day"), (date(2025, 6, 1), "month")]
    points = [_p(date(2026, 1, d), "7") for d in range(1, 6)]
    points += [_p(date(2026, 1, 6), None), _p(date(2026, 1, 7), "7", unit="nmol/L")]
    stats = level_stats(points, unit=UNIT, transplants=txs)
    assert stats.counted_from == date(2025, 6, 30) + timedelta(days=90)
    assert (stats.not_numeric_left_out, stats.other_unit_left_out) == (1, 1)
