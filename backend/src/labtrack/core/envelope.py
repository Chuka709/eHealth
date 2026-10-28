"""Envelope encryption format for `*_enc` columns (docs/04 §1 "Шифрлэлт ба түлхүүр").

Pure functions, no key management: a fresh 256-bit data key (DEK) encrypts each value with
AES-256-GCM, and the caller's KeyProvider wraps that DEK under a key-encryption key (KEK).

Layout (all lengths big-endian):
    ver(1) | kek_id_len(1) | kek_id | wrapped_len(2) | wrapped_dek | nonce(12) | ciphertext+tag

The associated data binds a value to its place (`table:column:row_id`) and to its own header,
so a ciphertext copied into another row, column or table fails to decrypt instead of silently
showing another person's data.
"""

import os
import re
import struct
from dataclasses import dataclass
from typing import Final

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

VERSION: Final = 1
NONCE_BYTES: Final = 12
KEY_BYTES: Final = 32
_KEK_ID = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
_AAD_PART = re.compile(r"^[a-z0-9_-]{1,64}$")


class EnvelopeError(Exception):
    """Malformed envelope, wrong key or wrong associated data. Never says which."""


@dataclass(frozen=True)
class Envelope:
    kek_id: str
    wrapped_dek: bytes
    nonce: bytes
    ciphertext: bytes

    def header(self) -> bytes:
        kek = self.kek_id.encode("ascii")
        return (
            struct.pack(">BB", VERSION, len(kek))
            + kek
            + struct.pack(">H", len(self.wrapped_dek))
            + self.wrapped_dek
        )


def field_aad(table: str, column: str, row_id: object) -> bytes:
    """`table:column:row_id`; table and column are identifiers, never user input."""
    if not (_AAD_PART.match(table) and _AAD_PART.match(column)):
        raise ValueError("table and column must be identifiers")
    row = str(row_id)
    if not row or ":" in row:
        raise ValueError("row id must be non-empty and contain no ':'")
    return f"{table}:{column}:{row}".encode("ascii")


def new_dek() -> bytes:
    return AESGCM.generate_key(bit_length=KEY_BYTES * 8)


def seal(plaintext: bytes, *, dek: bytes, kek_id: str, wrapped_dek: bytes, aad: bytes) -> bytes:
    if not _KEK_ID.match(kek_id):
        raise ValueError("invalid kek id")
    if len(dek) != KEY_BYTES or not wrapped_dek or len(wrapped_dek) > 0xFFFF:  # noqa: PLR2004
        raise ValueError("invalid data key")
    nonce = os.urandom(NONCE_BYTES)
    env = Envelope(kek_id, wrapped_dek, nonce, b"")
    ct = AESGCM(dek).encrypt(nonce, plaintext, env.header() + aad)
    return env.header() + nonce + ct


def parse(blob: bytes) -> Envelope:
    try:
        version, kek_len = struct.unpack_from(">BB", blob, 0)
        pos = 2
        kek_id = blob[pos : pos + kek_len].decode("ascii")
        pos += kek_len
        (wrapped_len,) = struct.unpack_from(">H", blob, pos)
        pos += 2
        wrapped = blob[pos : pos + wrapped_len]
        pos += wrapped_len
        nonce = blob[pos : pos + NONCE_BYTES]
        ciphertext = blob[pos + NONCE_BYTES :]
    except (struct.error, UnicodeDecodeError) as exc:
        raise EnvelopeError from exc
    if (
        version != VERSION
        or not _KEK_ID.match(kek_id)
        or len(wrapped) != wrapped_len
        or wrapped_len == 0
        or len(nonce) != NONCE_BYTES
        or len(ciphertext) < 16  # noqa: PLR2004 - GCM tag
    ):
        raise EnvelopeError
    return Envelope(kek_id, wrapped, nonce, ciphertext)


def open_sealed(env: Envelope, *, dek: bytes, aad: bytes) -> bytes:
    try:
        return AESGCM(dek).decrypt(env.nonce, env.ciphertext, env.header() + aad)
    except (InvalidTag, ValueError) as exc:
        raise EnvelopeError from exc
