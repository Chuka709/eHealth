"""core/dashboard.py - cards, spark, change, attention (docs/06 §1)."""

import json
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import get_args

from hypothesis import given
from hypothesis import strategies as st

from labtrack.core.dashboard import (
    DEFAULT_CARDS,
    LEVEL,
    LEVEL_TESTS,
    Latest,
    Organ,
    Point,
    attention,
    card_codes,
    change,
    default_cards,
    spark,
)
from labtrack.core.flags import Flag

_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_SEED = Path(os.environ.get("SEED_DIR", Path(__file__).parents[3] / "seed"))


def _p(
    day: int,
    value: str | None = "1",
    *,
    flag: Flag = "normal",
    comparator: str | None = None,
    unit: str | None = "mg/dL",
    rid: str | None = None,
) -> Point:
    return Point(
        result_id=rid or f"r{day}",
        collected_at=_T0 + timedelta(days=day),
        value=None if value is None else Decimal(value),
        comparator=comparator,  # type: ignore[arg-type]
        unit=unit,
        flag=flag,
    )


def test_every_organ_has_defaults_from_the_catalog() -> None:
    codes = {t["code"] for t in json.loads((_SEED / "lab_tests.json").read_text("utf-8"))["tests"]}
    assert set(DEFAULT_CARDS) == set(get_args(Organ))
    for cards in DEFAULT_CARDS.values():
        assert {c for c in cards if c != LEVEL} <= codes
        assert len(cards) == len(set(cards))
    assert set(LEVEL_TESTS) <= codes


def test_kidney_defaults_with_the_drug_taken() -> None:
    assert default_cards(["kidney"], ["TAC"], []) == ["CREA", "TAC", "HGB", "K", "UPCR", "BKV_DNA"]
    assert default_cards(["kidney"], ["CSA"], ["TAC"]) == [
        "CREA",
        "CSA",
        "HGB",
        "K",
        "UPCR",
        "BKV_DNA",
    ]


def test_no_drug_recorded_shows_a_level_only_if_there_are_results() -> None:
    assert default_cards(["heart"], [], []) == ["CREA", "HGB", "CMV_DNA"]
    assert default_cards(["heart"], [], ["SIR"]) == ["SIR", "CREA", "HGB", "CMV_DNA"]


def test_mpa_is_not_a_default_level() -> None:
    assert "MPA" not in default_cards(["kidney"], ["MPA"], ["MPA"])


def test_two_transplants_merge_without_repeats_most_recent_first() -> None:
    cards = default_cards(["liver", "kidney"], ["TAC"], [])
    assert cards[:5] == ["ALT", "AST", "TBIL", "GGT", "INR"]
    assert len(cards) == len(set(cards))
    assert {"CREA", "BKV_DNA", "TAC"} <= set(cards)


def test_cornea_presumes_nothing() -> None:
    assert default_cards(["cornea"], [], ["TAC"]) == []


def test_own_list_wins_even_empty() -> None:
    assert card_codes(["K"], ["kidney"], ["TAC"], []) == ["K"]
    assert card_codes([], ["kidney"], ["TAC"], []) == []
    assert card_codes(None, ["kidney"], ["TAC"], [])[0] == "CREA"


def test_spark_is_the_last_numeric_points_oldest_first() -> None:
    history = [_p(d) for d in range(15)] + [_p(20, None)]
    out = spark(list(reversed(history)))
    assert [p.result_id for p in out] == [f"r{d}" for d in range(5, 15)]
    assert spark(history, 0) == []


def test_change_is_plain_percent_of_the_previous() -> None:
    history = [_p(0, "1.00"), _p(10, "1.20")]
    out = change(history[1], history)
    assert out is not None
    assert (out.previous.result_id, out.percent) == ("r0", Decimal(20))
    down = [_p(0, "4.0"), _p(1, "3.0")]
    assert change(down[1], down).percent == Decimal(-25)  # type: ignore[union-attr]


def test_change_rounds_half_up() -> None:
    history = [_p(0, "8"), _p(1, "9")]  # 12.5 %
    assert change(history[1], history).percent == Decimal(13)  # type: ignore[union-attr]


def test_no_change_without_two_exact_values_in_one_unit() -> None:
    assert change(_p(1, "2"), [_p(1, "2")]) is None  # nothing earlier
    assert change(_p(1, "2"), [_p(0, "0"), _p(1, "2")]) is None
    assert change(_p(1, "2"), [_p(0, "1", comparator="<"), _p(1, "2")]) is None
    assert change(_p(1, "2", comparator="<"), [_p(0, "1")]) is None
    assert change(_p(1, "2"), [_p(0, "1", unit="umol/L")]) is None
    assert change(_p(1, None), [_p(0, "1")]) is None
    assert change(_p(1, "2"), [_p(0, None)]) is None


def test_attention_is_flagged_values_critical_first_then_newest() -> None:
    latest = [
        Latest("K", _p(5, flag="high")),
        Latest("CREA", _p(1, flag="critical_high")),
        Latest("HGB", _p(9, flag="low")),
        Latest("ALT", _p(9, flag="normal")),
        Latest("X", _p(9, flag="no_reference")),
        Latest("Y", _p(9, flag="unknown")),
        Latest("Z", _p(3, flag="abnormal")),
    ]
    assert [x.test_code for x in attention(latest)] == ["CREA", "HGB", "K", "Z"]
    assert len(attention(latest, 2)) == 2


_values = st.decimals(min_value=Decimal("0.001"), max_value=Decimal(100000), places=3)


@given(_values, _values)
def test_change_sign_follows_the_values(a: Decimal, b: Decimal) -> None:
    history = [_p(0, str(a)), _p(1, str(b))]
    out = change(history[1], history)
    assert out is not None
    if b > a:
        assert out.percent >= 0
    elif b < a:
        assert out.percent <= 0
    else:
        assert out.percent == 0
    assert abs(out.percent - (b - a) / a * 100) <= Decimal("0.5")


@given(
    st.lists(st.sampled_from(get_args(Organ)), max_size=4),
    st.lists(st.sampled_from(("TAC", "CSA", "EVR", "SIR", "MPA"))),
)
def test_defaults_never_repeat_and_levels_only_from_the_known_four(
    organs: list[Organ], taken: list[str]
) -> None:
    cards = default_cards(organs, taken, [])
    assert len(cards) == len(set(cards))
    assert LEVEL not in cards
    assert {c for c in cards if c in {*LEVEL_TESTS, "MPA"}} <= set(taken) - {"MPA"}


def test_change_rounds_half_away_from_zero_downwards() -> None:
    history = [_p(0, "8"), _p(1, "7")]  # -12.5 %
    assert change(history[1], history).percent == Decimal(-13)  # type: ignore[union-attr]


def test_no_percent_for_viral_loads() -> None:
    history = [_p(0, "500"), _p(1, "5000")]
    assert change(history[1], history, "virology") is None
    assert change(history[1], history, "renal") is not None


def test_spark_keeps_only_the_newest_unit() -> None:
    history = [_p(0, "100", unit="umol/L"), _p(1, "1.1"), _p(2, "90", unit="umol/L"), _p(3, "1.2")]
    assert [p.result_id for p in spark(history)] == ["r1", "r3"]


def test_spark_ties_are_ordered_by_id() -> None:
    a, b = _p(1, "1", rid="a"), _p(1, "2", rid="b")
    assert spark([b, a]) == spark([a, b]) == [a, b]


def test_attention_leaves_out_values_older_than_the_window() -> None:
    latest = [
        Latest("K", _p(0, flag="critical_high")),
        Latest("HGB", _p(200, flag="low")),
        Latest("CREA", _p(150, flag="high")),
    ]
    assert [x.test_code for x in attention(latest)] == ["HGB", "CREA"]
    assert attention([]) == []


def test_a_lab_critical_mark_counts_as_critical_even_when_unknown() -> None:
    marked = Point("m", _T0, Decimal(7), None, "mmol/L", "unknown", possibly_critical=True)
    high = Latest("HGB", _p(1, flag="high"))
    assert [x.test_code for x in attention([high, Latest("K", marked)])] == ["K", "HGB"]
