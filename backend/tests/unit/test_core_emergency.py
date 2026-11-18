"""Emergency card ordering, blood type and dosed medicines (core/emergency.py; H17)."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise

from hypothesis import given
from hypothesis import strategies as st

from labtrack.core.emergency import (
    BLOOD_TYPES,
    BloodRecord,
    card_blood_type,
    dosed_category,
    order_allergies,
    order_dosed,
    order_transplants,
    recently_stopped,
)
from labtrack.core.medications import upcoming_regimens

_TYPE = st.one_of(st.none(), st.just("unknown"), st.sampled_from(sorted(BLOOD_TYPES)))
_SOLID = st.sampled_from(["kidney", "liver", "heart", "lung"])


@given(st.lists(st.tuples(_SOLID, _TYPE, _TYPE), max_size=6))
def test_a_blood_type_is_shown_only_when_every_record_agrees(
    rows: list[tuple[str, str | None, str | None]],
) -> None:
    known = {r for _, r, _ in rows if r in BLOOD_TYPES}
    shown = card_blood_type(BloodRecord(*r) for r in rows)
    if len(known) == 1:
        assert (shown.value, shown.withheld) == (known.pop(), None)
    else:
        assert shown.value is None  # never picks one of two disagreeing records
        assert shown.withheld == ("conflict" if known else None)


def test_unknown_and_missing_never_count_as_a_blood_type() -> None:
    assert card_blood_type([BloodRecord("kidney", "unknown", None)]).withheld is None
    agree = [BloodRecord("kidney", "A+", None), BloodRecord("liver", "A+", "O-")]
    assert card_blood_type(agree).value == "A+"  # a solid-organ donor's type changes nothing


@given(_TYPE, _TYPE)
def test_after_an_hsct_the_type_is_shown_only_if_the_donor_had_the_same(
    recipient: str | None, donor: str | None
) -> None:
    shown = card_blood_type([BloodRecord("hsct", recipient, donor)])
    if recipient not in BLOOD_TYPES:
        assert (shown.value, shown.withheld) == (None, None)
    elif donor == recipient:
        assert shown.value == recipient
    else:
        assert (shown.value, shown.withheld) == (None, "hsct")


@dataclass(frozen=True)
class _T:
    status: str
    on: date
    number: int = 1


def _ordered(rows: list[_T]) -> list[_T]:
    return order_transplants(rows, lambda r: r.status, lambda r: r.on, lambda r: r.number)


def test_working_grafts_come_first_then_newest() -> None:
    rows = [
        _T("failed", date(2024, 1, 1)),
        _T("functioning", date(2010, 1, 1)),
        _T("removed", date(2025, 1, 1)),
        _T("functioning", date(2020, 1, 1)),
        _T("unknown", date(2015, 1, 1)),
    ]
    assert [(r.status, r.on.year) for r in _ordered(rows)] == [
        ("functioning", 2020),
        ("functioning", 2010),
        ("unknown", 2015),
        ("failed", 2024),  # still in the body: before a removed graft (Q40)
        ("removed", 2025),
    ]


def test_a_year_only_date_tie_is_broken_by_the_transplant_number() -> None:
    rows = [_T("functioning", date(2020, 1, 1), 1), _T("functioning", date(2020, 1, 1), 2)]
    assert [r.number for r in _ordered(rows)] == [2, 1]


_STATUS = st.sampled_from(["functioning", "unknown", "failed", "removed", "something_new"])


@given(st.lists(st.builds(_T, _STATUS, st.dates(), st.integers(1, 5)), max_size=10))
def test_transplant_order_loses_nothing_and_groups_by_graft(rows: list[_T]) -> None:
    ordered = _ordered(rows)
    assert sorted(map(repr, ordered)) == sorted(map(repr, rows))
    rank = {"functioning": 0, "failed": 2, "removed": 3}  # anything else ranks as unknown
    keys = [(rank.get(r.status, 1), -r.on.toordinal(), -r.number) for r in ordered]
    assert keys == sorted(keys)


@given(st.lists(st.sampled_from(["severe", "moderate", "mild", "unknown", None]), max_size=12))
def test_the_most_severe_allergy_comes_first_and_none_is_lost(
    severities: list[str | None],
) -> None:
    rows = list(enumerate(severities))
    ordered = order_allergies(rows, lambda r: r[1])
    assert sorted(ordered, key=lambda r: r[0]) == rows
    rank = {"severe": 0, "moderate": 1, "mild": 2}
    keys = [rank.get(s or "", 3) for _, s in ordered]
    assert keys == sorted(keys)
    for a, b in pairwise(ordered):  # ties keep the recorded order
        if rank.get(a[1] or "", 3) == rank.get(b[1] or "", 3):
            assert a[0] < b[0]


def test_immunosuppressants_and_corticosteroids_carry_their_dose() -> None:
    assert dosed_category("immunosuppressant") == "immunosuppressant"
    assert dosed_category("corticosteroid") == "corticosteroid"
    for other in (None, "", "antiviral", "induction", "antihypertensive"):
        assert dosed_category(other) is None


def test_immunosuppressants_come_before_corticosteroids() -> None:
    rows = [("corticosteroid", "a"), ("immunosuppressant", "b"), ("immunosuppressant", "c")]
    ordered = order_dosed(rows, lambda r: r[0])  # type: ignore[arg-type,return-value]
    assert [n for _, n in ordered] == ["b", "c", "a"]


@dataclass(frozen=True)
class _R:
    effective_from: date
    seq: int
    voided_at: datetime | None = None


_TODAY = date(2026, 11, 5)
_R_STRATEGY = st.builds(
    _R,
    st.dates(_TODAY - timedelta(days=30), _TODAY + timedelta(days=60)),
    st.integers(1, 1000),
    st.one_of(st.none(), st.just(datetime(2026, 1, 1, tzinfo=UTC))),
)


@given(st.lists(_R_STRATEGY, max_size=12, unique_by=lambda r: r.seq))
def test_every_step_ahead_is_kept_one_per_day(rows: list[_R]) -> None:
    ahead = upcoming_regimens(rows, _TODAY)
    days = [r.effective_from for r in ahead]
    assert days == sorted(set(days))  # earliest first, one per starting day
    live = [r for r in rows if r.voided_at is None and r.effective_from > _TODAY]
    assert set(days) == {r.effective_from for r in live}  # no step lost (a taper)
    for r in ahead:  # the latest entered for its day, never a voided one
        assert r.voided_at is None
        assert r.seq == max(x.seq for x in live if x.effective_from == r.effective_from)


def test_recently_stopped_is_the_last_fourteen_days() -> None:
    """Q37 (physician 2026-11-18): an immunosuppressant stopped within 14 days stays listed."""
    today = date(2026, 11, 18)
    assert recently_stopped(date(2026, 11, 18), today)  # stopped today
    assert recently_stopped(date(2026, 11, 4), today)  # 14 days ago
    assert not recently_stopped(date(2026, 11, 3), today)
    assert not recently_stopped(date(2026, 11, 20), today)  # not yet
    assert not recently_stopped(None, today)
