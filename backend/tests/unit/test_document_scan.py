"""clamd INSTREAM client (Phase 3.3) against a fake clamd on a local socket."""

import socket
import struct
import threading

import pytest

from labtrack import config
from labtrack.documents import scan as scan_module
from labtrack.documents.scan import ScanUnavailableError, scan


def _serve(reply: bytes) -> tuple[int, threading.Thread, list[bytes]]:
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    received: list[bytes] = []

    def run() -> None:
        conn, _ = server.accept()
        with conn:
            data = b""
            while not data.endswith(struct.pack(">I", 0)):
                part = conn.recv(65536)
                if not part:
                    break
                data += part
            received.append(data)
            conn.sendall(reply + b"\0")
        server.close()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return server.getsockname()[1], thread, received


def _clamd(monkeypatch: pytest.MonkeyPatch, port: int) -> None:
    settings = config.get_settings().model_copy(
        update={"clamd_host": "127.0.0.1", "clamd_port": port}
    )
    monkeypatch.setattr(scan_module, "get_settings", lambda: settings)


@pytest.mark.parametrize(
    ("reply", "verdict"),
    [(b"stream: OK", "clean"), (b"stream: Eicar-Test-Signature FOUND", "infected")],
)
def test_clean_and_infected(monkeypatch: pytest.MonkeyPatch, reply: bytes, verdict: str) -> None:
    port, thread, received = _serve(reply)
    _clamd(monkeypatch, port)
    data = b"x" * 200_000  # several chunks
    assert scan(data) == verdict
    thread.join(5)
    assert received[0].startswith(b"zINSTREAM\0")
    assert received[0].count(b"x") == len(data)


def test_a_clamd_error_is_never_taken_as_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    port, thread, _ = _serve(b"INSTREAM size limit exceeded. ERROR")
    _clamd(monkeypatch, port)
    with pytest.raises(ScanUnavailableError):
        scan(b"data")
    thread.join(5)


def test_no_scanner_listening_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()  # nothing listens there
    _clamd(monkeypatch, port)
    with pytest.raises(ScanUnavailableError):
        scan(b"data")
