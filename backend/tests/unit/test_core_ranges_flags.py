"""Printed ranges for this person and the flag from them (core/ranges.py, core/flags.py)."""

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from labtrack.core.flags import FlagResult, compute_flag, lab_mark, outside_target
from labtrack.core.lab_values import parse_value
from labtrack.core.ranges import Critical, Reference, critical_limits, reference_for

D = Decimal


# --- ranges -------------------------------------------------------------------------------


def test_single_printed_range_is_used_as_printed() -> None:
    assert reference_for("3.5 - 5.1", "unknown") == Reference(D("3.5"), D("5.1"), "printed")
    assert reference_for("< 5", "male") == Reference(None, D("5"), "printed")
    assert reference_for("> 60", "female") == Reference(D("60"), None, "printed")


@pytest.mark.parametrize(
    "text",
    ["Эр: 62-115 / Эм: 44-97", "Эрэгтэй 62-115; Эмэгтэй 44-97", "M 62-115 / F 44-97",
     "Муж: 62–115\nЖен: 44–97"],
)  # fmt: skip
def test_ranges_by_sex_pick_the_profiles(text: str) -> None:
    assert reference_for(text, "male") == Reference(D("62"), D("115"), "printed_for_sex")
    assert reference_for(text, "female") == Reference(D("44"), D("97"), "printed_for_sex")
    assert reference_for(text, "unknown") is None


@pytest.mark.parametrize(
    "text",
    [
        "Эр: 62-115",  # one sex only
        "Эр: 62-115 / Эр: 70-120",  # the same sex twice
        "Эр: 62-115 / Эм: 44-97 / Хүүхэд: 27-62",  # by age as well
        "1-5 нас: 27-62 / 6-18 нас: 44-97",  # by age
        "Эр: 115-62 / Эм: 44-97",  # low above high
        "Эр: хэвийн / Эм: 44-97",
        "normal",
        None,
    ],
)
def test_nothing_is_picked_when_unclear(text: str | None) -> None:
    assert reference_for(text, "male") is None


def test_critical_limits_read_the_other_way_round() -> None:
    assert critical_limits("< 2.5") == Critical(D("2.5"), None)  # critical below
    assert critical_limits("> 6.5") == Critical(None, D("6.5"))  # critical above
    assert critical_limits("≤ 2.5") == Critical(D("2.5"), None, low_inclusive=True)
    assert critical_limits("2.5 - 6.5") == Critical(D("2.5"), D("6.5"), ends_unclear=True)
    assert critical_limits(None) is None
    assert critical_limits(" - ") is None


@pytest.mark.parametrize("text", ["<2.5 / >6.5", "<2.5; >6.5", "< 2,5 или > 6,5", ">6.5 or <2.5",
                                  "<2.5, >6.5"])  # fmt: skip
def test_two_sided_critical_limits(text: str) -> None:
    assert critical_limits(text) == Critical(D("2.5"), D("6.5"))


@pytest.mark.parametrize("text", ["see note", "<2.5 / <3", ">6.5 / <7", "Эр: <2 / Эм: <3"])
def test_unreadable_critical_text_is_never_dropped(text: str) -> None:
    assert critical_limits(text) == Critical(None, None, unreadable=True)


# --- flags --------------------------------------------------------------------------------


def _flag(
    raw: str,
    ref: str | None = None,
    *,
    critical: str | None = None,
    mark: str | None = None,
    sex: str = "unknown",
) -> FlagResult:
    return compute_flag(
        parse_value(raw),
        reference=reference_for(ref, sex),  # type: ignore[arg-type]
        ref_text=ref,
        critical=critical_limits(critical),
        lab_flag=mark,
    )


@pytest.mark.parametrize(
    ("raw", "ref", "flag"),
    [
        ("4.2", "3.5-5.1", "normal"),
        ("3.5", "3.5-5.1", "normal"),  # at a limit: inside
        ("5.1", "3.5-5.1", "normal"),
        ("3.4", "3.5-5.1", "low"),
        ("5.2", "3.5-5.1", "high"),
        ("<0.5", "< 5", "normal"),
        (">1000", "< 200", "high"),
        ("<5", "2-10", "unknown"),  # may be below 2: not told
        ("<2", "2-10", "low"),  # every value below 2
        ("<=2", "2-10", "unknown"),  # 2 itself is normal
        (">=10", "2-10", "unknown"),
        (">10", "2-10", "high"),
        ("45", "> 60", "low"),
        ("STRAW", "3.5-5.1", "unknown"),
        ("4.2", None, "no_reference"),
        ("4.2", "хэвийн", "unknown"),  # printed but not usable: never "no reference"
    ],
)
def test_flag_against_the_printed_range(raw: str, ref: str | None, flag: str) -> None:
    result = _flag(raw, ref)
    assert result.flag == flag
    expected_source = (
        "none" if flag == "no_reference" or ref == "хэвийн" else "computed_document_range"
    )
    assert result.source == expected_source


def test_flag_by_sex() -> None:
    assert _flag("100", "Эр: 62-115 / Эм: 44-97", sex="female").flag == "high"
    assert _flag("100", "Эр: 62-115 / Эм: 44-97", sex="male").flag == "normal"
    assert _flag("100", "Эр: 62-115 / Эм: 44-97").flag == "unknown"  # sex not known


@pytest.mark.parametrize(
    ("raw", "ref", "flag"),
    [
        ("Сөрөг", "Сөрөг", "normal"),
        ("(-)", "Negative", "normal"),
        ("2+", "Сөрөг", "abnormal"),
        ("Эерэг", "Negative", "abnormal"),
        ("±", "Сөрөг", "unknown"),
        ("Эерэг", None, "no_reference"),  # never "positive = abnormal" from the catalog
    ],
)
def test_qualitative_against_a_printed_qualitative_reference(
    raw: str, ref: str | None, flag: str
) -> None:
    assert _flag(raw, ref).flag == flag


def test_critical_before_reference() -> None:
    assert _flag("2.1", "3.5-5.1", critical="< 2.5").flag == "critical_low"
    assert _flag("7.0", "3.5-5.1", critical="2.5 - 6.5").flag == "critical_high"
    assert _flag("6.5", "3.5-5.1", critical="> 6.5").flag == "high"  # at the limit: not
    assert _flag("2.1", None, critical="< 2.5").flag == "critical_low"  # with no reference


def test_possibly_critical_when_it_cannot_be_told() -> None:
    result = _flag(">500", "< 200", critical="> 1000")
    assert result.flag == "high"
    assert result.possibly_critical
    assert not _flag("300", "< 200", critical="> 1000").possibly_critical


def test_lab_mark_used_only_without_a_range() -> None:
    assert _flag("9.9", None, mark="H") == FlagResult("high", "lab_flag")
    assert _flag("9.9", None, mark="↓") == FlagResult("low", "lab_flag")
    assert _flag("9.9", None, mark="HH") == FlagResult("critical_high", "lab_flag")
    assert _flag("9.9", None, mark="*") == FlagResult("abnormal", "lab_flag")
    assert _flag("9.9", None, mark="-") == FlagResult("no_reference", "none")


def test_mismatch_when_the_mark_points_another_way() -> None:
    assert _flag("4.2", "3.5-5.1", mark="H").mismatch
    assert _flag("5.2", "3.5-5.1", mark="L").mismatch
    assert _flag("4.2", "3.5-5.1", mark="*").mismatch
    assert not _flag("5.2", "3.5-5.1", mark="H").mismatch
    assert not _flag("5.2", "3.5-5.1").mismatch  # many labs print no mark
    assert not _flag("<5", "2-10", mark="L").mismatch  # unknown: nothing to compare


def test_cyrillic_h_is_not_read_as_high() -> None:
    assert lab_mark("Н") == "unknown"  # may be "низкий" (low)
    assert _flag("9.9", None, mark="Н") == FlagResult("unknown", "lab_flag")
    assert lab_mark(" (H) ") == "high"
    assert lab_mark("") is None


def test_outside_target_is_a_label() -> None:
    assert outside_target(parse_value("12"), D("5"), D("10")) is True
    assert outside_target(parse_value("7"), D("5"), D("10")) is False
    assert outside_target(parse_value("<6"), D("5"), D("10")) is None
    assert outside_target(parse_value("7"), None, None) is None


numbers = st.decimals(min_value=0, max_value=10000, places=2)


@given(numbers, numbers, numbers)
def test_flag_matches_plain_comparison(value: Decimal, a: Decimal, b: Decimal) -> None:
    low, high = min(a, b), max(a, b)
    result = compute_flag(
        parse_value(str(value)),
        reference=Reference(low, high, "printed"),
        ref_text=None,
        critical=None,
        lab_flag=None,
    )
    expected = "low" if value < low else "high" if value > high else "normal"
    assert result.flag == expected


@given(numbers, numbers, numbers, st.sampled_from(["<", "<=", ">", ">="]))
def test_a_comparator_is_never_flagged_against_what_it_may_be(
    value: Decimal, a: Decimal, b: Decimal, cmp: str
) -> None:
    """Whatever flag is given must hold for every value the comparator allows."""
    low, high = min(a, b), max(a, b)
    result = compute_flag(
        parse_value(f"{cmp}{value}"),
        reference=Reference(low, high, "printed"),
        ref_text=None,
        critical=None,
        lab_flag=None,
    )
    step = D("0.001")
    edge = value if "=" in cmp else (value - step if "<" in cmp else value + step)
    far = D(-1) if "<" in cmp else D(100000)
    for candidate in (edge, far):
        plain = "low" if candidate < low else "high" if candidate > high else "normal"
        if result.flag != "unknown":
            assert result.flag == plain


def test_inclusive_and_unclear_critical_ends() -> None:
    assert _flag("2.5", "3.5-5.1", critical="≤ 2.5").flag == "critical_low"
    at_end = _flag("6.5", "3.5-5.1", critical="2.5 - 6.5")
    assert at_end.flag == "high"
    assert at_end.possibly_critical
    assert not _flag("6.4", "3.5-5.1", critical="2.5 - 6.5").possibly_critical
    assert _flag("2.0", "3.5-5.1", critical="<2.5 / >6.5").flag == "critical_low"


def test_unreadable_critical_text_is_possibly_critical() -> None:
    assert _flag("4.0", "3.5-5.1", critical="see note").possibly_critical


def test_lab_critical_mark_is_never_lost_to_a_range() -> None:
    result = _flag("5.8", "3.5-5.1", mark="HH")
    assert result.flag == "high"
    assert result.possibly_critical
    assert result.mismatch
    starred = _flag("9.9", None, mark="H*")
    assert starred == FlagResult("high", "lab_flag", possibly_critical=True)
    assert not _flag("9.9", None, mark="HH").possibly_critical  # the flag itself is critical


def test_mark_on_a_qualitative_result_is_no_mismatch() -> None:
    assert not _flag("2+", "Сөрөг", mark="H").mismatch


def test_critical_limits_inside_the_reference_are_pointed_out() -> None:
    assert _flag("4.0", "3.5-5.1", critical="3.5 - 5.1").critical_inside_reference is False
    assert _flag("4.0", "3.5-5.1", critical="< 4 / > 5").critical_inside_reference
    assert not _flag("4.0", "3.5-5.1", critical="< 2.5 / > 6.5").critical_inside_reference
