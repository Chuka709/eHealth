"""core/slots.py: planned dose instants and the monthly summary (H7, Q22, Q23)."""

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given
from hypothesis import strategies as st

from labtrack.core.medications import IntakeRecord
from labtrack.core.slots import (
    MedicationPlan,
    RegimenPlan,
    Slot,
    ZoneSwitch,
    dose_slots,
    month_window,
    order_zones,
    place,
    summarize,
)

_CANDIDATES = (
    Path("/fixtures"),  # the test container (infra/docker-compose.yml)
    Path(__file__).resolve().parents[3] / "packages" / "shared" / "fixtures",
)


def _fixture(name: str) -> dict[str, Any]:
    for base in _CANDIDATES:
        path = base / name
        if path.is_file():
            data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            return data
    raise FileNotFoundError(name)


def _at(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _day(text: str | None) -> date | None:
    return date.fromisoformat(text) if text else None


def _plan(raw: dict[str, Any]) -> MedicationPlan:
    return MedicationPlan(
        mode=raw["mode"],
        started_on=_day(raw["started_on"]),
        stopped_on=_day(raw["stopped_on"]),
        planned_end_on=_day(raw["planned_end_on"]),
        regimens=[
            RegimenPlan(
                effective_from=date.fromisoformat(r["effective_from"]),
                seq=r["seq"],
                schedule=r["schedule"],
                voided_at=datetime(2026, 1, 1, tzinfo=UTC) if r["voided"] else None,
            )
            for r in raw["regimens"]
        ],
    )


def _zones(raw: list[dict[str, Any]]) -> list[ZoneSwitch]:
    return [ZoneSwitch(z["timezone"], _at(z["effective_at"]), z["seq"]) for z in raw]


_CASES = _fixture("dose-slots.json")["cases"]


@pytest.mark.parametrize("case", _CASES, ids=[c["name"] for c in _CASES])
def test_shared_fixtures(case: dict[str, Any]) -> None:
    """The app's reminder planner is checked against the same file (Jest)."""
    slots = dose_slots(
        _plan(case["plan"]), _zones(case["zones"]), _at(case["from"]), _at(case["to"])
    )
    got = [
        {"scheduled_at": s.scheduled_at, "amount": None if s.amount is None else str(s.amount)}
        for s in slots
    ]
    want = [
        {"scheduled_at": _at(e["scheduled_at"]), "amount": e["amount"]} for e in case["expected"]
    ]
    assert got == want


_ZONES = st.sampled_from(
    [
        "Asia/Ulaanbaatar",
        "Asia/Seoul",
        "Asia/Kolkata",
        "Europe/Istanbul",
        "America/New_York",
        "Asia/Kathmandu",
        "Pacific/Kiritimati",
        "Pacific/Pago_Pago",
        "Australia/Lord_Howe",
    ]
)
_TIMES = st.lists(
    st.tuples(st.integers(0, 23), st.integers(0, 59)).map(lambda t: f"{t[0]:02d}:{t[1]:02d}"),
    min_size=1,
    max_size=4,
    unique=True,
)


@st.composite
def _switches(draw: st.DrawFn) -> list[ZoneSwitch]:
    n = draw(st.integers(0, 4))
    base = datetime(2026, 10, 1, tzinfo=UTC)
    return [
        ZoneSwitch(draw(_ZONES), base + timedelta(minutes=draw(st.integers(0, 60 * 24 * 60))), i)
        for i in range(n)
    ]


def _daily(times: list[str]) -> MedicationPlan:
    schedule = {"type": "daily", "times": [{"at": t, "amount": "1"} for t in sorted(times)]}
    return MedicationPlan("local", None, None, None, [RegimenPlan(date(2026, 1, 1), 1, schedule)])


@given(times=_TIMES, zones=_switches())
def test_one_dose_per_day_and_time_never_two_never_none(
    times: list[str], zones: list[ZoneSwitch]
) -> None:
    """Across any zone switches, each (day, "HH:MM") is exactly one dose - a switch neither
    drops a dose nor repeats one (H7): every day and time in the middle of the window appears
    once. (Two times may land on one minute after a large eastward shift - Q26 - but stay two
    doses.)"""
    start = datetime(2026, 10, 1, tzinfo=UTC)
    end = start + timedelta(days=70)
    slots = dose_slots(_daily(times), zones, start, end)
    instants = [s.scheduled_at for s in slots]
    assert instants == sorted(instants)
    for s in slots:
        assert s.scheduled_at.second == 0
        assert s.scheduled_at.microsecond == 0
        assert start <= s.scheduled_at < end
    keys = [(s.local_day, s.at) for s in slots]
    assert len(set(keys)) == len(keys)
    for offset in range(3, 67):
        day = (start + timedelta(days=offset)).date()
        for t in times:
            assert (day, t) in keys, (day, t)


@given(times=_TIMES, zones=_switches(), extra=_ZONES, hours=st.integers(0, 24 * 80))
def test_a_switch_never_moves_a_dose_already_due(
    times: list[str], zones: list[ZoneSwitch], extra: str, hours: int
) -> None:
    """Medical review H1: a new switch at T (after all others) leaves every dose before T where
    it was - a dose already reminded is never reminded again after a flight west."""
    start = datetime(2026, 10, 1, tzinfo=UTC)
    end = start + timedelta(days=80)
    latest = max((z.effective_at for z in zones), default=start)
    at = max(latest, start + timedelta(hours=hours))
    switched = [*zones, ZoneSwitch(extra, at, len(zones))]
    before = [s for s in dose_slots(_daily(times), zones, start, end) if s.scheduled_at < at]
    after = [s for s in dose_slots(_daily(times), switched, start, end) if s.scheduled_at < at]
    assert before == after


@given(times=_TIMES, zones=_switches())
def test_only_nearby_switches_are_walked_with_the_same_result(
    times: list[str], zones: list[ZoneSwitch]
) -> None:
    """dose_slots walks only the switches near each day (security review M2); the result is
    what the full causal walk over every switch gives."""
    start = datetime(2026, 10, 1, tzinfo=UTC)
    every = order_zones(zones)
    for s in dose_slots(_daily(times), zones, start, start + timedelta(days=70)):
        assert place(s.local_day, s.at, "local", every) == s.scheduled_at


@given(times=_TIMES, zones=_switches())
def test_home_mode_ignores_the_profile_zone(times: list[str], zones: list[ZoneSwitch]) -> None:
    plan = _daily(times)
    home = MedicationPlan("home", None, None, None, plan.regimens)
    start = datetime(2026, 10, 1, tzinfo=UTC)
    end = start + timedelta(days=20)
    assert dose_slots(home, zones, start, end) == dose_slots(home, [], start, end)
    ub = ZoneInfo("Asia/Ulaanbaatar")
    for s in dose_slots(home, zones, start, end):
        assert s.scheduled_at.astimezone(ub).strftime("%H:%M") == s.at


@given(times=_TIMES, zone=_ZONES)
def test_a_settled_zone_puts_doses_on_its_wall_clock(times: list[str], zone: str) -> None:
    """Long after a switch, a "local" dose is at its written time on that zone's clock (DST
    gaps aside: a skipped wall time cannot be shown)."""
    switch = [ZoneSwitch(zone, datetime(2026, 1, 1, tzinfo=UTC))]
    start = datetime(2026, 5, 1, tzinfo=UTC)  # no DST change in May anywhere sampled
    slots = dose_slots(_daily(times), switch, start, start + timedelta(days=10))
    tz = ZoneInfo(zone)
    for s in slots:
        local = s.scheduled_at.astimezone(tz)
        assert local.strftime("%H:%M") == s.at
        assert local.date() == s.local_day


def test_windows_split_anywhere_give_the_same_doses() -> None:
    plan = _daily(["08:00", "20:00"])
    zones = [ZoneSwitch("Asia/Seoul", datetime(2026, 11, 2, 3, 17, tzinfo=UTC))]
    a, b, c = (datetime(2026, 11, d, h, tzinfo=UTC) for d, h in ((1, 0), (2, 7), (5, 0)))
    whole = dose_slots(plan, zones, a, c)
    assert whole == dose_slots(plan, zones, a, b) + dose_slots(plan, zones, b, c)


def test_month_window_is_the_ulaanbaatar_calendar() -> None:
    assert month_window(2026, 11) == (
        datetime(2026, 10, 31, 16, tzinfo=UTC),
        datetime(2026, 11, 30, 16, tzinfo=UTC),
    )
    assert month_window(2026, 12)[1] == datetime(2026, 12, 31, 16, tzinfo=UTC)


_LATER = datetime(2026, 11, 3, tzinfo=UTC)  # the recording window of 1 Nov has passed


def test_doses_within_the_recording_window_are_open_not_unrecorded() -> None:
    slots = [_slot(0), _slot(1)]
    now = slots[1].scheduled_at + timedelta(hours=23)  # slot 0: 23 h 1 min ago, slot 1: 23 h
    summary = summarize(slots, [], now)
    assert (summary.unrecorded, summary.open) == (0, 2)
    assert summary.percent_taken is None  # nothing closed yet
    later = summarize(slots, [(slots[0].scheduled_at, _rec("taken"))], now + timedelta(hours=2))
    assert (later.taken, later.unrecorded, later.open, later.percent_taken) == (
        1,
        1,
        0,
        Decimal(50),
    )


def _slot(minute: int) -> Slot:
    return Slot(datetime(2026, 11, 1, 0, minute, tzinfo=UTC), date(2026, 11, 1), "08:00", None)


def _rec(status: str, minute: int = 0) -> IntakeRecord:
    taken_at = None if status == "skipped" else datetime(2026, 11, 1, 0, minute, tzinfo=UTC)
    return IntakeRecord(status, taken_at)  # type: ignore[arg-type]


def test_summary_counts_planned_doses_only() -> None:
    slots = [_slot(0), _slot(1), _slot(2), _slot(3)]
    at = slots[0].scheduled_at
    records = [
        (at, _rec("skipped")),
        (at.replace(second=30), _rec("taken")),  # a second device: taken wins (H20)
        (slots[1].scheduled_at, _rec("late", 1)),  # the user's own word; counts as taken
        (slots[2].scheduled_at, _rec("skipped")),
        (datetime(2026, 11, 1, 5, tzinfo=UTC), _rec("taken")),  # not a planned dose
    ]
    summary = summarize(slots, records, _LATER)
    assert (summary.planned, summary.taken, summary.skipped, summary.unrecorded) == (4, 2, 1, 1)
    assert summary.open == 0
    assert summary.percent_taken == Decimal(50)


def test_summary_without_planned_doses_has_no_percent() -> None:
    assert summarize([], [], _LATER).percent_taken is None


@given(st.lists(st.sampled_from(["taken", "late", "skipped", None]), max_size=30))
def test_summary_parts_add_up(statuses: list[str | None]) -> None:
    slots = [_slot(i) for i in range(len(statuses))]
    records = [
        (s.scheduled_at, _rec(x, i))
        for i, (s, x) in enumerate(zip(slots, statuses, strict=True))
        if x
    ]
    summary = summarize(slots, records, _LATER)
    assert (
        summary.taken + summary.skipped + summary.unrecorded + summary.open
        == summary.planned
        == len(slots)
    )
    if summary.percent_taken is not None:
        assert Decimal(0) <= summary.percent_taken <= Decimal(100)
