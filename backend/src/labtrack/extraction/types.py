"""What a reader sees (words placed on pages) and what it returns (raw text per result row)."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Word:
    text: str
    x0: float
    x1: float
    top: float


@dataclass(frozen=True, slots=True)
class Line:
    """Words at one height, left to right."""

    words: tuple[Word, ...]

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def top(self) -> float:
        return self.words[0].top


@dataclass(frozen=True, slots=True)
class Page:
    number: int  # 1-based
    lines: tuple[Line, ...]


@dataclass(frozen=True, slots=True)
class PrintedIdentity:
    """The person's name as printed - only to check it is the profile's (name_match_score).

    Never stored, logged or sent anywhere (docs/03 lab_reports; CLAUDE.md rule 3): kept out of
    `repr` and out of `ReadDocument.to_raw_output`.
    """

    family_name: str | None = field(default=None, repr=False)
    given_name: str | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class ReadResult:
    raw_name: str
    raw_value: str
    raw_unit: str | None
    ref_text: str | None
    lab_flag: str | None
    page: int
    snippet: str  # the row as printed (no identity on a result row)


@dataclass(frozen=True, slots=True)
class ReadReport:
    lab_name: str | None
    panel_name: str | None
    specimen: str | None
    collected_raw: str | None  # when the sample was taken (or sent), as printed
    reported_raw: str | None  # when the lab signed the result
    results: tuple[ReadResult, ...]
    analysed_raw: str | None = None  # when the lab analysed it


@dataclass(frozen=True, slots=True)
class ReadDocument:
    reader: str  # e.g. "unte.v1" - extraction_runs.reader
    reports: tuple[ReadReport, ...]
    identity: PrintedIdentity = field(default_factory=PrintedIdentity, repr=False)

    def to_raw_output(self) -> dict[str, Any]:
        """extraction_runs.raw_output: everything read, without the printed identity."""
        return {
            "reader": self.reader,
            "reports": [
                {
                    "lab_name": r.lab_name,
                    "panel_name": r.panel_name,
                    "specimen": r.specimen,
                    "collected_raw": r.collected_raw,
                    "reported_raw": r.reported_raw,
                    "analysed_raw": r.analysed_raw,
                    "results": [
                        {
                            "raw_name": x.raw_name,
                            "raw_value": x.raw_value,
                            "raw_unit": x.raw_unit,
                            "ref_text": x.ref_text,
                            "lab_flag": x.lab_flag,
                            "page": x.page,
                        }
                        for x in r.results
                    ],
                }
                for r in self.reports
            ],
        }
