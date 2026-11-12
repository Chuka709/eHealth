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
from typing import Any, Final

from labtrack.extraction.types import (
    PrintedIdentity,
    ReadDocument,
    ReadReport,
    ReadResult,
)

MEMORY_LIMIT: Final = 1024 * 1024 * 1024  # bytes of address space for the child
CPU_LIMIT: Final = 60  # seconds of CPU


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
                    [x.raw_name, x.raw_value, x.raw_unit, x.ref_text, x.lab_flag, x.page, x.snippet]
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
                        page=int(x[5]),
                        snippet=str(x[6]),
                    )
                    for x in r["results"]
                ),
            )
            for r in data["reports"]
        ),
    )


def read_isolated(data: bytes, *, timeout: float) -> ReadDocument | None:
    """The document read in a child process; None when no local reader can read it.

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
        return None if answer["document"] is None else from_json(answer["document"])
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        raise IsolatedReadError from exc


def _main() -> None:  # pragma: no cover - exercised through read_isolated
    from labtrack.extraction.readers import read_locally  # noqa: PLC0415
    from labtrack.extraction.text_pdf import TooMuchText, read_pages  # noqa: PLC0415

    data = sys.stdin.buffer.read()
    try:
        document = read_locally(read_pages(data))
    except TooMuchText:
        document = None
    out = {"document": None if document is None else to_json(document)}
    sys.stdout.write(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    _main()
