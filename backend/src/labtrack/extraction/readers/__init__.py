"""Local readers for known lab layouts (Q50). The first that recognises a document reads it."""

from typing import Protocol

from labtrack.extraction.readers.unte import READER as UNTE
from labtrack.extraction.types import Page, ReadDocument


class Reader(Protocol):
    @property
    def NAME(self) -> str: ...  # noqa: N802 - the reader's id, extraction_runs.reader

    def recognises(self, pages: tuple[Page, ...]) -> bool: ...

    def read(self, pages: tuple[Page, ...]) -> ReadDocument: ...


READERS: tuple[Reader, ...] = (UNTE,)


def read_locally(pages: tuple[Page, ...]) -> ReadDocument | None:
    """The document read by a known layout's reader, or None (AI or by hand - Q50)."""
    for reader in READERS:
        if reader.recognises(pages):
            document = reader.read(pages)
            return document if any(r.results for r in document.reports) else None
    return None
