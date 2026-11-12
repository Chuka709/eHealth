"""The words of a PDF's text layer with their places, grouped into lines (pdfplumber, MIT).

Only for files that passed the upload checks (documents/files.py: type, size, pages, no
scripts). A page without words gives no lines: a scan needs another reader (Q50).
"""

import io
from typing import Final

import pdfplumber

from labtrack.extraction.types import Line, Page, Word

LINE_TOLERANCE: Final = 2.5  # points: words this close in height are one line


def group_lines(words: list[Word]) -> tuple[Line, ...]:
    lines: list[list[Word]] = []
    for word in sorted(words, key=lambda w: (w.top, w.x0)):
        if lines and abs(lines[-1][0].top - word.top) <= LINE_TOLERANCE:
            lines[-1].append(word)
        else:
            lines.append([word])
    return tuple(Line(tuple(sorted(line, key=lambda w: w.x0))) for line in lines)


def read_pages(data: bytes) -> tuple[Page, ...]:
    pages: list[Page] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for number, page in enumerate(pdf.pages, 1):
            words = [
                Word(
                    text=str(w["text"]),
                    x0=float(w["x0"]),
                    x1=float(w["x1"]),
                    top=float(w["top"]),
                )
                for w in page.extract_words(keep_blank_chars=False, use_text_flow=False)
            ]
            pages.append(Page(number=number, lines=group_lines(words)))
    return tuple(pages)
