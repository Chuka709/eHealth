"""Draft lab reports from what a reader read (docs/05 steps 6-7; rules 4-7; H2, H30).

Everything here is a draft for the person to check (rule 4): numbers and ranges as printed
(`core.lab_values`), the test by exact name (`core.matching`), and checks that point the
reviewer at what may be misread - never a correction. Each issue is put on every row it
concerns, so no row of a doubtful report looks sure:
- `unknown_test`: no catalog test for the printed name (the person picks one);
- `implausible`: a number outside the catalog's physiological bounds, in the catalog unit
  (`core.units`: the value and its printed limits by the test's own factor); `unit_missing` /
  `unknown_unit` when that check cannot be made for a known test (a known unit with no listed
  factor keeps its printed numbers and no catalog value - never on the trend);
- `ref_suspicious`: a printed range with low above high (not used);
- dates: `date_missing`, `date_ambiguous`, `date_future`, `date_old`, and `date_inconsistent`
  (analysed or signed before the sample's day);
- the person: `name_mismatch` (the printed name does not fit the profile) or `name_missing`;
- `truncated`: a printed text longer than kept;
- the flag from the printed range for the profile's sex (`core.flags`): `flag_mismatch` when
  the lab's mark points another way, `possible_critical` when a value may be critical but
  cannot be told (also the lab's own HH/LL on a value the printed limits do not call
  critical), `critical_unreadable`, `critical_inside_reference`;
- with earlier confirmed values (`with_history`): `possible_duplicate` (same test, day and
  value) and `large_delta` (beyond the catalog's delta check from the latest earlier value).
A report `has_unconfirmed_critical` when any row is critical or possibly critical (H5).
Dates printed without a zone are Ulaanbaatar time (the labs read so far are in Mongolia); a
date printed without a time is kept as that day (`precision` "day"), never as a made-up time.
"""

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Final, Literal
from zoneinfo import ZoneInfo

from labtrack.core.flags import compute_flag
from labtrack.core.lab_values import parse_range, parse_value
from labtrack.core.matching import match_test
from labtrack.core.ranges import Sex, critical_limits, reference_for
from labtrack.core.text import normalize_name
from labtrack.core.units import Limits, UnitSpec, convert, implausible
from labtrack.extraction.types import PrintedIdentity, ReadReport, ReadResult

LOCAL_ZONE: Final = ZoneInfo("Asia/Ulaanbaatar")
NAME_MATCH_THRESHOLD: Final = Decimal("0.85")
OLDEST: Final = datetime(1990, 1, 1, tzinfo=UTC)
MAX_RESULTS: Final = 500
_STAMP: Final = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?: (\d{2}):(\d{2})(?::(\d{2}))?)?$")
_LIMITS: Final = {
    "raw_name": 200,
    "raw_value": 200,
    "raw_unit": 50,
    "ref_text": 300,
    "lab_flag": 10,
}

Precision = Literal["day", "minute"]


@dataclass(frozen=True, slots=True)
class CatalogTest:
    code: str
    canonical_unit: str | None
    physio_min: Decimal | None
    physio_max: Decimal | None
    factors: Mapping[str, Decimal] = field(default_factory=dict)  # unit -> to canonical
    delta_check_pct: Decimal | None = None

    def units(self) -> UnitSpec:
        return UnitSpec(self.canonical_unit, self.factors, self.physio_min, self.physio_max)


@dataclass(frozen=True, slots=True)
class Catalog:
    tests: Mapping[str, CatalogTest]
    synonyms: Mapping[str, str]  # normalised name -> code (global)
    unit_aliases: Mapping[str, str]  # normalised alias -> unit


@dataclass(frozen=True, slots=True)
class Stamp:
    moment: datetime | None  # UTC; for a day, that day's start in Ulaanbaatar
    precision: Precision = "minute"
    ambiguous: bool = False

    def local_day(self) -> date | None:
        return self.moment.astimezone(LOCAL_ZONE).date() if self.moment else None


@dataclass(frozen=True, slots=True)
class DraftResult:
    position: int
    test_code: str | None
    raw_name: str
    raw_value: str
    raw_unit: str | None
    value_numeric: Decimal | None
    comparator: str | None
    value_text: str | None
    qualitative: str | None
    ref_text: str | None
    ref_low: Decimal | None
    ref_high: Decimal | None
    lab_flag: str | None
    issues: tuple[str, ...]
    source_page: int | None
    source_snippet: str
    critical_text: str | None = None
    critical_low: Decimal | None = None
    critical_high: Decimal | None = None
    unit_canonical: str | None = None
    value_canonical: Decimal | None = None
    ref_low_canonical: Decimal | None = None
    ref_high_canonical: Decimal | None = None
    critical_low_canonical: Decimal | None = None
    critical_high_canonical: Decimal | None = None
    flag: str = "unknown"
    flag_source: str | None = None
    flag_mismatch: bool = False

    @property
    def critical(self) -> bool:
        return self.flag in {"critical_low", "critical_high"} or "possible_critical" in self.issues


@dataclass(frozen=True, slots=True)
class DraftReport:
    lab_name: str | None
    panel_name: str | None
    specimen: str | None
    collected_at: datetime | None
    collected_precision: Precision
    analysed_at: datetime | None
    reported_at: datetime | None
    date_ambiguous: bool
    results: tuple[DraftResult, ...]

    @property
    def has_unconfirmed_critical(self) -> bool:
        return any(r.critical for r in self.results)


def parse_stamp(raw: str | None) -> Stamp:
    """'2025-08-18 12:05:52' (Ulaanbaatar) -> UTC minute; '2025-08-18' -> that day.

    Only ISO order is read; anything else is left for the person (None, ambiguous) - a day and
    month that could be swapped are never guessed.
    """
    if raw is None:
        return Stamp(None, "day")  # no time is known
    match = _STAMP.match(raw.strip())
    if match is None:
        return Stamp(None, "day", ambiguous=True)
    year, month, day = (int(match.group(i)) for i in (1, 2, 3))
    hour, minute, second = (int(match.group(i) or 0) for i in (4, 5, 6))
    try:
        local = datetime(year, month, day, hour, minute, second, tzinfo=LOCAL_ZONE)
    except ValueError:
        return Stamp(None, "day", ambiguous=True)
    return Stamp(local.astimezone(UTC), "minute" if match.group(4) else "day")


def _name_key(word: str) -> str:
    return normalize_name(word.strip().rstrip("."))


def _family_fits(printed: str, profile: str) -> bool:
    """Whole names agree, or one side is an initial ("Д." / "Д") of the other."""
    if len(printed) == 1 or len(profile) == 1:
        return printed[:1] == profile[:1]
    return printed == profile


def _readings(profile_name: str) -> list[tuple[str | None, str, bool]]:
    """(family, given, as written) ways to read the profile's name: "Дорж Батболд",
    "Д.Батболд", or - not as written - given name first ("Батболд Дорж")."""
    words = [w for w in re.split(r"[\s.]+", profile_name) if w]
    if not words:
        return []
    if len(words) == 1:
        return [(None, _name_key(words[0]), True)]
    first, last = _name_key(" ".join(words[:-1])), _name_key(words[-1])
    reversed_family, reversed_given = _name_key(" ".join(words[1:])), _name_key(words[0])
    return [(first, last, True), (reversed_family, reversed_given, False)]


def name_match_score(printed: PrintedIdentity, profile_name: str) -> Decimal | None:
    """How well the printed name fits the profile (H2); None when no name is printed.

    The given name must be the profile's given name - never its family name (a father's
    report in his son's profile: "Дорж Батболд" vs "Батболд Тэмүүлэн"). Then: the family name
    (or its initial) agrees 1.00; only one side has a family name 0.90; the family names
    differ 0.50 (same given name, another person - common in Mongolia); given name differs 0.
    Read the other way round ("Батболд Дорж"), the profile's first word may be a family name:
    there a printed family name must agree, or the score stays below the threshold (0.80) -
    a father's report printing only "Батболд" never passes in "Батболд Тэмүүлэн".
    """
    if printed.given_name is None and printed.family_name is None:
        return None
    given = _name_key(printed.given_name or "")
    family = _name_key(printed.family_name or "")
    best = Decimal("0.00")
    for profile_family, profile_given, as_written in _readings(profile_name):
        if not given or given != profile_given:
            continue
        if not as_written and not family:
            score = Decimal("0.80")
        elif not family or profile_family is None:
            score = Decimal("0.90")
        elif _family_fits(family, profile_family):
            score = Decimal("1.00")
        else:
            score = Decimal("0.50")
        best = max(best, score)
    return best


def _person_issues(score: Decimal | None) -> tuple[str, ...]:
    if score is None:
        return ("name_missing",)
    return ("name_mismatch",) if score < NAME_MATCH_THRESHOLD else ()


def _date_issues(
    collected: Stamp, analysed: Stamp, reported: Stamp, now: datetime
) -> tuple[str, ...]:
    issues: list[str] = []
    if collected.ambiguous:
        issues.append("date_ambiguous")
    elif collected.moment is None:
        issues.append("date_missing")
    moments = [s.moment for s in (collected, analysed, reported) if s.moment is not None]
    if any(m > now + timedelta(days=1) for m in moments):
        issues.append("date_future")
    if collected.moment is not None and collected.moment < OLDEST:
        issues.append("date_old")
    day = collected.local_day()
    later = [s.local_day() for s in (analysed, reported)]
    if day is not None and any(d is not None and d < day for d in later):
        issues.append("date_inconsistent")
    return tuple(issues)


@dataclass(frozen=True, slots=True)
class _Units:
    issues: tuple[str, ...] = ()
    unit: str | None = None
    value: Decimal | None = None
    reference: Limits = field(default_factory=Limits)
    critical: Limits = field(default_factory=Limits)


def _units(
    value: Decimal | None,
    unit: str | None,
    test: CatalogTest | None,
    catalog: Catalog,
    *,
    reference: Limits,
    critical: Limits,
) -> _Units:
    if value is None or test is None or test.canonical_unit is None:
        return _Units()
    out = convert(
        unit, test.units(), catalog.unit_aliases, value=value, reference=reference,
        critical=critical,
    )  # fmt: skip
    if out == "no_conversion":
        # a known unit with no listed factor (urea mg/dL - Q52): printed numbers only, off the
        # trend and without the plausibility check - said on the row
        return _Units(issues=("no_conversion",))
    if isinstance(out, str):
        return _Units(issues=(out,))
    issues = ("implausible",) if implausible(out.value, test.units()) else ()
    return _Units(issues, out.unit, out.value, out.reference, out.critical)


def _trim(row: ReadResult) -> tuple[dict[str, str | None], bool]:
    texts: dict[str, str | None] = {
        "raw_name": row.raw_name,
        "raw_value": row.raw_value,
        "raw_unit": row.raw_unit,
        "ref_text": row.ref_text,
        "lab_flag": row.lab_flag,
    }
    cut = any(t is not None and len(t) > _LIMITS[k] for k, t in texts.items())
    return {k: (t[: _LIMITS[k]] if t else None) for k, t in texts.items()}, cut


def _result(
    position: int,
    row: ReadResult,
    *,
    specimen: str | None,
    catalog: Catalog,
    user_synonyms: Mapping[str, str],
    report_issues: tuple[str, ...],
    sex: Sex,
) -> DraftResult:
    texts, cut = _trim(row)
    value = parse_value(row.raw_value)
    printed = parse_range(row.ref_text)
    reference = reference_for(row.ref_text, sex)
    critical = critical_limits(row.critical_text)
    flag = compute_flag(
        value, reference=reference, ref_text=row.ref_text, critical=critical,
        lab_flag=row.lab_flag,
    )  # fmt: skip
    code = match_test(row.raw_name, specimen, catalog.synonyms, user_synonyms)
    test = catalog.tests.get(code) if code else None
    limits = Limits(reference.low, reference.high) if reference else Limits()
    critical_at = Limits(critical.low, critical.high) if critical else Limits()
    units = _units(
        value.numeric, row.raw_unit, test, catalog, reference=limits, critical=critical_at
    )
    issues = [*report_issues, *row.issues]
    if code is None:
        issues.append("unknown_test")
    issues.extend(units.issues)
    if printed.kind == "suspicious":
        issues.append("ref_suspicious")
    if flag.mismatch:
        issues.append("flag_mismatch")
    if flag.possibly_critical:
        issues.append("possible_critical")
    if critical is not None and critical.unreadable:
        issues.append("critical_unreadable")
    if flag.critical_inside_reference:
        issues.append("critical_inside_reference")
    # a range printed but none used for this person (also when the lab's mark set the flag)
    if (
        reference is None
        and printed.kind not in {"none", "suspicious"}
        and flag.source != "computed_document_range"
    ):
        issues.append("ref_not_used")  # printed, but none could be picked for this person
    if cut or len(row.snippet) > 500:  # noqa: PLR2004 - lab_results.source_snippet
        issues.append("truncated")
    return DraftResult(
        position=position,
        test_code=code,
        raw_name=texts["raw_name"] or "",
        raw_value=texts["raw_value"] or "",
        raw_unit=texts["raw_unit"],
        value_numeric=value.numeric,
        comparator=value.comparator,
        value_text=value.text[:200] if value.text else None,
        qualitative=value.qualitative,
        ref_text=texts["ref_text"],
        # the printed range for this person (by sex when printed so), never the catalog's
        ref_low=limits.low,
        ref_high=limits.high,
        lab_flag=texts["lab_flag"],
        issues=tuple(dict.fromkeys(issues)),
        source_page=row.page,
        source_snippet=row.snippet[:500],
        critical_text=row.critical_text[:300] if row.critical_text else None,
        # "< 2.5" printed as a critical limit means critical below 2.5 (core.ranges)
        critical_low=critical_at.low,
        critical_high=critical_at.high,
        unit_canonical=units.unit,
        value_canonical=units.value,
        ref_low_canonical=units.reference.low,
        ref_high_canonical=units.reference.high,
        critical_low_canonical=units.critical.low,
        critical_high_canonical=units.critical.high,
        flag=flag.flag,
        flag_source=flag.source,
        flag_mismatch=flag.mismatch,
    )


def draft_report(
    report: ReadReport,
    catalog: Catalog,
    user_synonyms: Mapping[str, str],
    *,
    name_score: Decimal | None,
    sex: Sex = "unknown",
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> DraftReport:
    """`name_score`: `name_match_score` of the document's printed name (one per document)."""
    collected = parse_stamp(report.collected_raw)
    analysed = parse_stamp(report.analysed_raw)
    reported = parse_stamp(report.reported_raw)
    report_issues = (
        *_date_issues(collected, analysed, reported, now()),
        *_person_issues(name_score),
    )
    return DraftReport(
        lab_name=report.lab_name,
        panel_name=report.panel_name,
        specimen=report.specimen,
        collected_at=collected.moment,
        collected_precision=collected.precision,
        analysed_at=analysed.moment,
        reported_at=reported.moment,
        date_ambiguous=collected.ambiguous,
        results=tuple(
            _result(
                i,
                row,
                specimen=report.specimen,
                catalog=catalog,
                user_synonyms=user_synonyms,
                report_issues=report_issues,
                sex=sex,
            )
            for i, row in enumerate(report.results[:MAX_RESULTS])
        ),
    )


@dataclass(frozen=True, slots=True)
class Prior:
    """An earlier confirmed value of the profile, in the catalog unit."""

    test_code: str
    collected_at: datetime
    value_canonical: Decimal
    confirmed: bool = True  # False: another draft still waiting for review


def _changed_by(new: Decimal, old: Decimal) -> Decimal:
    """How far apart, in % of the smaller: the same for a rise and a fall (45 -> 4.5 and
    4.5 -> 45 both 900 %), so a misread comma that lowers a value is caught as well."""
    return (max(new / old, old / new) - 1) * 100


def _history_issues(
    row: DraftResult, day: date | None, at: datetime | None, prior: Sequence[Prior],
    catalog: Catalog, *, by_day: bool,
) -> tuple[str, ...]:  # fmt: skip
    # a value with a comparator ("<0.5") is not one number: never compared
    if row.test_code is None or row.value_canonical is None or row.comparator is not None:
        return ()
    mine = [p for p in prior if p.test_code == row.test_code]
    issues: list[str] = []
    if day is not None and any(
        p.collected_at.astimezone(LOCAL_ZONE).date() == day
        and p.value_canonical == row.value_canonical
        for p in mine
    ):
        issues.append("possible_duplicate")
    test = catalog.tests.get(row.test_code)
    # a report with only its day: earlier means an earlier day (the hour is not known)
    earlier = [
        p
        for p in mine
        if p.confirmed
        and (
            (by_day and day is not None and p.collected_at.astimezone(LOCAL_ZONE).date() < day)
            or (not by_day and at is not None and p.collected_at < at)
        )
    ]
    if test is not None and test.delta_check_pct is not None and earlier:
        last = max(earlier, key=lambda p: p.collected_at).value_canonical
        new = row.value_canonical
        if last > 0 and new > 0 and _changed_by(new, last) > test.delta_check_pct:
            issues.append("large_delta")
    return tuple(issues)


def with_history(report: DraftReport, prior: Sequence[Prior], catalog: Catalog) -> DraftReport:
    """`possible_duplicate` (against confirmed values and other drafts) / `large_delta`
    (against the latest earlier confirmed value) - `prior` holds no comparator values."""
    day = report.collected_at.astimezone(LOCAL_ZONE).date() if report.collected_at else None
    rows = tuple(
        replace(r, issues=tuple(dict.fromkeys((*r.issues, *extra))))
        if (
            extra := _history_issues(
                r,
                day,
                report.collected_at,
                prior,
                catalog,
                by_day=report.collected_precision == "day",
            )
        )
        else r
        for r in report.results
    )
    return replace(report, results=rows)
