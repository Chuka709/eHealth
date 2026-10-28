"""Key management for field encryption (docs/04 §1, Q5).

`KeyProvider` wraps and unwraps data keys under a key-encryption key (KEK) that never leaves
the provider: dev/test use a KEK from the environment (Docker secret), production will use the
OpenBao transit engine. Outside dev/test there is no fallback - a missing provider stops the
service rather than storing secrets under a development key.
"""

import base64
import binascii
import os
from functools import lru_cache
from typing import Final, Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from labtrack.config import get_settings
from labtrack.core.envelope import (
    KEY_BYTES,
    NONCE_BYTES,
    EnvelopeError,
    new_dek,
    open_sealed,
    parse,
    seal,
)

_WRAP_CONTEXT: Final = b"labtrack-dek:"


class KeyProvider(Protocol):
    """Contract: unwrap must not cache data keys. Admin sign-in decrypts a fixed dummy secret
    when the password is wrong; a cache would make that path faster than the real one."""

    @property
    def current_kek_id(self) -> str: ...

    async def wrap(self, dek: bytes, aad: bytes) -> bytes: ...

    async def unwrap(self, kek_id: str, wrapped: bytes, aad: bytes) -> bytes: ...


class LocalKeyProvider:
    """KEKs held in process memory (dev/test). Old KEKs stay readable after rotation."""

    def __init__(self, keks: dict[str, bytes], current: str) -> None:
        if current not in keks or any(len(k) != KEY_BYTES for k in keks.values()):
            raise ValueError("invalid KEK set")
        self._keks = dict(keks)
        self._current = current

    @property
    def current_kek_id(self) -> str:
        return self._current

    async def wrap(self, dek: bytes, aad: bytes) -> bytes:
        nonce = os.urandom(NONCE_BYTES)
        return nonce + AESGCM(self._keks[self._current]).encrypt(nonce, dek, _WRAP_CONTEXT + aad)

    async def unwrap(self, kek_id: str, wrapped: bytes, aad: bytes) -> bytes:
        kek = self._keks.get(kek_id)
        if kek is None:
            raise EnvelopeError
        try:
            dek = AESGCM(kek).decrypt(
                wrapped[:NONCE_BYTES], wrapped[NONCE_BYTES:], _WRAP_CONTEXT + aad
            )
        except (InvalidTag, ValueError) as exc:
            raise EnvelopeError from exc
        if len(dek) != KEY_BYTES:
            raise EnvelopeError
        return dek


async def encrypt_field(provider: KeyProvider, plaintext: str, aad: bytes) -> bytes:
    dek = new_dek()
    wrapped = await provider.wrap(dek, aad)
    return seal(
        plaintext.encode("utf-8"),
        dek=dek,
        kek_id=provider.current_kek_id,
        wrapped_dek=wrapped,
        aad=aad,
    )


async def decrypt_field(provider: KeyProvider, blob: bytes, aad: bytes) -> str:
    env = parse(blob)
    dek = await provider.unwrap(env.kek_id, env.wrapped_dek, aad)
    try:
        return open_sealed(env, dek=dek, aad=aad).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EnvelopeError from exc


@lru_cache
def get_key_provider() -> KeyProvider:
    settings = get_settings()
    if settings.environment not in {"dev", "test"}:
        # Production: OpenBao transit (docs/04 §1) - implemented before the first deployment.
        raise RuntimeError("no KeyProvider configured outside dev/test")
    if settings.dev_kek is None:
        raise RuntimeError("LABTRACK_DEV_KEK is required in dev/test")
    try:
        kek = base64.b64decode(settings.dev_kek.get_secret_value(), validate=True)
    except binascii.Error as exc:
        raise RuntimeError("LABTRACK_DEV_KEK must be base64") from exc
    return LocalKeyProvider({"dev1": kek}, "dev1")
