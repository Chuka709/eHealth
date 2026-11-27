"""Virus scan of an uploaded file with clamd (Phase 3.3; docs/04 "ClamAV").

clamd's INSTREAM command over TCP: the bytes are sent in chunks, each prefixed with its length,
and clamd answers "stream: OK" or "stream: <signature> FOUND". The signature name is never
kept or logged - only clean / infected (CLAUDE.md rule 3 spirit: no detail that is not needed).
Outside dev/test a scanner is required: no scanner, no document (fail-closed).
"""

import socket
import struct
from typing import Final, Literal

from labtrack.config import get_settings

CHUNK: Final = 64 * 1024
TIMEOUT_S: Final = 60
MAX_SCAN_BYTES: Final = 21 * 1024 * 1024  # clamd's StreamMaxLength is 25M

Verdict = Literal["clean", "infected"]


class ScanUnavailableError(Exception):
    """clamd could not be reached or did not answer (retried, then the document fails)."""


def scanner_configured() -> bool:
    settings = get_settings()
    if settings.clamd_host:
        return True
    if settings.environment in {"dev", "test"}:
        return False  # dev without the "av" profile: documents go on unscanned
    raise ScanUnavailableError  # production without a scanner: nothing is accepted


def scan(data: bytes) -> Verdict:
    settings = get_settings()
    if not settings.clamd_host or len(data) > MAX_SCAN_BYTES:
        raise ScanUnavailableError
    try:
        with socket.create_connection(
            (settings.clamd_host, settings.clamd_port), timeout=TIMEOUT_S
        ) as conn:
            conn.sendall(b"zINSTREAM\0")
            for start in range(0, len(data), CHUNK):
                piece = data[start : start + CHUNK]
                conn.sendall(struct.pack(">I", len(piece)) + piece)
            conn.sendall(struct.pack(">I", 0))
            answer = _read_reply(conn)
    except OSError as exc:
        raise ScanUnavailableError from exc
    if answer == b"stream: OK":
        return "clean"
    if answer.startswith(b"stream: ") and answer.endswith(b" FOUND"):
        return "infected"
    # "INSTREAM size limit exceeded" and any other error: not scanned, so not accepted
    raise ScanUnavailableError


def _read_reply(conn: socket.socket) -> bytes:
    reply = b""
    while not reply.endswith(b"\0"):
        part = conn.recv(4096)
        if not part:
            break
        reply += part
        if len(reply) > 4096:  # noqa: PLR2004 - a clamd reply is one short line
            break
    return reply.rstrip(b"\0").strip()
