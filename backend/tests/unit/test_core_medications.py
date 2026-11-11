"""core.medications and core.timeline - properties (hypothesis) and examples."""

import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from itertools import permutations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from labtrack.core.medications import (
    AmountError,
    IntakeRecord,
    RegimenRow,
    ScheduleError,
    amount_text,
    is_current,
    is_taken,
    merge_intake,
    merged_all,
    next_regimen,
    normalize_schedule,
    parse_amount,
    regimen_on,
)
from labtrack.core.timeline import elapsed_since, latest_possible

_times = st.builds(lambda h, m: f"{h:02d}:{m:02d}", st.integers(0, 23), st.integers(0, 59))
_moment = st.datetimes(
    # hypothesis takes naive bounds and adds the zone itself
    min_value=datetime(2020, 1, 1),  # noqa: DTZ001
    max_value=datetime(2030, 1, 1),  # noqa: DTZ001
    timezones=st.just(UTC),
)
_record = st.one_of(
    st.builds(IntakeRecord, st.just("skipped"), st.none()),
    st.builds(IntakeRecord, st.sampled_from(["taken", "late"]), _moment),
)
_amounts = st.decimals(
    min_value=Decimal("0.0001"), max_value=Decimal("99999.9999"), places=4, allow_nan=False
)


# --- amounts ------------------------------------------------------------------------------------


@given(_amounts)
def test_an_amount_survives_writing_and_reading(amount: Decimal) -> None:
    text = amount_text(amount)
    assert "e" not in text.lower()
    if re.fullmatch(r"[1-9][0-9]{0,2}\.[0-9]{3}", text):
        # "1.234" reads as one thousand two hundred and thirty-four on some packs: refused
        with pytest.raises(AmountError):
            parse_amount(text)
        return
    assert parse_amount(text) == amount
    assert amount_text(parse_amount(text)) == text
    assert "e" not in text.lower()


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("2", "2"),
        ("1.5", "1.5"),
        ("1,5", "1.5"),
        ("0,25", "0.25"),
        ("0.125", "0.125"),
        ("1.25", "1.25"),
        (" 500 ", "500"),
        ("1.50", "1.5"),
    ],
)
def test_amounts_as_people_write_them(text: str, value: str) -> None:
    assert amount_text(parse_amount(text)) == value


@pytest.mark.parametrize(
    "text",
    [
        "1,000",  # thousands separator or 1.000? (1000 mg mycophenolate): never guessed
        "50,000",
        "1.000",  # "20.000 I.E." on a German vitamin D pack
        "50.000",
        "1e3",
        "1_000",
        "+2",
        "-1",
        "0",
        "0.00001",
        "١٢",  # other scripts' digits
        "2 мг",
        "",
        "123456",
    ],
)
def test_ambiguous_or_inexact_amounts_are_refused(text: str) -> None:
    with pytest.raises(AmountError):
        parse_amount(text)


# --- schedule -----------------------------------------------------------------------------------


@given(st.lists(_times, min_size=1, max_size=12, unique=True), st.booleans())
def test_a_daily_schedule_is_canonical_and_stable(times: list[str], amounts: bool) -> None:
    raw = [{"at": t, "amount": "1,5"} if amounts else {"at": t} for t in reversed(times)]
    once = normalize_schedule({"type": "daily", "times": raw, "x": 1})
    expected = [{"at": t, "amount": "1.5"} if amounts else {"at": t} for t in sorted(times)]
    assert once == {"type": "daily", "times": expected}
    assert normalize_schedule(once) == once


def test_each_time_keeps_its_own_dose() -> None:
    """Tacrolimus 2 mg in the morning and 1.5 mg in the evening is one regimen."""
    schedule = normalize_schedule(
        {
            "type": "daily",
            "times": [{"at": "20:00", "amount": "1,5"}, {"at": "08:00", "amount": "2"}],
        }
    )
    assert schedule["times"] == [{"at": "08:00", "amount": "2"}, {"at": "20:00", "amount": "1.5"}]


@pytest.mark.parametrize(
    "bad",
    [
        None,
        {"type": "hourly", "times": [{"at": "08:00"}]},
        {"type": "daily"},
        {"type": "daily", "times": []},
        {"type": "daily", "times": ["08:00"]},  # plain strings: the old shape
        {"type": "daily", "times": [{"at": "8:00"}]},
        {"type": "daily", "times": [{"at": "24:00"}]},
        {"type": "daily", "times": [{"at": "08:60"}]},
        {"type": "daily", "times": [{"at": "08:00"}, {"at": "08:00"}]},
        {"type": "daily", "times": [{"at": f"{h:02d}:00"} for h in range(13)]},
        {"type": "daily", "times": [{"at": "08:00", "amount": "2"}, {"at": "20:00"}]},
        {"type": "daily", "times": [{"at": "08:00", "amount": 2}]},
        {"type": "daily", "times": [{"at": "08:00", "amount": "1,000"}]},
        {"type": "weekly", "times": [{"at": "09:00"}]},
        {"type": "weekly", "times": [{"at": "09:00"}], "days": []},
        {"type": "weekly", "times": [{"at": "09:00"}], "days": [0]},
        {"type": "weekly", "times": [{"at": "09:00"}], "days": [8]},
        {"type": "weekly", "times": [{"at": "09:00"}], "days": [1, 1]},
        {"type": "weekly", "times": [{"at": "09:00"}], "days": [True]},
        {"type": "weekly", "times": [{"at": "09:00"}], "days": ["1"]},
    ],
)
def test_schedules_a_reminder_cannot_follow_are_refused(bad: object) -> None:
    with pytest.raises(ScheduleError):
        normalize_schedule(bad)


def test_weekly_and_as_needed() -> None:
    assert normalize_schedule({"type": "weekly", "times": [{"at": "09:00"}], "days": [4, 1]}) == {
        "type": "weekly",
        "times": [{"at": "09:00"}],
        "days": [1, 4],
    }
    assert normalize_schedule({"type": "prn", "times": ["09:00"]}) == {"type": "prn"}


# --- dose history (H8) --------------------------------------------------------------------------

_rows = st.lists(
    st.builds(
        RegimenRow,
        st.dates(date(2015, 1, 1), date(2030, 1, 1)),
        st.integers(1, 10_000),
        st.one_of(st.none(), _moment),
    ),
    unique_by=lambda r: r.seq,
    max_size=20,
)


@given(_rows, st.dates(date(2015, 1, 1), date(2030, 1, 1)))
def test_the_dose_in_force_is_the_latest_started_and_never_a_voided_one(
    rows: list[RegimenRow], day: date
) -> None:
    found = regimen_on(rows, day)
    started = [r for r in rows if r.voided_at is None and r.effective_from <= day]
    if not started:
        assert found is None
        return
    assert found is not None
    assert found.voided_at is None
    assert found.effective_from <= day
    assert all((r.effective_from, r.seq) <= (found.effective_from, found.seq) for r in started)
    # a future change does not apply yet
    assert regimen_on([*rows, RegimenRow(day + timedelta(days=1), 99_999)], day) == found


@given(_rows, st.dates(date(2015, 1, 1), date(2030, 1, 1)))
def test_the_next_change_is_the_nearest_ahead(rows: list[RegimenRow], day: date) -> None:
    found = next_regimen(rows, day)
    ahead = [r for r in rows if r.voided_at is None and r.effective_from > day]
    if not ahead:
        assert found is None
        return
    assert found is not None
    assert found.effective_from == min(r.effective_from for r in ahead)
    # on its first day it is the dose in force
    assert regimen_on(rows, found.effective_from) == found


def test_a_voided_future_mistake_never_applies() -> None:
    now = datetime(2026, 11, 4, tzinfo=UTC)
    current = RegimenRow(date(2026, 1, 1), 1)
    mistake = RegimenRow(date(2027, 1, 1), 2, voided_at=now)
    assert regimen_on([current, mistake], date(2027, 6, 1)) == current
    assert next_regimen([current, mistake], date(2026, 11, 4)) is None


def test_a_same_day_correction_replaces_the_mistake() -> None:
    mistake, fix = RegimenRow(date(2026, 3, 1), 7), RegimenRow(date(2026, 3, 1), 8)
    assert regimen_on([fix, mistake], date(2026, 3, 1)) == fix


def test_stopped_and_finished_courses_are_not_current() -> None:
    today = date(2026, 11, 4)
    assert is_current(None, None, today)
    assert is_current(None, today, today)  # the course's last day
    assert not is_current(None, today - timedelta(days=1), today)
    assert not is_current(today, None, today)  # stopped today: the first day not taken (Q21)
    assert not is_current(today - timedelta(days=3), None, today)
    # a stop entered ahead: still taken today, as the reminders and the summary count it
    assert is_current(today + timedelta(days=1), None, today)


# --- intakes (H20) ------------------------------------------------------------------------------


@given(st.lists(_record, min_size=1, max_size=6))
def test_taken_always_wins_whatever_the_order(records: list[IntakeRecord]) -> None:
    results = {merged_all(list(p)) for p in permutations(records)}
    assert len(results) == 1  # the order the devices wrote in does not matter
    (result,) = results
    if any(is_taken(r) for r in records):
        assert is_taken(result)
        earliest = min(r.taken_at for r in records if r.taken_at is not None)
        assert result.taken_at == earliest
    else:
        assert result.status == "skipped"


def test_skipped_never_overwrites_taken() -> None:
    taken = IntakeRecord("taken", datetime(2026, 11, 4, 0, 5, tzinfo=UTC))
    assert merge_intake(taken, IntakeRecord("skipped", None)) == taken


# --- time since the transplant ------------------------------------------------------------------

_day = st.dates(date(1960, 1, 1), date(2030, 1, 1))


@given(_day, _day, st.sampled_from(["day", "month", "year"]))
def test_elapsed_never_overstates(start: date, today: date, precision: str) -> None:
    stored = (
        start.replace(day=1)
        if precision == "month"
        else start.replace(month=1, day=1)
        if precision == "year"
        else start
    )
    e = elapsed_since(stored, precision, today)  # type: ignore[arg-type]
    if stored > today:
        assert e is None
        return
    assert e is not None
    assert e.approximate == (precision != "day")
    assert e.years == e.months // 12
    # whatever the real day within the month/year, at least this much time has passed
    real_latest = latest_possible(stored, precision)  # type: ignore[arg-type]
    assert e.days <= max((today - real_latest).days, 0)
    assert e.days >= 0


@given(_day, _day)
def test_exact_dates_count_whole_months(start: date, today: date) -> None:
    e = elapsed_since(start, "day", today)
    if start > today:
        assert e is None
        return
    assert e is not None
    assert e.days == (today - start).days
    assert e.months * 28 <= e.days < (e.months + 1) * 31 + 1


def test_partial_dates_count_from_their_last_possible_day() -> None:
    today = date(2026, 11, 4)
    year = elapsed_since(date(2015, 1, 1), "year", today)
    month = elapsed_since(date(2025, 11, 1), "month", today)
    this_month = elapsed_since(date(2026, 11, 1), "month", today)
    assert year is not None
    assert month is not None
    assert this_month is not None
    assert (year.years, year.approximate) == (10, True)  # not 11: it may have been December
    assert (month.years, month.months) == (0, 11)  # not "1 year" before it can be true
    assert (this_month.days, this_month.months) == (0, 0)
    assert elapsed_since(date(2026, 11, 5), "day", today) is None
