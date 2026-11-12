"""The untrusted PDF parse in a child process (commit security review 4.4).

In the Linux container: the child has memory and CPU limits and is killed on timeout.
"""

import subprocess
import sys
from typing import Any

import pytest

from labtrack.extraction import isolated
from labtrack.extraction.isolated import IsolatedReadError, from_json, read_isolated, to_json
from labtrack.extraction.types import PrintedIdentity, ReadDocument, ReadReport, ReadResult

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the worker runs on Linux")


def _pdf(lines: list[tuple[float, float, str]]) -> bytes:
    """A one-page PDF (Helvetica) with text at (x, y-from-top) points; Latin only."""
    height = 842
    body = "".join(
        f"BT /F1 10 Tf {x} {height - y} Td ({text}) Tj ET\n" for x, y, text in lines
    ).encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R"
        b" /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(body)).encode() + b" >>\nstream\n" + body + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode()
    out += f"startxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def test_a_pdf_of_no_known_layout_is_read_as_nothing() -> None:
    assert read_isolated(_pdf([(25, 100, "Glucose 5.4")]), timeout=30) is None


def test_garbage_makes_the_child_fail_without_details() -> None:
    with pytest.raises(IsolatedReadError) as caught:
        read_isolated(b"not a pdf at all", timeout=30)
    assert str(caught.value) == ""


def test_a_child_that_runs_too_long_is_killed(monkeypatch: pytest.MonkeyPatch) -> None:
    real_run = subprocess.run

    def slow(*args: object, **kwargs: Any) -> object:
        return real_run(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            timeout=kwargs["timeout"],
            capture_output=True,
            check=False,
        )

    monkeypatch.setattr(subprocess, "run", slow)  # the module isolated.py uses
    with pytest.raises(TimeoutError):
        read_isolated(b"%PDF", timeout=0.5)


def test_the_child_cannot_take_unbounded_memory() -> None:
    """The address-space limit is in force in the child."""
    done = subprocess.run(
        [sys.executable, "-c", "b = bytearray(2 * 1024 ** 3)"],
        capture_output=True,
        check=False,
        preexec_fn=isolated._limits,
    )
    assert done.returncode != 0
    assert b"MemoryError" in done.stderr


def test_the_reading_crosses_the_pipe_whole() -> None:
    document = ReadDocument(
        reader="unte.v1",
        reports=(
            ReadReport(
                "Lab",
                "Биохими",
                "цус",
                "2025-08-18",
                "2025-08-18 12:05:52",
                (ReadResult("Глюкоз", "5.37", "ммоль/л", "4.11 - 6.38", "H", 1, "Глюкоз 5.37"),),
                "2025-08-18 10:15:21",
            ),
        ),
        identity=PrintedIdentity("Тест", "Хэрэглэгч"),
    )
    again = from_json(to_json(document))
    assert again == document
    assert (again.identity.family_name, again.identity.given_name) == ("Тест", "Хэрэглэгч")
