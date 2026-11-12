"""Draft reports from a reading (core/lab_drafts.py): checks point at, never correct."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from labtrack.core.lab_drafts import (
    Catalog,
    CatalogTest,
    Prior,
    Stamp,
    draft_report,
    name_match_score,
    parse_stamp,
    with_history,
)
from labtrack.core.text import normalize_name, normalize_unit
from labtrack.extraction.types import PrintedIdentity, ReadReport, ReadResult

CATALOG = Catalog(
    tests={
        "GLU": CatalogTest("GLU", "mmol/L", Decimal("0.5"), Decimal("60")),
        "CREA": CatalogTest("CREA", "µmol/L", Decimal("5"), Decimal("3000")),
    },
    synonyms={normalize_name("Глюкоз"): "GLU", normalize_name("Креатинин"): "CREA"},
    unit_aliases={normalize_unit("ммоль/л"): "mmol/L", normalize_unit("мг/дл"): "mg/dL"},
)
NOW = datetime(2026, 11, 12, tzinfo=UTC)
SURE = Decimal("1.00")


def _row(name: str, value: str, ref: str | None = None, unit: str | None = "ммоль/л") -> ReadResult:
    return ReadResult(name, value, unit, ref, None, 1, f"{name} {value}")


def _report(
    *rows: ReadResult,
    collected: str | None = "2025-08-18",
    analysed: str | None = "2025-08-18 10:15:21",
    reported: str | None = "2025-08-18 12:05:52",
) -> ReadReport:
    return ReadReport("Lab", "Биохими", "цус", collected, reported, rows, analysed)


def _draft(report: ReadReport, score: Decimal | None = SURE, mine: dict[str, str] | None = None):  # type: ignore[no-untyped-def]
    return draft_report(report, CATALOG, mine or {}, name_score=score, now=lambda: NOW)


def test_rows_become_drafts_with_numbers_ranges_and_tests() -> None:
    draft = _draft(
        _report(_row("Глюкоз", "5,37", "4.11 - 6.38"), _row("Альфа амилаза", "73.7", unit="нэгж/л"))
    )
    glucose, amylase = draft.results
    assert (glucose.position, glucose.test_code, glucose.value_numeric) == (
        0,
        "GLU",
        Decimal("5.37"),
    )
    assert (glucose.ref_low, glucose.ref_high, glucose.issues) == (
        Decimal("4.11"),
        Decimal("6.38"),
        (),
    )
    assert (amylase.test_code, amylase.issues) == (None, ("unknown_test",))


def test_a_printed_day_stays_a_day_and_the_times_are_kept_apart() -> None:
    """H30: no made-up midnight where only the day is printed."""
    draft = _draft(_report(_row("Глюкоз", "5")))
    assert (draft.collected_at, draft.collected_precision) == (
        datetime(2025, 8, 17, 16, tzinfo=UTC),  # the day's start in Ulaanbaatar
        "day",
    )
    assert draft.analysed_at == datetime(2025, 8, 18, 2, 15, 21, tzinfo=UTC)
    assert draft.reported_at == datetime(2025, 8, 18, 4, 5, 52, tzinfo=UTC)
    timed = _draft(_report(_row("Глюкоз", "5"), collected="2025-08-18 07:30"))
    assert timed.collected_precision == "minute"


def test_implausible_in_the_catalog_unit_only() -> None:
    draft = _draft(
        _report(
            _row("Глюкоз", "537"),  # a dropped decimal point
            _row("Креатинин", "0.70", "0.7 - 1.2", "мг/дл"),  # no factor listed: not converted
        )
    )
    assert draft.results[0].issues == ("implausible",)
    assert draft.results[1].issues == ("no_conversion",)  # said: off the trend, unchecked


@pytest.mark.parametrize(
    ("unit", "issue"), [(None, "unit_missing"), ("ммоль/литр", "unknown_unit")]
)
def test_a_known_test_without_a_usable_unit_says_so(unit: str | None, issue: str) -> None:
    draft = _draft(_report(_row("Глюкоз", "537", unit=unit)))
    assert draft.results[0].issues == (issue,)


def test_a_range_with_low_above_high_is_not_used() -> None:
    result = _draft(_report(_row("Глюкоз", "5", "9 - 3"))).results[0]
    assert (result.ref_low, result.ref_high, result.issues) == (None, None, ("ref_suspicious",))


@pytest.mark.parametrize(
    ("dates", "issue"),
    [
        ({"collected": "2027-01-01"}, "date_future"),
        ({"reported": "2027-01-01 10:00"}, "date_future"),
        ({"collected": "1985-03-02"}, "date_old"),
        ({"collected": "03.05.2025"}, "date_ambiguous"),
        ({"collected": None}, "date_missing"),
        ({"analysed": "2025-08-17 10:00"}, "date_inconsistent"),  # analysed before it was sent
        ({"reported": "2025-08-16 10:00"}, "date_inconsistent"),
    ],
)
def test_odd_dates_are_marked_on_every_row(dates: dict[str, str | None], issue: str) -> None:
    draft = _draft(_report(_row("Глюкоз", "5"), _row("Креатинин", "80", unit=None), **dates))
    assert all(issue in r.issues for r in draft.results)


@pytest.mark.parametrize(
    ("score", "issue"),
    [(Decimal("0.50"), "name_mismatch"), (None, "name_missing")],
)
def test_the_persons_name_issue_is_on_every_row(score: Decimal | None, issue: str) -> None:
    draft = _draft(_report(_row("Глюкоз", "5"), _row("Креатинин", "80", unit=None)), score)
    assert all(issue in r.issues for r in draft.results)


def test_ambiguous_dates_are_never_guessed() -> None:
    assert parse_stamp("03.05.2025") == Stamp(None, "day", ambiguous=True)
    assert parse_stamp("2025-02-30") == Stamp(None, "day", ambiguous=True)
    assert parse_stamp(None) == Stamp(None, "day")


def test_long_texts_are_cut_and_marked() -> None:
    result = _draft(_report(_row("Глюкоз " + "x" * 300, "5"))).results[0]
    assert len(result.raw_name) == 200
    assert "truncated" in result.issues


def test_the_persons_synonym_is_used() -> None:
    mine = {normalize_name("Альфа амилаза"): "GLU"}
    draft = _draft(_report(_row("Альфа амилаза", "5")), mine=mine)
    assert draft.results[0].test_code == "GLU"


@pytest.mark.parametrize(
    ("family", "given", "profile", "score"),
    [
        ("Дорж", "Батболд", "Дорж Батболд", "1.00"),
        ("Дорж", "Батболд", "Д.Батболд", "1.00"),  # the family initial
        ("Д", "Батболд", "Дорж Батболд", "1.00"),
        ("Дорж", "Батболд", "Батболд Дорж", "1.00"),  # given name written first
        (None, "Батболд", "Дорж Батболд", "0.90"),
        ("Дорж", "Батболд", "Батболд", "0.90"),  # no family name in the profile
        ("Сүх", "Батболд", "Дорж Батболд", "0.50"),  # same given name, another person
        ("Дулам", "Батболд", "Д.Батболд", "1.00"),  # an initial cannot tell them apart
        ("Дулам", "Батболд", "Дорж Батболд", "0.50"),  # a whole name can
        ("Дорж", "Батболд", "Батболд Тэмүүлэн", "0.50"),  # a father's report, his son's profile
        (None, "Батболд", "Батболд Тэмүүлэн", "0.80"),  # ...printing only his given name
        (None, "Тэмүүлэн", "Батболд Тэмүүлэн", "0.90"),  # the son's own, given name only
        ("Дорж", "Болд", "Дорж Батболд", "0.00"),
        ("Сүх", "Болд", "Дорж Батболд", "0.00"),
    ],
)
def test_the_printed_name_against_the_profile(
    family: str | None, given: str | None, profile: str, score: str
) -> None:
    assert name_match_score(PrintedIdentity(family, given), profile) == Decimal(score)


def test_no_printed_name_is_no_score() -> None:
    assert name_match_score(PrintedIdentity(), "Дорж Батболд") is None


CONVERTING = Catalog(
    tests={
        "CREA": CatalogTest(
            "CREA",
            "µmol/L",
            Decimal("5"),
            Decimal("3000"),
            factors={"mg/dL": Decimal("88.4")},
            delta_check_pct=Decimal("50"),
        ),
    },
    synonyms={normalize_name("Креатинин"): "CREA"},
    unit_aliases={normalize_unit("мг/дл"): "mg/dL", normalize_unit("мкмоль/л"): "µmol/L"},
)


def _converted(*rows: ReadResult, sex: str = "unknown"):  # type: ignore[no-untyped-def]
    return draft_report(
        _report(*rows), CONVERTING, {}, name_score=SURE, sex=sex,  # type: ignore[arg-type]
        now=lambda: NOW,
    )  # fmt: skip


def test_value_and_printed_limits_go_to_the_catalog_unit_by_one_factor() -> None:
    row = ReadResult("Креатинин", "1,2", "мг/дл", "0.7 - 1.3", None, 1, "x", critical_text="> 10")
    result = _converted(row).results[0]
    assert (result.unit_canonical, result.value_canonical) == ("µmol/L", Decimal("106.08"))
    assert (result.ref_low_canonical, result.ref_high_canonical) == (
        Decimal("61.88"),
        Decimal("114.92"),
    )
    assert (result.critical_low_canonical, result.critical_high_canonical) == (
        None,
        Decimal("884.0"),
    )
    assert (result.flag, result.flag_source) == ("normal", "computed_document_range")
    # printed numbers stay as printed
    assert (result.value_numeric, result.ref_low) == (Decimal("1.2"), Decimal("0.7"))


def test_implausible_after_conversion() -> None:
    result = _converted(_row("Креатинин", "120", unit="мг/дл")).results[0]  # µmol/L as mg/dL
    assert "implausible" in result.issues


def test_the_range_for_the_profiles_sex() -> None:
    row = _row("Креатинин", "100", "Эр: 62-115 / Эм: 44-97", "мкмоль/л")
    female = _converted(row, sex="female").results[0]
    assert (female.ref_low, female.ref_high, female.flag) == (Decimal("44"), Decimal("97"), "high")
    unknown = _converted(row).results[0]
    # printed, but none can be picked: unknown (never "no reference"), and said on the row
    assert (unknown.ref_low, unknown.flag) == (None, "unknown")
    assert "ref_not_used" in unknown.issues


def test_critical_rows_make_the_report_critical() -> None:
    critical = ReadResult(
        "Креатинин", "1200", "мкмоль/л", None, None, 1, "x", critical_text="> 1000"
    )
    possible = ReadResult("Креатинин", "90", "мкмоль/л", "62 - 115", "HH", 1, "x")
    plain = _row("Креатинин", "90", "62 - 115", "мкмоль/л")
    assert _converted(critical).has_unconfirmed_critical
    assert _converted(critical).results[0].flag == "critical_high"
    drafted = _converted(possible)
    assert drafted.has_unconfirmed_critical  # the lab's own HH (H5)
    assert {"possible_critical", "flag_mismatch"} <= set(drafted.results[0].issues)
    assert not _converted(plain).has_unconfirmed_critical
    unreadable = ReadResult("Креатинин", "90", "мкмоль/л", None, None, 1, "x", critical_text="?!")
    assert {"possible_critical", "critical_unreadable"} <= set(
        _converted(unreadable).results[0].issues
    )


def test_history_marks_duplicates_and_large_changes() -> None:
    draft = _converted(_row("Креатинин", "200", "62 - 115", "мкмоль/л"))  # 18 Aug (UB)
    prior = [
        Prior("CREA", datetime(2025, 8, 10, tzinfo=UTC), Decimal("100")),
        Prior("CREA", datetime(2025, 8, 18, 2, tzinfo=UTC), Decimal("200")),
        Prior("GLU", datetime(2025, 8, 18, 2, tzinfo=UTC), Decimal("200")),
    ]
    issues = with_history(draft, prior, CONVERTING).results[0].issues
    assert "possible_duplicate" in issues
    assert "large_delta" in issues  # 100 -> 200: +100 % over a 50 % check
    calm = with_history(draft, prior[:1], CONVERTING.__class__(
        tests={"CREA": CatalogTest("CREA", "µmol/L", None, None)},
        synonyms={}, unit_aliases={},
    ))  # fmt: skip
    assert calm.results[0].issues == draft.results[0].issues  # no delta check listed


def test_a_range_not_used_is_said_also_when_the_lab_mark_sets_the_flag() -> None:
    row = ReadResult("Креатинин", "100", "мкмоль/л", "Эр: 62-115 / Эм: 44-97", "H", 1, "x")
    result = _converted(row).results[0]
    assert (result.flag, result.flag_source) == ("high", "lab_flag")
    assert "ref_not_used" in result.issues
