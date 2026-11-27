"""Reading an untrusted PDF in a process of its own (commit security review 4.4).

A crafted PDF can make the parser use unbounded memory or CPU before any check of ours runs
(pdfplumber decodes a page's content to count its characters). So the parse runs in a child
process the worker can kill: a wall-clock timeout (the child is killed, not left running),
and on Linux an address-space and CPU limit set before the child starts. The child gets the
file on stdin and writes the reading as JSON on stdout - the printed name included, since it
is needed for the name check; it never reaches a log (stderr is discarded: a traceback may
quote the document).

`python -m labtrack.extraction.isolated` is the child; `read_isolated` is the parent's side.
"""

import json
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Final

from labtrack.extraction.types import (
    PrintedIdentity,
    ReadDocument,
    ReadReport,
    ReadResult,
)

MEMORY_LIMIT: Final = 1024 * 1024 * 1024  # bytes of address space for the child
CPU_LIMIT: Final = 60  # seconds of CPU
MAX_TEXT_CHARS: Final = 60_000  # text handed on for the AI: a few report pages


class IsolatedReadError(Exception):
    """The child failed (crashed, killed by a limit, bad output) - no details kept."""


def _limits() -> None:  # pragma: no cover - runs in the child before exec
    if sys.platform != "win32":  # the worker runs on Linux; Windows only for local tools
        import resource  # noqa: PLC0415 - POSIX only

        resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT, MEMORY_LIMIT))
        resource.setrlimit(resource.RLIMIT_CPU, (CPU_LIMIT, CPU_LIMIT))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def to_json(document: ReadDocument) -> dict[str, Any]:
    return {
        "reader": document.reader,
        "identity": {
            "family_name": document.identity.family_name,
            "given_name": document.identity.given_name,
        },
        "reports": [
            {
                "lab_name": r.lab_name,
                "panel_name": r.panel_name,
                "specimen": r.specimen,
                "collected_raw": r.collected_raw,
                "reported_raw": r.reported_raw,
                "analysed_raw": r.analysed_raw,
                "results": [
                    [
                        x.raw_name,
                        x.raw_value,
                        x.raw_unit,
                        x.ref_text,
                        x.lab_flag,
                        x.page,
                        x.snippet,
                        x.critical_text,
                        list(x.issues),
                    ]
                    for x in r.results
                ],
            }
            for r in document.reports
        ],
    }


def from_json(data: dict[str, Any]) -> ReadDocument:
    return ReadDocument(
        reader=str(data["reader"]),
        identity=PrintedIdentity(**data["identity"]),
        reports=tuple(
            ReadReport(
                lab_name=r["lab_name"],
                panel_name=r["panel_name"],
                specimen=r["specimen"],
                collected_raw=r["collected_raw"],
                reported_raw=r["reported_raw"],
                analysed_raw=r["analysed_raw"],
                results=tuple(
                    ReadResult(
                        raw_name=str(x[0]),
                        raw_value=str(x[1]),
                        raw_unit=x[2],
                        ref_text=x[3],
                        lab_flag=x[4],
                        page=None if x[5] is None else int(x[5]),
                        snippet=str(x[6]),
                        critical_text=x[7] if len(x) > 7 else None,  # noqa: PLR2004
                        issues=tuple(str(i) for i in x[8]) if len(x) > 8 else (),  # noqa: PLR2004
                    )
                    for x in r["results"]
                ),
            )
            for r in data["reports"]
        ),
    )


@dataclass(frozen=True, slots=True)
class Reading:
    """A known layout's reading, or else the page text lines (for the AI, after deidentify)."""

    document: ReadDocument | None
    lines: tuple[tuple[int, str], ...] = ()


def read_isolated(data: bytes, *, timeout: float) -> Reading:
    """The document read in a child process.

    Raises TimeoutError (the child was killed) or IsolatedReadError.
    """
    try:
        done = subprocess.run(
            [sys.executable, "-I", "-m", "labtrack.extraction.isolated"],
            input=data,
            capture_output=True,
            timeout=timeout,
            check=False,
            preexec_fn=_limits if sys.platform != "win32" else None,
        )
    except subprocess.TimeoutExpired:
        raise TimeoutError from None  # subprocess.run has killed the child
    if done.returncode != 0:
        raise IsolatedReadError
    try:
        answer = json.loads(done.stdout)
        document = None if answer["document"] is None else from_json(answer["document"])
        lines = tuple((int(page), str(text)) for page, text in answer["lines"])
        return Reading(document, lines)
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        raise IsolatedReadError from exc


def _main() -> None:  # pragma: no cover - exercised through read_isolated
    from labtrack.extraction.readers import read_locally  # noqa: PLC0415
    from labtrack.extraction.text_pdf import TooMuchText, read_pages  # noqa: PLC0415

    data = sys.stdin.buffer.read()
    try:
        pages = read_pages(data)
    except TooMuchText:
        pages = ()
    document = read_locally(pages) if pages else None
    lines: list[tuple[int, str]] = []
    if document is None:  # the text, for the AI path - capped
        size = 0
        for page in pages:
            for line in page.lines:
                size += len(line.text)
                if size > MAX_TEXT_CHARS:
                    break
                lines.append((page.number, line.text))
    out = {"document": None if document is None else to_json(document), "lines": lines}
    # bytes: UTF-8 whatever the platform's console encoding is (Windows dev machines)
    sys.stdout.buffer.write(json.dumps(out, ensure_ascii=False).encode("utf-8"))


if __name__ == "__main__":
    _main()
