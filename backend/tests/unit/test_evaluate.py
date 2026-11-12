"""The eval runner (Phase 4.6; docs/05 "Eval"): reading, scoring and the DoD check."""

import json
from pathlib import Path
from typing import Any

import pytest

from labtrack.core.lab_drafts import Catalog
from labtrack.extraction import evaluate
from labtrack.extraction.isolated import Reading
from labtrack.extraction.llm import AiAnswer, AiReadError
from labtrack.extraction.types import ReadDocument, ReadReport, ReadResult

SEED = Path(__file__).resolve().parents[3] / "seed" / "lab_tests.json"

_HEADER = [
    [40, "ШИНЖЛЭГДЭХҮҮН"],
    [220, "ХАРИУ"],
    [300, "ЛАВЛАХ"],
    [420, "ХЭМЖЭЭ"],
    [500, "АНХААРУУЛГА"],
]


def _central_lab_case(folder: Path, *, value: str = "88") -> Path:
    lines = [
        [40, [[40, "Улсын"], [80, "Нэгдүгээр"], [150, "Төв"], [180, "Эмнэлгийн"]]],
        [54, [[40, "ТӨРӨЛ:"], [90, "Биохими"], [300, "БАРКОД:"], [360, "1"]]],
        [68, [[40, "СОРЬЦ:"], [90, "Ийлдэс"], [300, "ТӨХӨӨРӨМЖ:"], [380, "A"]]],
        [82, _HEADER],
        [96, [[40, "Креатинин"], [220, value], [268, "62"], [290, "-"], [300, "115"],
              [420, "мкмоль/л"]]],
        [110, [[40, "Илгээсэн:"], [100, "Эмч"], [140, "2025-05-03"], [220, "00:00:00"]]],
    ]  # fmt: skip
    folder.mkdir(parents=True)
    (folder / "input.words.json").write_text(json.dumps({"pages": [lines]}), encoding="utf-8")
    expected = {
        "reports": [
            {
                "collected": "2025-05-03",
                "results": [
                    {"name": "Креатинин", "value": "88", "numeric": "88", "unit": "мкмоль/л",
                     "ref_low": "62", "ref_high": "115", "test_code": "CREA"},
                ],
            }
        ]
    }  # fmt: skip
    (folder / "expected.json").write_text(json.dumps(expected), encoding="utf-8")
    return folder


def _foreign_case(folder: Path) -> Path:
    lines = [
        [40, [[40, "Example"], [100, "Hospital"]]],
        [54, [[40, "Creatinine"], [220, "1.02"], [300, "mg/dL"], [380, "0.70"], [410, "-"],
              [420, "1.20"]]],
    ]  # fmt: skip
    folder.mkdir(parents=True)
    (folder / "input.words.json").write_text(json.dumps({"pages": [lines]}), encoding="utf-8")
    expected = {
        "profile_name": "Зохиомол Туршилт",
        "reports": [
            {
                "collected": None,
                "results": [
                    {"name": "Creatinine", "value": "1.02", "numeric": "1.02", "unit": "mg/dL",
                     "ref_low": "0.70", "ref_high": "1.20", "test_code": "CREA"},
                ],
            }
        ],
    }  # fmt: skip
    (folder / "expected.json").write_text(json.dumps(expected), encoding="utf-8")
    return folder


class _FakeAi:
    def __init__(self, rows: list[tuple[str, str]], error: str | None = None) -> None:
        self.rows, self.error = rows, error
        self.sent: list[str] = []

    def read(self, text: str) -> AiAnswer:
        self.sent.append(text)
        if self.error:
            raise AiReadError(self.error)
        results = tuple(
            ReadResult(raw_name=n, raw_value=v, raw_unit="mg/dL", ref_text="0.70 - 1.20",
                       lab_flag=None, page=1, snippet="")
            for n, v in self.rows
        )  # fmt: skip
        report = ReadReport(lab_name=None, panel_name=None, specimen=None, collected_raw=None,
                            reported_raw=None, results=results)  # fmt: skip
        return AiAnswer(ReadDocument(reader="ai:fake", reports=(report,)), "fake", 10, 10)


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    return evaluate.catalog_from_seed(SEED)


def test_a_local_reading_scores_every_measure(tmp_path: Path, catalog: Catalog) -> None:
    case = evaluate.load_case(_central_lab_case(tmp_path / "c1"))
    outcome = evaluate.read_case(case, catalog, None)
    assert outcome.method == "local"
    s = evaluate.score(outcome)
    assert (s.expected, s.found, s.extracted) == (1, 1, 1)
    assert all(s.rate(k) == 1.0 for k in evaluate.FIELDS if k != "critical"), s.wrong
    assert s.rate("critical") is None  # none printed: not measured, not 100%
    assert evaluate.failures([s], [outcome]) == []


def test_a_wrong_value_is_counted_and_fails_the_check(tmp_path: Path, catalog: Catalog) -> None:
    case = evaluate.load_case(_central_lab_case(tmp_path / "c1", value="8.8"))
    outcome = evaluate.read_case(case, catalog, None)
    s = evaluate.score(outcome)
    assert s.correct["value"] == 0
    assert s.correct["ref"] == 1  # the other measures still count
    assert [w[0] for w in s.wrong] == ["value"]
    assert evaluate.failures([s], [outcome]) == ["value 0.0% < 98.0%"]


def test_an_unknown_layout_is_missed_without_the_ai(tmp_path: Path, catalog: Catalog) -> None:
    case = evaluate.load_case(_foreign_case(tmp_path / "f"))
    outcome = evaluate.read_case(case, catalog, None)
    assert (outcome.method, outcome.drafts) == ("none", [])
    s = evaluate.score(outcome)
    assert (s.found, s.rate("value")) == (0, 0.0)


def test_the_ai_gets_the_de_identified_text_and_is_checked_against_it(
    tmp_path: Path, catalog: Catalog
) -> None:
    case = evaluate.load_case(_foreign_case(tmp_path / "f"))
    # a row that is not in the sent text is flagged, as on the AI worker
    ai = _FakeAi([("Creatinine", "1.02"), ("Glucose", "5.4")])
    outcome = evaluate.read_case(case, catalog, ai)
    assert outcome.method == "ai"
    [sent] = ai.sent
    assert "Creatinine 1.02" in sent
    rows = {x.raw_name: x for r in outcome.drafts for x in r.results}
    assert "not_in_source" in rows["Glucose"].issues
    s = evaluate.score(outcome)
    assert (s.found, s.extracted, s.correct["value"], s.correct["ref"]) == (1, 2, 1, 1)


def test_an_ai_failure_is_reported_by_code(tmp_path: Path, catalog: Catalog) -> None:
    case = evaluate.load_case(_foreign_case(tmp_path / "f"))
    outcome = evaluate.read_case(case, catalog, _FakeAi([], error="ai_refused"))
    assert (outcome.method, outcome.error) == ("none", "ai_refused")
    text = evaluate.report_markdown([outcome], [evaluate.score(outcome)], ai=True)
    assert "none (ai_refused)" in text
    assert "Creatinine" not in text  # the report keeps ids and counts only


def test_main_writes_the_report_and_checks_the_dod(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _central_lab_case(tmp_path / "cases" / "c1")
    report = tmp_path / "report.md"
    args = [str(tmp_path / "cases"), str(tmp_path / "missing"), "--seed", str(SEED)]
    assert evaluate.main([*args, "--report", str(report), "--check"]) == 0
    assert "| c1 |" in report.read_text(encoding="utf-8")
    _central_lab_case(tmp_path / "cases" / "c2", value="9")
    assert evaluate.main([*args, "--check", "--details"]) == 1
    out = capsys.readouterr().out
    assert "below DoD" in out
    assert "c2: value: expected Креатинин" in out
    assert evaluate.main([str(tmp_path / "missing"), "--seed", str(SEED)]) == 1


def test_a_real_document_without_the_profile_name_is_never_sent(
    tmp_path: Path, catalog: Catalog
) -> None:
    folder = _foreign_case(tmp_path / "f")
    (folder / "input.words.json").rename(folder / "unused.json")
    (folder / "input.pdf").write_bytes(b"%PDF-1.4 not really")
    data = json.loads((folder / "expected.json").read_text(encoding="utf-8"))
    del data["profile_name"]
    (folder / "expected.json").write_text(json.dumps(data), encoding="utf-8")
    case = evaluate.load_case(folder)
    ai = _FakeAi([("Creatinine", "1.02")])
    lines = Reading(None, ((1, "Creatinine 1.02 mg/dL 0.70 - 1.20"),))
    with pytest.MonkeyPatch.context() as m:
        m.setattr(evaluate, "_read_input", lambda _: (lines, 1))
        outcome = evaluate.read_case(case, catalog, ai)
    assert (outcome.method, outcome.error, ai.sent) == ("none", "no_profile_name", [])


def test_a_case_folder_must_not_carry_a_name(tmp_path: Path) -> None:
    _central_lab_case(tmp_path / "cases" / "Бат Болд")
    with pytest.raises(SystemExit):
        evaluate.find_cases([tmp_path / "cases"])


def _rewrite(folder: Path, change: object) -> None:
    data = json.loads((folder / "expected.json").read_text(encoding="utf-8"))
    change(data)  # type: ignore[operator]
    (folder / "expected.json").write_text(json.dumps(data), encoding="utf-8")


def test_a_range_read_where_none_is_printed_is_made_up(tmp_path: Path, catalog: Catalog) -> None:
    folder = _central_lab_case(tmp_path / "c1")

    def no_range(data: dict[str, Any]) -> None:
        row = data["reports"][0]["results"][0]
        del row["ref_low"], row["ref_high"]

    _rewrite(folder, no_range)
    outcome = evaluate.read_case(evaluate.load_case(folder), catalog, None)
    s = evaluate.score(outcome)
    assert (s.made_up["ref"], s.measured["ref"], s.rate("ref")) == (1, 0, None)
    assert evaluate.failures([s], [outcome]) == [
        "1 range/critical limit(s) made up where none is printed"
    ]


def test_bootstrapped_answers_never_count_for_the_dod(tmp_path: Path, catalog: Catalog) -> None:
    folder = _central_lab_case(tmp_path / "c1", value="9")
    _rewrite(folder, lambda d: d.update(source="reader_bootstrap"))
    case = evaluate.load_case(folder)
    assert case.bootstrap
    outcome = evaluate.read_case(case, catalog, None)
    s = evaluate.score(outcome)
    assert s.correct["value"] == 0
    assert evaluate.failures([s], [outcome]) == []  # a baseline only
    assert "Baseline" in evaluate.report_markdown([outcome], [s], ai=False)


def test_ai_cases_are_skipped_without_the_ai(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _central_lab_case(tmp_path / "cases" / "c1")
    folder = _foreign_case(tmp_path / "cases" / "f")
    _rewrite(folder, lambda d: d.update(tags=["ai"]))
    assert evaluate.main([str(tmp_path / "cases"), "--seed", str(SEED), "--check"]) == 0
    assert "| f | ai | - | skipped |" in capsys.readouterr().out


def test_p95() -> None:
    assert evaluate.p95([]) == 0.0
    assert evaluate.p95([float(i) for i in range(1, 21)]) == 20.0
    assert evaluate.p95([1.0, 2.0]) == 2.0
