"""core/trends.py - dose steps and the days-since axis (docs/06 §2; H8, H23, H24)."""

import itertools
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from labtrack.core.trends import Regimen, Series, day_total, day_zero, days_since
from labtrack.core.trends import dose_series as _dose_series

_TODAY = date(2030, 1, 1)


def dose_series(
    regimens: list[Regimen],
    started_on: date | None,
    stopped_on: date | None,
    planned_end_on: date | None,
    today: date = _TODAY,
) -> list[Series]:
    return _dose_series(regimens, started_on, stopped_on, planned_end_on, today)


def _daily(*amounts: str) -> dict[str, object]:
    times = [{"at": f"{8 + 12 * i:02d}:00", "amount": a} for i, a in enumerate(amounts)]
    return {"type": "daily", "times": times}


def _r(day: str, *amounts: str, seq: int = 1, unit: str | None = "mg", **kw: object) -> Regimen:
    return Regimen(
        effective_from=date.fromisoformat(day),
        seq=seq,
        voided_at=kw.get("voided"),  # type: ignore[arg-type]
        schedule=kw.get("schedule") or _daily(*amounts),  # type: ignore[arg-type]
        dose_unit=unit,
        dose_unit_text=kw.get("unit_text"),  # type: ignore[arg-type]
    )


def test_day_total_is_the_sum_of_the_recorded_amounts() -> None:
    assert day_total(_daily("2", "1.5")) == Decimal("3.5")
    weekly: dict[str, object] = {
        "type": "weekly",
        "days": [1, 4],
        "times": [{"at": "08:00", "amount": "5"}],
    }
    assert day_total(weekly) == Decimal(5)


def test_no_amounts_or_as_needed_have_no_total() -> None:
    assert day_total({"type": "daily", "times": [{"at": "08:00"}]}) is None
    assert day_total({"type": "prn"}) is None


def test_steps_follow_the_regimens_until_the_stop_day() -> None:
    (series,) = dose_series(
        [_r("2025-01-01", "2", "2"), _r("2025-03-10", "2", "1.5", seq=2)],
        started_on=date(2025, 1, 1),
        stopped_on=date(2025, 6, 1),
        planned_end_on=None,
    )
    assert series.unit == "mg"
    assert [(s.starts_on, s.ends_before, s.amount) for s in series.steps] == [
        (date(2025, 1, 1), date(2025, 3, 10), Decimal(4)),
        (date(2025, 3, 10), date(2025, 6, 1), Decimal("3.5")),  # the stop day is not taken
    ]


def test_the_latest_entered_wins_a_day_and_voided_rows_never_count() -> None:
    voided = datetime(2025, 1, 5, tzinfo=UTC)
    (series,) = dose_series(
        [
            _r("2025-01-01", "2", seq=1),
            _r("2025-01-01", "3", seq=2),  # a correction entered later
            _r("2025-02-01", "9", seq=3, voided=voided),
        ],
        started_on=None,
        stopped_on=None,
        planned_end_on=None,
    )
    assert [(s.starts_on, s.ends_before, s.amount) for s in series.steps] == [
        (date(2025, 1, 1), None, Decimal(3))
    ]


def test_a_planned_course_end_closes_the_step_the_next_day() -> None:
    (series,) = dose_series([_r("2025-01-01", "450")], None, None, date(2025, 3, 31))
    assert series.steps[0].ends_before == date(2025, 4, 1)


def test_a_change_of_unit_starts_a_new_series() -> None:
    out = dose_series(
        [_r("2025-01-01", "1", unit="mg"), _r("2025-02-01", "500", seq=2, unit="mcg")],
        None,
        None,
        None,
    )
    assert [(s.unit, len(s.steps)) for s in out] == [("mg", 1), ("mcg", 1)]


def test_a_regimen_after_the_stop_is_never_in_force() -> None:
    (series,) = dose_series(
        [_r("2025-01-01", "2"), _r("2025-07-01", "3", seq=2)], None, date(2025, 6, 1), None
    )
    assert [s.amount for s in series.steps] == [Decimal(2)]


def test_a_step_starts_no_earlier_than_the_medication() -> None:
    (series,) = dose_series([_r("2024-12-01", "2")], date(2025, 1, 1), None, None)
    assert series.steps[0].starts_on == date(2025, 1, 1)


def test_an_as_needed_regimen_is_a_step_without_an_amount() -> None:
    (series,) = dose_series([_r("2025-01-01", schedule={"type": "prn"})], None, None, None)
    assert (series.steps[0].amount, series.steps[0].schedule_type) == (None, "prn")


def test_days_since_counts_from_the_last_possible_day() -> None:
    exact = day_zero(date(2021, 6, 14), "day")
    assert (days_since(exact, date(2021, 6, 14)), exact.approximate) == (0, False)
    assert days_since(exact, date(2021, 6, 1)) == -13
    month = day_zero(date(2021, 6, 1), "month")
    assert (month.day, month.approximate) == (date(2021, 6, 30), True)
    year = day_zero(date(2021, 1, 1), "year")
    assert days_since(year, date(2022, 1, 1)) == 1


@given(
    st.dates(min_value=date(1990, 1, 1), max_value=date(2030, 12, 31)),
    st.sampled_from(["day", "month", "year"]),
    st.integers(min_value=0, max_value=20000),
)
def test_days_since_never_runs_ahead(stored: date, precision: str, offset: int) -> None:
    on = stored + timedelta(days=offset)
    zero = day_zero(stored, precision)  # type: ignore[arg-type]
    out = days_since(zero, on)
    assert out is None or out <= (on - stored).days
    if out is not None and out < 0:
        assert on < stored  # never "before" a day it may already be after


@given(
    st.dates(min_value=date(1990, 1, 1), max_value=date(2030, 12, 31)),
    st.sampled_from(["month", "year"]),
    st.integers(min_value=0, max_value=400),
)
def test_inside_the_uncertain_window_there_is_no_count(
    stored: date, precision: str, offset: int
) -> None:
    zero = day_zero(stored, precision)  # type: ignore[arg-type]
    on = stored + timedelta(days=offset)
    if on < zero.day:
        assert days_since(zero, on) is None


@given(
    st.lists(
        st.tuples(
            st.integers(min_value=0, max_value=400),
            st.integers(min_value=1, max_value=50),
            st.booleans(),
        ),
        max_size=12,
    )
)
def test_steps_never_overlap_and_are_in_order(rows: list[tuple[int, int, bool]]) -> None:
    base = date(2025, 1, 1)
    regimens = [
        _r((base + timedelta(days=d)).isoformat(), str(a), seq=n,
           voided=datetime(2025, 1, 1, tzinfo=UTC) if v else None)
        for n, (d, a, v) in enumerate(rows)
    ]  # fmt: skip
    steps = [s for series in dose_series(regimens, None, None, None) for s in series.steps]
    for a, b in itertools.pairwise(steps):
        assert a.ends_before == b.starts_on
        assert a.starts_on < b.starts_on


def test_a_year_only_transplant_counts_before_it_from_its_first_day() -> None:
    year = day_zero(date(2025, 1, 1), "year")
    assert days_since(year, date(2024, 12, 31)) == -1
    assert days_since(year, date(2025, 6, 1)) is None  # around the transplant
    assert days_since(year, date(2025, 12, 31)) == 0


def test_two_own_units_never_share_a_series() -> None:
    out = dose_series(
        [
            _r("2025-01-01", "1", unit="other", unit_text="капсул"),
            _r("2025-02-01", "2", seq=2, unit="other", unit_text="дусал"),
        ],
        None,
        None,
        None,
    )
    assert [(s.unit, s.unit_text) for s in out] == [("other", "капсул"), ("other", "дусал")]


def test_a_step_entered_ahead_is_planned() -> None:
    (series,) = dose_series(
        [_r("2025-01-01", "2"), _r("2025-02-01", "3", seq=2)], None, None, None,
        today=date(2025, 1, 15),
    )  # fmt: skip
    assert [s.planned for s in series.steps] == [False, True]


def test_weekly_steps_carry_their_days() -> None:
    weekly: dict[str, object] = {
        "type": "weekly",
        "days": [1, 4],
        "times": [{"at": "08:00", "amount": "5"}],
    }
    (series,) = dose_series([_r("2025-01-01", schedule=weekly)], None, None, None)
    assert (series.steps[0].days, series.steps[0].amount) == ((1, 4), Decimal(5))


def test_the_earlier_of_the_stop_and_the_course_end_closes_the_step() -> None:
    (series,) = dose_series([_r("2025-01-01", "2")], None, date(2025, 3, 1), date(2025, 1, 31))
    assert series.steps[0].ends_before == date(2025, 2, 1)
    (series,) = dose_series([_r("2025-01-01", "2")], None, date(2025, 1, 20), date(2025, 1, 31))
    assert series.steps[0].ends_before == date(2025, 1, 20)


def test_a_regimen_ending_before_the_medication_started_is_skipped() -> None:
    (series,) = dose_series(
        [_r("2024-11-01", "1"), _r("2024-12-01", "2", seq=2)], date(2024, 12, 15), None, None
    )
    assert [(s.starts_on, s.amount) for s in series.steps] == [(date(2024, 12, 15), Decimal(2))]
