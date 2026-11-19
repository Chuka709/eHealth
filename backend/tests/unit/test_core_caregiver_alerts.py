"""Which doses a caregiver hears about (core/caregiver_alerts.py; H16)."""

from datetime import UTC, date, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from labtrack.core.caregiver_alerts import ALERT_WINDOW, alert_range, overdue_slots
from labtrack.core.slots import Slot

NOW = datetime(2026, 11, 11, 4, 0, tzinfo=UTC)  # 12:00 in Ulaanbaatar


def _slot(at: datetime) -> Slot:
    return Slot(at, date(2026, 11, 11), at.strftime("%H:%M"), None)


def _ago(minutes: int) -> datetime:
    return NOW - timedelta(minutes=minutes)


def test_a_dose_is_announced_once_its_delay_has_passed() -> None:
    delay = timedelta(minutes=30)
    due_now, not_yet, long_ago = _slot(_ago(30)), _slot(_ago(29)), _slot(_ago(90))
    window_edge = _slot(_ago(89))
    assert overdue_slots([not_yet, due_now, long_ago, window_edge], [], NOW, delay) == [
        window_edge,
        due_now,
    ]


def test_a_recorded_dose_is_never_announced_taken_or_skipped() -> None:
    dose = _slot(_ago(45))
    # a record carries the planned minute; seconds and zones do not matter
    recorded = [(dose.scheduled_at + timedelta(seconds=40)).astimezone(UTC)]
    assert overdue_slots([dose], recorded, NOW, timedelta(minutes=30)) == []


def test_two_times_on_one_minute_give_one_alert() -> None:
    at = _ago(40)
    first = Slot(at, date(2026, 11, 11), "11:20", None)
    second = Slot(at, date(2026, 11, 11), "12:20", None)  # Q26: kept on home time
    assert overdue_slots([first, second], [], NOW, timedelta(minutes=30)) == [first]


def test_only_the_caregivers_own_range_of_delays() -> None:
    for minutes in (14, 241, 0):
        with pytest.raises(ValueError, match="delay"):
            alert_range(NOW, timedelta(minutes=minutes))


@given(
    delay=st.integers(min_value=15, max_value=240),
    offsets=st.lists(st.integers(min_value=-600, max_value=600), max_size=30),
    recorded=st.sets(st.integers(min_value=-600, max_value=600), max_size=10),
)
def test_announced_doses_are_exactly_the_due_unrecorded_recent_ones(
    delay: int, offsets: list[int], recorded: set[int]
) -> None:
    slots = [_slot(NOW + timedelta(minutes=m)) for m in offsets]
    out = overdue_slots(
        slots, [NOW + timedelta(minutes=m) for m in recorded], NOW, timedelta(minutes=delay)
    )
    expected = sorted({m for m in offsets if -delay - 60 < m <= -delay and m not in recorded})
    assert [s.scheduled_at for s in out] == [NOW + timedelta(minutes=m) for m in expected]
    for slot in out:  # never one that is not yet due, never one older than the window
        due = slot.scheduled_at + timedelta(minutes=delay)
        assert NOW - ALERT_WINDOW < due <= NOW


@given(delay=st.integers(min_value=15, max_value=240))
def test_the_range_matches_what_is_announced(delay: int) -> None:
    start, end = alert_range(NOW, timedelta(minutes=delay))
    inside = [_slot(at) for at in (start, end - timedelta(microseconds=1))]
    outside = [_slot(at) for at in (start - timedelta(microseconds=1), end)]
    out = overdue_slots(inside + outside, [], NOW, timedelta(minutes=delay))
    assert out == inside
