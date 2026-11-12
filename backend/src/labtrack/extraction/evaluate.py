"""`just eval`: how well documents are read, against hand-checked answers (docs/05 "Eval").

A case is a folder with its answers and one input. The answers are `expected.json`, or
`answers.csv` written by hand from the paper result (eval/answers_template.csv; Excel's
"CSV UTF-8" with "," or ";"), plus an optional `case.json` ({"profile_name", "tags"}):
- `input.pdf` - a real document, read the way the worker reads it (child process, then the
  local readers); real cases live in `eval/local/` and are never committed (PHI).
- `input.words.json` - a made-up printout as words placed on pages (synthetic cases in
  `eval/cases/`, built by `eval/make_synthetic.py`); it skips only the PDF text layer.
A document no local reader knows is read by the AI only with `--ai` (Q50): the text is
de-identified and checked against what was sent, as on the AI worker, and each call costs
money - the key and model come from ANTHROPIC_API_KEY / EXTRACTION_MODEL (rule 11).

Every expected row is scored (a row not found counts as wrong): value (and qualitative
reading), unit, test and its report's date over all rows; range and critical limit over the
rows that print one, and separately how often one was made up where none is printed (rule 5).
Rows read that were not expected are counted too. Cases whose answers were bootstrapped from
the reader's own output (`"source": "reader_bootstrap"`) are a regression baseline only: shown
apart, never counted for the DoD. Cases tagged "ai" are skipped without `--ai`. `--check`
fails below the Phase 4 DoD (value >= 98%, range >= 95%, test >= 95%), on any made-up range or
extra row, or p95 > 30 s per page of a real PDF. The report keeps only case ids and counts;
`--details` prints each wrong row on screen (never into the report, nor a CI log).
"""

import argparse
import csv
import io
import json
import os
import re
import sys
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Final
from zoneinfo import ZoneInfo

from labtrack.core.lab_drafts import Catalog, CatalogTest, DraftReport, DraftResult, draft_report
from labtrack.core.text import normalize_name, normalize_unit
from labtrack.extraction.deidentify import deidentify
from labtrack.extraction.isolated import Reading, read_isolated
from labtrack.extraction.llm import AiReader, AiReadError
from labtrack.extraction.readers import read_locally
from labtrack.extraction.types import Line, Page, ReadDocument, Word
from labtrack.extraction.verify import check_against_source

LOCAL: Final = ZoneInfo("Asia/Ulaanbaatar")
FIELDS: Final = ("value", "unit", "ref", "critical", "test", "date")
DOD: Final = {"value": 0.98, "ref": 0.95, "test": 0.95}
DOD_P95_PAGE_S: Final = 30.0
READ_TIMEOUT_S: Final = 60.0
# a case's id is its folder's name and goes into the report: never a person's name
CASE_ID: Final = re.compile(r"[a-z0-9-]{1,40}")


# --- cases --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExpectedRow:
    name: str
    value: str
    numeric: Decimal | None = None
    comparator: str | None = None
    unit: str | None = None
    ref_low: Decimal | None = None
    ref_high: Decimal | None = None
    ref_text: str | None = None  # a text range ("(-) Clear"): compared as printed
    critical_low: Decimal | None = None
    critical_high: Decimal | None = None
    qualitative: str | None = None  # positive | negative | equivocal, when it reads as one
    test_code: str | None = None  # None: not in the catalog - must stay unknown
    collected: str | None = None  # the report's date, YYYY-MM-DD in Ulaanbaatar

    @property
    def has_ref(self) -> bool:
        return self.ref_low is not None or self.ref_high is not None or self.ref_text is not None

    @property
    def has_critical(self) -> bool:
        return self.critical_low is not None or self.critical_high is not None


@dataclass(frozen=True, slots=True)
class Case:
    id: str
    path: Path
    rows: tuple[ExpectedRow, ...]
    profile_name: str = ""
    tags: tuple[str, ...] = ()
    bootstrap: bool = False  # answers taken from the reader's own output: a baseline only


def _exact(value: object) -> Decimal | None:
    return None if value is None else Decimal(str(value))


# answers.csv columns (eval/answers_template.csv); only date, name and value are required
CSV_COLUMNS: Final = (
    "date", "name", "value", "unit", "ref_low", "ref_high", "ref_text", "critical_low",
    "critical_high", "qualitative", "test_code",
)  # fmt: skip
_QUALITATIVE: Final = {
    "эерэг": "positive", "positive": "positive", "+": "positive",
    "сөрөг": "negative", "negative": "negative", "-": "negative",
    "эргэлзээтэй": "equivocal", "equivocal": "equivocal",
}  # fmt: skip
_PRINTED_NUMBER: Final = re.compile(r"(<=|>=|<|>)?\s*([0-9]+(?:[.,][0-9]+)?(?:[eE][+-]?[0-9]+)?)")


def _cell(row: dict[str, str], key: str) -> str | None:
    value = (row.get(key) or "").strip()
    return value or None


def _number(text: str | None) -> str | None:
    return None if text is None else text.replace(",", ".")


def answers_from_csv(text: str) -> list[dict[str, object]]:
    """The `reports` of expected.json from a hand-written answers.csv: one report per date.

    A value is a number when it reads as one as written ("12,4", "<500", "1.2E+06"); the
    numbers are taken from the person's own writing, never from the reader (no circularity).
    """
    dialect = csv.Sniffer().sniff(text.splitlines()[0], delimiters=",;")
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    missing = {"date", "name", "value"} - set(reader.fieldnames or ())
    if missing:
        raise SystemExit(f"answers.csv: missing column(s) {sorted(missing)}")
    by_date: dict[str | None, list[dict[str, object]]] = {}
    for number, row in enumerate(reader, start=2):
        name, value = _cell(row, "name"), _cell(row, "value")
        if name is None and value is None:
            continue  # an empty line
        if name is None or value is None:
            raise SystemExit(f"answers.csv line {number}: name and value are both needed")
        answer: dict[str, object] = {"name": name, "value": value, "unit": _cell(row, "unit")}
        if match := _PRINTED_NUMBER.fullmatch(value.replace(" ", "")):
            answer["numeric"] = _number(match.group(2))
            if match.group(1):
                answer["comparator"] = match.group(1)
        for key in ("ref_low", "ref_high", "critical_low", "critical_high"):
            if (cell := _cell(row, key)) is not None:
                answer[key] = _number(cell)
        if (ref_text := _cell(row, "ref_text")) is not None:
            answer["ref_text"] = ref_text
        if (word := _cell(row, "qualitative")) is not None:
            if word.casefold() not in _QUALITATIVE:
                raise SystemExit(f"answers.csv line {number}: qualitative is Эерэг/Сөрөг/...")
            answer["qualitative"] = _QUALITATIVE[word.casefold()]
        answer["test_code"] = _cell(row, "test_code")
        by_date.setdefault(_cell(row, "date"), []).append(answer)
    return [{"collected": day, "results": rows} for day, rows in by_date.items()]


def _case_data(path: Path) -> dict[str, object]:
    if (path / "expected.json").exists():
        data: dict[str, object] = json.loads((path / "expected.json").read_text(encoding="utf-8"))
        return data
    meta = path / "case.json"
    data = json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else {}
    data["reports"] = answers_from_csv((path / "answers.csv").read_text(encoding="utf-8-sig"))
    return data


def load_case(path: Path) -> Case:
    data: dict[str, Any] = _case_data(path)
    rows: list[ExpectedRow] = []
    for report in data["reports"]:
        for r in report["results"]:
            rows.append(
                ExpectedRow(
                    name=r["name"],
                    value=r["value"],
                    numeric=_exact(r.get("numeric")),
                    comparator=r.get("comparator"),
                    unit=r.get("unit"),
                    ref_low=_exact(r.get("ref_low")),
                    ref_high=_exact(r.get("ref_high")),
                    ref_text=r.get("ref_text"),
                    critical_low=_exact(r.get("critical_low")),
                    critical_high=_exact(r.get("critical_high")),
                    qualitative=r.get("qualitative"),
                    test_code=r.get("test_code"),
                    collected=report.get("collected"),
                )
            )
    return Case(
        id=path.name,
        path=path,
        rows=tuple(rows),
        profile_name=data.get("profile_name", ""),
        tags=tuple(data.get("tags", ())),
        bootstrap=data.get("source") == "reader_bootstrap",
    )


def find_cases(roots: Iterable[Path]) -> list[Case]:
    paths = sorted(
        {
            p.parent
            for root in roots
            if root.is_dir()
            for name in ("expected.json", "answers.csv")
            for p in root.glob(f"*/{name}")
        }
    )
    if bad := [p for p in paths if not CASE_ID.fullmatch(p.name)]:
        raise SystemExit(f"{len(bad)} case folder(s) not named like 'local-1' (a-z, 0-9, -)")
    return [load_case(p) for p in paths]


def catalog_from_seed(path: Path) -> Catalog:
    """The catalog as `just seed` loads it (seed.py), without a database."""
    lab = json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)
    tests: dict[str, CatalogTest] = {}
    synonyms: dict[str, str] = {}
    clashes: list[str] = []
    for t in lab["tests"]:
        tests[t["code"]] = CatalogTest(
            t["code"], t.get("canonical_unit"), _exact(t.get("physio_min")),
            _exact(t.get("physio_max")),
        )  # fmt: skip
        names = [t["code"], t["name_mn"], t["name_en"], t.get("name_ru"), *t.get("synonyms", [])]
        for name in filter(None, names):
            key = normalize_name(name)
            if key and synonyms.setdefault(key, t["code"]) != t["code"]:
                clashes.append(name)
    if clashes:  # as seed.py refuses it: one name, two tests
        raise SystemExit(f"ambiguous synonyms in the seed: {len(clashes)}")
    units = {normalize_unit(a): u for a, u in lab.get("unit_aliases", {}).items()}
    return Catalog(tests=tests, synonyms=synonyms, unit_aliases=units)


# --- reading ------------------------------------------------------------------------------------


def _pages_from_words(path: Path) -> tuple[Page, ...]:
    data = json.loads(path.read_text(encoding="utf-8"))
    pages: list[Page] = []
    for number, page in enumerate(data["pages"], start=1):
        lines: list[Line] = []
        for top, words in page:
            placed = [Word(text=t, x0=x, x1=x + 5.5 * len(t), top=top) for x, t in words]
            lines.append(Line(tuple(sorted(placed, key=lambda w: w.x0))))
        pages.append(Page(number, tuple(lines)))
    return tuple(pages)


def _read_input(case: Case) -> tuple[Reading, int]:
    """The local reading (or the text lines for the AI) and the page count."""
    pdf = case.path / "input.pdf"
    if pdf.exists():
        reading = read_isolated(pdf.read_bytes(), timeout=READ_TIMEOUT_S)
        pages = {page for page, _ in reading.lines} or {
            r.page for rep in (reading.document.reports if reading.document else ()) for r in
            rep.results if r.page
        }  # fmt: skip
        return reading, max(len(pages), 1)
    pages_read = _pages_from_words(case.path / "input.words.json")
    document = read_locally(pages_read)
    lines = (
        ()
        if document is not None
        else tuple((p.number, line.text) for p in pages_read for line in p.lines)
    )
    return Reading(document, lines), max(len(pages_read), 1)


@dataclass(slots=True)
class Outcome:
    case: Case
    method: str  # local | ai | none
    drafts: list[DraftReport]
    seconds: float
    pages: int
    error: str | None = None


def read_case(case: Case, catalog: Catalog, ai: AiReader | None) -> Outcome:
    started = time.monotonic()
    try:
        reading, pages = _read_input(case)
    except Exception as exc:
        return Outcome(case, "none", [], time.monotonic() - started, 1, type(exc).__name__)
    document: ReadDocument | None = reading.document
    method = "local" if document is not None else "none"
    error = None
    real = (case.path / "input.pdf").exists()
    if document is None and ai is not None and reading.lines and real and not case.profile_name:
        # without the profile's name its masks are not applied: a real name could go out
        # (security review 4.6) - expected.json must say whose document it is
        error = "no_profile_name"
    elif document is None and ai is not None and reading.lines:
        clean = deidentify(reading.lines, case.profile_name)
        try:
            answer = ai.read(clean.text)
            document = check_against_source(answer.document, clean.text)
            method = "ai"
        except AiReadError as exc:
            error = exc.code
    drafts = (
        [draft_report(r, catalog, {}, name_score=None) for r in document.reports]
        if document is not None
        else []
    )
    return Outcome(case, method, drafts, time.monotonic() - started, pages, error)


# --- scoring ------------------------------------------------------------------------------------


def _same_text(a: str | None, b: str | None) -> bool:
    def norm(s: str | None) -> str:
        return " ".join((s or "").replace(",", ".").casefold().split())

    return norm(a) == norm(b)


def _value_ok(row: ExpectedRow, got: DraftResult) -> bool:
    if row.numeric is not None:
        return got.value_numeric == row.numeric and got.comparator == row.comparator
    return (
        got.value_numeric is None
        and _same_text(got.raw_value, row.value)
        and got.qualitative == row.qualitative
    )


def _ref_ok(row: ExpectedRow, got: DraftResult) -> bool:
    if row.ref_text is not None and row.ref_low is None and row.ref_high is None:
        return _same_text(got.ref_text, row.ref_text) and got.ref_low is got.ref_high is None
    return (got.ref_low, got.ref_high) == (row.ref_low, row.ref_high)


def _unit_ok(row: ExpectedRow, got: DraftResult) -> bool:
    return normalize_unit(got.raw_unit or "") == normalize_unit(row.unit or "")


def _day(report: DraftReport) -> str | None:
    return report.collected_at.astimezone(LOCAL).date().isoformat() if report.collected_at else None


_CHECKS: Final[dict[str, Callable[[ExpectedRow, DraftResult, DraftReport], bool]]] = {
    "value": lambda e, g, _: _value_ok(e, g),
    "unit": lambda e, g, _: _unit_ok(e, g),
    "ref": lambda e, g, _: _ref_ok(e, g),
    "critical": lambda e, g, _: (
        (g.critical_low, g.critical_high) == (e.critical_low, e.critical_high)
    ),
    "test": lambda e, g, _: g.test_code == e.test_code,
    "date": lambda e, _, r: _day(r) == e.collected,
}
# measured only over the rows that print one; elsewhere one read is "made up" (rule 5)
_PRINTED: Final[dict[str, Callable[[ExpectedRow], bool]]] = {
    "ref": lambda e: e.has_ref,
    "critical": lambda e: e.has_critical,
}
_READ: Final[dict[str, Callable[[DraftResult], bool]]] = {
    "ref": lambda g: g.ref_low is not None or g.ref_high is not None,
    "critical": lambda g: g.critical_low is not None or g.critical_high is not None,
}


@dataclass(slots=True)
class Score:
    expected: int = 0
    found: int = 0
    extracted: int = 0
    correct: dict[str, int] = field(default_factory=lambda: dict.fromkeys(FIELDS, 0))
    measured: dict[str, int] = field(default_factory=lambda: dict.fromkeys(FIELDS, 0))
    made_up: dict[str, int] = field(default_factory=lambda: dict.fromkeys(_PRINTED, 0))
    wrong: list[tuple[str, str, str]] = field(default_factory=list)  # (field, expected, got)

    def add(self, other: "Score") -> None:
        self.expected += other.expected
        self.found += other.found
        self.extracted += other.extracted
        for k in FIELDS:
            self.correct[k] += other.correct[k]
            self.measured[k] += other.measured[k]
        for k in _PRINTED:
            self.made_up[k] += other.made_up[k]

    def rate(self, name: str) -> float | None:
        """Correct over the rows it applies to; None when no row has it (not measured)."""
        return self.correct[name] / self.measured[name] if self.measured[name] else None

    @property
    def extra(self) -> int:
        return self.extracted - self.found

    @property
    def recall(self) -> float:
        return self.found / self.expected if self.expected else 1.0


def _describe(row: ExpectedRow, got: DraftResult | None) -> tuple[str, str]:
    want = f"{row.name} = {row.value} {row.unit or ''} [{row.ref_low}-{row.ref_high}]"
    if got is None:
        return want, "-"
    have = f"{got.raw_name} = {got.raw_value} {got.raw_unit or ''} [{got.ref_low}-{got.ref_high}]"
    return want, f"{have} test={got.test_code}"


def _match(
    row: ExpectedRow, pool: list[tuple[DraftResult, DraftReport]], used: set[int]
) -> int | None:
    """The row read under the same name, preferring one in a report of the same day (a test
    printed twice, as serum and urine creatinine on two reports, pairs with its own)."""
    key = normalize_name(row.name)
    named = [
        i for i, (x, _) in enumerate(pool) if i not in used and normalize_name(x.raw_name) == key
    ]
    same_day = [i for i in named if _day(pool[i][1]) == row.collected]
    best = same_day or named
    return best[0] if best else None


def score(outcome: Outcome) -> Score:
    s = Score(expected=len(outcome.case.rows))
    pool = [(x, rep) for rep in outcome.drafts for x in rep.results]
    s.extracted = len(pool)
    used: set[int] = set()
    for row in outcome.case.rows:
        applies = {k: _PRINTED[k](row) if k in _PRINTED else True for k in FIELDS}
        for k in FIELDS:
            s.measured[k] += applies[k]
        hit = _match(row, pool, used)
        if hit is None:
            s.wrong.append(("missing", *_describe(row, None)))
            continue
        used.add(hit)
        s.found += 1
        got, report = pool[hit]
        for name, check in _CHECKS.items():
            if not applies[name]:
                if _READ[name](got):
                    s.made_up[name] += 1
                    s.wrong.append((f"{name} made up", *_describe(row, got)))
            elif check(row, got, report):
                s.correct[name] += 1
            else:
                s.wrong.append((name, *_describe(row, got)))
    return s


def p95(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))]


def _real_page_times(outcomes: Sequence[Outcome]) -> list[float]:
    """Seconds per page of real PDFs only: a made-up printout skips the parse."""
    return [o.seconds / o.pages for o in outcomes if (o.case.path / "input.pdf").exists()]


# --- report -------------------------------------------------------------------------------------


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def _total(scores: Iterable[Score]) -> Score:
    total = Score()
    for s in scores:
        total.add(s)
    return total


def _summary(title: str, total: Score) -> list[str]:
    return [
        f"## {title}",
        "",
        f"- Expected rows: {total.expected}; found {_pct(total.recall)}; rows read that were"
        f" not expected: {total.extra}",
        f"- Made up where none is printed: range {total.made_up['ref']},"
        f" critical {total.made_up['critical']}",
        "",
        "| Measure | Score | Rows measured | DoD |",
        "|---|---|---|---|",
        *(
            f"| {k} | {_pct(total.rate(k))} | {total.measured[k]} |"
            f" {_pct(DOD[k]) if k in DOD else '-'} |"
            for k in FIELDS
        ),
        "",
    ]


def report_markdown(
    outcomes: Sequence[Outcome],
    scores: Sequence[Score],
    *,
    ai: bool,
    skipped: Sequence[Case] = (),
) -> str:
    pairs = list(zip(outcomes, scores, strict=True))
    times = _real_page_times(outcomes)
    lines = [
        "# Eval",
        "",
        f"- {datetime.now(LOCAL):%Y-%m-%d %H:%M} (Asia/Ulaanbaatar); AI: {'on' if ai else 'off'}",
        f"- Cases: {len(outcomes)}; skipped without --ai: {len(skipped)}",
        f"- Time per page of a real PDF: p95 {p95(times):.2f} s" if times else
        "- Time per page: n/a (no real PDF)",
        "",
        *_summary(
            "Checked answers (counted for the DoD)",
            _total(s for o, s in pairs if not o.case.bootstrap),
        ),
        *_summary(
            "Baseline: answers from the reader's own output (regression only)",
            _total(s for o, s in pairs if o.case.bootstrap),
        ),
        "| Case | Tags | Answers | Read by | Rows | Found | Value | Unit | Range | Test | Date"
        " | s |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]  # fmt: skip
    for o, s in pairs:
        lines.append(
            f"| {o.case.id} | {' '.join(o.case.tags)} |"
            f" {'baseline' if o.case.bootstrap else 'checked'} | {o.method}"
            f"{' (' + o.error + ')' if o.error else ''} | {s.expected} | {s.found} | "
            f"{s.correct['value']} | {s.correct['unit']} |"
            f" {s.correct['ref']}/{s.measured['ref']} | "
            f"{s.correct['test']} | {s.correct['date']} | {o.seconds:.2f} |"
        )
    lines += [
        f"| {c.id} | {' '.join(c.tags)} | - | skipped | - | - | - | - | - | - | - | - |"
        for c in skipped
    ]
    return "\n".join(lines) + "\n"


def failures(scores: Sequence[Score], outcomes: Sequence[Outcome]) -> list[str]:
    total = _total(s for o, s in zip(outcomes, scores, strict=True) if not o.case.bootstrap)
    out = [
        f"{k} {_pct(rate)} < {_pct(v)}"
        for k, v in DOD.items()
        if (rate := total.rate(k)) is not None and rate < v
    ]
    if made_up := sum(total.made_up.values()):
        out.append(f"{made_up} range/critical limit(s) made up where none is printed")
    if total.extra:
        out.append(f"{total.extra} row(s) read that were not expected")
    worst = p95(_real_page_times(outcomes))
    if worst > DOD_P95_PAGE_S:
        out.append(f"p95 {worst:.1f} s per page > {DOD_P95_PAGE_S:.0f} s")
    return out


# --- command ------------------------------------------------------------------------------------


def _ai_reader() -> AiReader:
    from labtrack.extraction.llm import AnthropicReader  # noqa: PLC0415 - only with --ai

    key, model = os.environ.get("ANTHROPIC_API_KEY"), os.environ.get("EXTRACTION_MODEL")
    if not key or not model:
        raise SystemExit("--ai needs ANTHROPIC_API_KEY and EXTRACTION_MODEL in the environment")
    return AnthropicReader(key, model)


def _say(text: str) -> None:
    sys.stdout.write(f"{text}\n")  # a command's output (the screen), not a log


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="just eval", description="How well documents are read.")
    parser.add_argument("roots", nargs="+", type=Path, help="folders of cases")
    parser.add_argument("--seed", type=Path, required=True, help="seed/lab_tests.json")
    parser.add_argument("--report", type=Path, help="write the markdown report here")
    parser.add_argument("--ai", action="store_true", help="read unknown layouts with the AI")
    parser.add_argument("--check", action="store_true", help="fail below the Phase 4 DoD")
    parser.add_argument("--details", action="store_true", help="print each wrong row")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    cases = find_cases(args.roots)
    if not cases:
        _say("no cases found")
        return 1
    catalog = catalog_from_seed(args.seed)
    ai = _ai_reader() if args.ai else None
    skipped = [c for c in cases if ai is None and "ai" in c.tags]
    outcomes = [read_case(c, catalog, ai) for c in cases if c not in skipped]
    scores = [score(o) for o in outcomes]
    text = report_markdown(outcomes, scores, ai=ai is not None, skipped=skipped)
    _say(text)
    if args.details:
        for o, s in zip(outcomes, scores, strict=True):
            if os.environ.get("CI") and (o.case.path / "input.pdf").exists():
                continue  # a real document's values never go into a build log
            for what, want, got in s.wrong:
                _say(f"{o.case.id}: {what}: expected {want} | got {got}")
    if args.report:
        args.report.write_text(text, encoding="utf-8", newline="\n")
    if args.check and (missed := failures(scores, outcomes)):
        _say("below DoD: " + "; ".join(missed))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
