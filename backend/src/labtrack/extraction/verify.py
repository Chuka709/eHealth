"""An AI reading checked against the text it was given (4.5 reviews: H1, prompt injection).

A row's value - and its range, when one is given - must be found in one line of the text
that was sent; that line becomes the row's evidence (`snippet`). A row whose value or range
is not in the text is kept for the person to see but marked `not_in_source`, so a made-up
value (an error, or an instruction hidden in the document) never looks printed; a critical
limit not in the text is dropped (no banner from a made-up limit). Matching is
on whole tokens after folding spaces, case and Unicode forms ("5.4" is not found in "15.4").
"""

import re
import unicodedata
from dataclasses import replace

from labtrack.extraction.types import ReadDocument, ReadReport, ReadResult


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip().casefold()


def _contains(line: str, part: str) -> bool:
    if not part:
        return True
    return re.search(rf"(?<![\w.,]){re.escape(part)}(?![\w.,])", line) is not None


def _check(row: ReadResult, lines: list[str]) -> ReadResult:
    value, ref, name = _norm(row.raw_value), _norm(row.ref_text or ""), _norm(row.raw_name)
    unit = _norm(row.raw_unit or "")
    with_value = [line for line in lines if value and _contains(line, value)]
    # the line that also has the test's name, else any line with the value
    best = next((line for line in with_value if name and name in line), None)
    best = best or (with_value[0] if with_value else None)
    # the unit may be printed in a column header: anywhere in the text, then
    unit_found = not unit or any(_contains(line, unit) for line in lines)
    if best is None or not _contains(best, ref) or not unit_found:
        issues = (*row.issues, "not_in_source")
        return replace(row, issues=tuple(dict.fromkeys(issues)), snippet=best or "")
    critical = _norm(row.critical_text or "")
    if critical and not any(_contains(line, critical) for line in lines):
        # a critical limit not in the text is dropped: no banner from a made-up limit
        issues = tuple(dict.fromkeys((*row.issues, "not_in_source")))
        return replace(row, critical_text=None, issues=issues, snippet=best[:500])
    return replace(row, snippet=best[:500])


def check_against_source(document: ReadDocument, source: str) -> ReadDocument:
    lines = [_norm(line) for line in source.splitlines() if line.strip()]
    return replace(
        document,
        reports=tuple(
            ReadReport(
                lab_name=r.lab_name,
                panel_name=r.panel_name,
                specimen=r.specimen,
                collected_raw=r.collected_raw,
                reported_raw=r.reported_raw,
                analysed_raw=r.analysed_raw,
                results=tuple(_check(x, lines) for x in r.results),
            )
            for r in document.reports
        ),
    )
