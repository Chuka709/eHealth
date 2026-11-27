"""Results from the First Central Hospital of Mongolia (УНТЭ) central laboratory, text PDF.

The layout (seen on real reports, kept only locally - test samples are git-ignored):
- Each page starts with the person's identity in labelled cells (ОВОГ:, НЭР:, РЕГИСТР:,
  ТӨРСӨН:, НАС:, ХҮЙС:) - read only for the name check, nothing else is kept.
- A panel: "ТӨРӨЛ: <panel> БАРКОД: <n>", "СОРЬЦ: <specimen> ТӨХӨӨРӨМЖ: <analyser>", a column
  header "ШИНЖЛЭГДЭХҮҮН ХАРИУ ЛАВЛАХ ХЭМЖЭЭ АНХААРУУЛГА", then one row per test
  ("<name> <value> <low> - <high> <unit> [H|L|LL]"), a legend line "H - лавлах ...", and
  three signatures with dates (Илгээсэн - sent, date only; Шинжилсэн; Баталгаажуулсан).
- A panel may run over a page break: its last rows come on the next page, after the identity
  block and before any new panel header.
- Columns are found from the header's word positions, so a row's value, range, unit and flag
  are told apart by where they are printed, not by guessing from the text (qualitative values
  such as "normal", "(-)", "STRAW 02" and text ranges such as "(-) Clear" stay as printed).
- The lab's own H/L flags are kept as printed in `lab_flag`; they are not trusted (seen wrong
  on real reports) - flags are computed from the range in `core` (rule 5).
"""

import re
from dataclasses import dataclass, field
from typing import Final

from labtrack.extraction.types import Line, Page, PrintedIdentity, ReadDocument, ReadReport
from labtrack.extraction.types import ReadResult as Row

NAME: Final = "unte.v1"
LAB_NAME: Final = "Улсын Нэгдүгээр Төв Эмнэлэг"
_HEADER: Final = ("ШИНЖЛЭГДЭХҮҮН", "ХАРИУ", "ЛАВЛАХ", "ХЭМЖЭЭ", "АНХААРУУЛГА")
_IDENTITY_LABELS: Final = frozenset({"ОВОГ:", "НЭР:", "РЕГИСТР:", "ТӨРСӨН:", "НАС:", "ХҮЙС:"})
_MARK: Final = re.compile(r"Улсын\s+Нэгдүгээр\s+Төв\s+Эмнэлг")
_DATE: Final = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME: Final = re.compile(r"^\d{2}:\d{2}:\d{2}$")
_SLACK: Final = 3.0  # points a word may start left of its column
# a panel's signatures: which date each gives, and whether only its day is printed (sent)
_SIGNED: Final = {
    "Илгээсэн:": ("collected_raw", True),
    "Шинжилсэн:": ("analysed_raw", False),
    "Баталгаажуулсан:": ("reported_raw", False),
}


@dataclass(frozen=True, slots=True)
class _Columns:
    value: float
    ref: float
    unit: float
    flag: float

    @classmethod
    def from_header(cls, line: Line) -> "_Columns":
        x = {w.text: w.x0 for w in line.words}
        # the range has no header word of its own: it starts between the result and ЛАВЛАХ
        return cls(
            value=x["ХАРИУ"],
            ref=(x["ХАРИУ"] + x["ЛАВЛАХ"]) / 2,
            unit=x["ХЭМЖЭЭ"],
            flag=x["АНХААРУУЛГА"],
        )


@dataclass(slots=True)
class _Panel:
    panel_name: str | None
    specimen: str | None = None
    collected_raw: str | None = None
    analysed_raw: str | None = None
    reported_raw: str | None = None
    rows: list[Row] = field(default_factory=list)

    def report(self) -> ReadReport:
        return ReadReport(
            lab_name=LAB_NAME,
            panel_name=self.panel_name,
            specimen=self.specimen,
            collected_raw=self.collected_raw,
            reported_raw=self.reported_raw,
            results=tuple(self.rows),
            analysed_raw=self.analysed_raw,
        )


def _is_header(line: Line) -> bool:
    return tuple(w.text for w in line.words) == _HEADER


def _between(line: Line, start: str, end: str | None) -> str | None:
    """The words after the label `start` and before the label `end`."""
    texts = [w.text for w in line.words]
    if start not in texts:
        return None
    after = texts[texts.index(start) + 1 :]
    if end is not None and end in after:
        after = after[: after.index(end)]
    return " ".join(after) or None


def _signed_date(line: Line, *, day_only: bool = False) -> str | None:
    """'Шинжилсэн: <who> 2025-08-18 10:15:21' -> '2025-08-18 10:15:21' (the signer is dropped).

    `day_only`: the "Илгээсэн" (sent) date is printed with a placeholder 00:00:00 - only the
    day is known, so only the day is returned (never a made-up midnight; H30).
    """
    texts = [w.text for w in line.words]
    for i, text in enumerate(texts):
        if _DATE.match(text):
            time = texts[i + 1] if i + 1 < len(texts) and _TIME.match(texts[i + 1]) else None
            return f"{text} {time}" if time and not day_only else text
    return None


def _row(line: Line, columns: _Columns, page: int) -> Row | None:
    parts: dict[str, list[str]] = {"name": [], "value": [], "ref": [], "unit": [], "flag": []}
    for word in line.words:
        x = word.x0 + _SLACK
        if x < columns.value:
            parts["name"].append(word.text)
        elif x < columns.ref:
            parts["value"].append(word.text)
        elif x < columns.unit:
            parts["ref"].append(word.text)
        elif x < columns.flag:
            parts["unit"].append(word.text)
        else:
            parts["flag"].append(word.text)
    if not parts["name"] or not parts["value"]:
        return None
    return Row(
        raw_name=" ".join(parts["name"]),
        raw_value=" ".join(parts["value"]),
        raw_unit=" ".join(parts["unit"]) or None,
        ref_text=" ".join(parts["ref"]) or None,
        lab_flag=" ".join(parts["flag"]) or None,
        page=page,
        snippet=line.text[:500],
    )


class _UnteReader:
    NAME: Final = NAME

    def recognises(self, pages: tuple[Page, ...]) -> bool:
        text = "\n".join(line.text for page in pages for line in page.lines)
        has_header = any(_is_header(line) for page in pages for line in page.lines)
        return has_header and "ТӨРӨЛ:" in text and "СОРЬЦ:" in text and bool(_MARK.search(text))

    def read(self, pages: tuple[Page, ...]) -> ReadDocument:
        panels: list[_Panel] = []
        columns: _Columns | None = None
        in_table = False
        family: str | None = None
        given: str | None = None
        for page in pages:
            for line in page.lines:
                first = line.words[0].text
                if _IDENTITY_LABELS.intersection(w.text for w in line.words):
                    family = family or _between(line, "ОВОГ:", "РЕГИСТР:")
                    given = given or _between(line, "НЭР:", "ТӨРСӨН:")
                    continue
                if first == "ТӨРӨЛ:":
                    panels.append(_Panel(panel_name=_between(line, "ТӨРӨЛ:", "БАРКОД:")))
                    in_table = False
                elif first == "СОРЬЦ:" and panels:
                    panels[-1].specimen = _between(line, "СОРЬЦ:", "ТӨХӨӨРӨМЖ:")
                elif _is_header(line):
                    columns = _Columns.from_header(line)
                    in_table = bool(panels)
                elif line.text.startswith("H - лавлах"):
                    in_table = False
                elif first in _SIGNED and panels:
                    field_name, day_only = _SIGNED[first]
                    setattr(panels[-1], field_name, _signed_date(line, day_only=day_only))
                elif first in {"Хуудас", "Байршил:"}:
                    break  # the page footer; a panel open here goes on over the page
                elif in_table and columns is not None:
                    row = _row(line, columns, page.number)
                    if row is not None:
                        panels[-1].rows.append(row)
        return ReadDocument(
            reader=NAME,
            reports=tuple(p.report() for p in panels if p.rows),
            identity=PrintedIdentity(family_name=family, given_name=given),
        )


READER: Final = _UnteReader()
