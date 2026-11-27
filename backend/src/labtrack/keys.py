"""Key management for field encryption (docs/04 §1, Q5).

`KeyProvider` wraps and unwraps data keys under a key-encryption key (KEK) that never leaves
the provider: dev/test use a KEK from the environment (Docker secret), production the OpenBao
transit engine (`TransitKeyProvider`; used wherever OPENBAO_ADDR is set). Outside dev/test there
is no fallback - a missing provider stops the service rather than storing secrets under a
development key.
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
from labtrack.openbao import KeyNotFoundError, KeyServiceError, OpenBaoClient

_WRAP_CONTEXT: Final = b"labtrack-dek:"
# the service KEK in OpenBao (infra/openbao/setup); its versions live inside the ciphertext, so
# a rotation (`bao write -f transit/keys/labtrack-kek/rotate`) keeps the same id here
SERVICE_KEK: Final = "labtrack-kek"
SERVICE_KEK_ID: Final = "bao:labtrack-kek"


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


class TransitKeyProvider:
    """A KEK that stays in OpenBao: the data key goes there to be wrapped and comes back to be
    unwrapped, bound to the field's AAD (OpenBao's associated_data). Nothing is cached."""

    def __init__(
        self, client: OpenBaoClient, key: str, kek_id: str, *, missing_is_outage: bool = False
    ) -> None:
        self._client = client
        self._key = key
        self._kek_id = kek_id
        # the service KEK never goes: missing, OpenBao is misconfigured or was emptied - every
        # document must not turn "unreadable" for it (security review S1 M1). A user's key
        # missing is a purged account.
        self._missing_is_outage = missing_is_outage

    @property
    def current_kek_id(self) -> str:
        return self._kek_id

    async def wrap(self, dek: bytes, aad: bytes) -> bytes:
        return await self._client.encrypt(self._key, dek, _WRAP_CONTEXT + aad)

    async def unwrap(self, kek_id: str, wrapped: bytes, aad: bytes) -> bytes:
        if kek_id != self._kek_id:
            raise EnvelopeError
        try:
            dek = await self._client.decrypt(self._key, wrapped, _WRAP_CONTEXT + aad)
        except KeyNotFoundError as exc:
            if self._missing_is_outage:
                raise KeyServiceError("openbao has no service KEK") from exc
            raise
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


async def encrypt_bytes(provider: KeyProvider, data: bytes, aad: bytes) -> bytes:
    """A file (an uploaded document) sealed as a field is: its own data key, wrapped (Q49)."""
    dek = new_dek()
    wrapped = await provider.wrap(dek, aad)
    return seal(data, dek=dek, kek_id=provider.current_kek_id, wrapped_dek=wrapped, aad=aad)


async def decrypt_bytes(provider: KeyProvider, blob: bytes, aad: bytes) -> bytes:
    env = parse(blob)
    dek = await provider.unwrap(env.kek_id, env.wrapped_dek, aad)
    return open_sealed(env, dek=dek, aad=aad)


@lru_cache
def get_openbao() -> OpenBaoClient | None:
    """One client (and AppRole token) per process; None without OPENBAO_ADDR."""
    config = get_settings().openbao()
    return OpenBaoClient(config) if config is not None else None


@lru_cache
def get_key_provider() -> KeyProvider:
    settings = get_settings()
    bao = get_openbao()
    if bao is not None:
        return TransitKeyProvider(bao, SERVICE_KEK, SERVICE_KEK_ID, missing_is_outage=True)
    if settings.environment not in {"dev", "test"}:
        raise RuntimeError("OPENBAO_ADDR is required outside dev/test")
    if settings.dev_kek is None:
        raise RuntimeError("LABTRACK_DEV_KEK is required in dev/test")
    try:
        kek = base64.b64decode(settings.dev_kek.get_secret_value(), validate=True)
    except binascii.Error as exc:
        raise RuntimeError("LABTRACK_DEV_KEK must be base64") from exc
    return LocalKeyProvider({"dev1": kek}, "dev1")
