"""Per-user keys for crypto-shredding (docs/04 §6.9; migration 0008).

A user's encrypted fields are sealed with data keys wrapped by that user's own key instead of
the service KEK. Destroying the user's key at purge makes every copy of those fields - backups
included - unreadable. Envelopes record the key as `u:<user id hex>` in their kek_id slot.

Where the user keys live is a `UserKeyStore`: in dev/test a database table (wrapped by the KEK,
so the rows are in database backups too); production (OPENBAO_ADDR) keeps each one in OpenBao
as its own transit key `u-<user id hex>` that never leaves it, and the maintenance worker
destroys it at purge - which is what makes backups unreadable. Either way the database decides
who may use a key: `user_key_get` (only after an audited reveal in this transaction) and
`user_key_put` (only for an account being created in it); with OpenBao the row holds a marker
instead of the wrapped key.
"""

import base64
from typing import Final, Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from labtrack.core.envelope import EnvelopeError, field_aad, new_dek, parse
from labtrack.db.sql import bound_text
from labtrack.keys import (
    KeyProvider,
    LocalKeyProvider,
    TransitKeyProvider,
    decrypt_field,
    encrypt_field,
    get_key_provider,
    get_openbao,
)
from labtrack.openbao import OpenBaoClient

_PREFIX = "u:"
# user_keys.wrapped_key when the key itself is in OpenBao (not a key, not secret)
OPENBAO_MARKER: Final = b"openbao:v1"


class UserKeyStore(Protocol):
    """A user's key as a KeyProvider; None when it is gone (the account was purged)."""

    async def provider(self, user_id: UUID) -> KeyProvider | None: ...

    async def create(self, user_id: UUID) -> KeyProvider: ...


def openbao_key_name(user_id: UUID) -> str:
    return f"u-{user_id.hex}"


def kek_id_for(user_id: UUID) -> str:
    return f"{_PREFIX}{user_id.hex}"


def _key_aad(user_id: UUID) -> bytes:
    return field_aad("user_keys", "wrapped_key", user_id)


async def wrap_user_key(provider: KeyProvider, user_id: UUID, key: bytes) -> bytes:
    return await encrypt_field(provider, base64.b64encode(key).decode(), _key_aad(user_id))


async def unwrap_user_key(provider: KeyProvider, user_id: UUID, blob: bytes) -> bytes:
    return base64.b64decode(await decrypt_field(provider, blob, _key_aad(user_id)))


class DbUserKeyStore:
    """Dev/test: user keys in `user_keys`, wrapped by the service KEK (admin_* context)."""

    def __init__(self, db: AsyncSession, provider: KeyProvider) -> None:
        self._db = db
        self._provider = provider

    async def provider(self, user_id: UUID) -> KeyProvider | None:
        blob = await _key_row(self._db, user_id)
        if blob is None:
            return None
        if blob == OPENBAO_MARKER:
            raise EnvelopeError  # an OpenBao key, and this process has no OpenBao
        return _provider_for(user_id, await unwrap_user_key(self._provider, user_id, blob))

    async def create(self, user_id: UUID) -> KeyProvider:
        """A key for an account being created in this transaction (user_key_put refuses any
        other)."""
        key = new_dek()
        await _put_row(self._db, user_id, await wrap_user_key(self._provider, user_id, key))
        return _provider_for(user_id, key)


class OpenBaoUserKeyStore:
    """Production: the key is OpenBao's transit key `u-<hex>`; the database row only says it
    exists and gates its use exactly as in dev/test."""

    def __init__(self, db: AsyncSession, client: OpenBaoClient) -> None:
        self._db = db
        self._client = client

    def _transit(self, user_id: UUID) -> TransitKeyProvider:
        return TransitKeyProvider(self._client, openbao_key_name(user_id), kek_id_for(user_id))

    async def provider(self, user_id: UUID) -> KeyProvider | None:
        blob = await _key_row(self._db, user_id)
        if blob is None:
            return None
        if blob != OPENBAO_MARKER:
            raise EnvelopeError  # a database-held key: never mixed with OpenBao (fail closed)
        return self._transit(user_id)

    async def create(self, user_id: UUID) -> KeyProvider:
        # the database refuses first (an existing or purged account); a key made in OpenBao for
        # a transaction that then rolls back seals nothing and is left unused
        await _put_row(self._db, user_id, OPENBAO_MARKER)
        await self._client.create_key(openbao_key_name(user_id))
        return self._transit(user_id)


def get_user_key_store(db: AsyncSession) -> UserKeyStore:
    bao = get_openbao()
    if bao is not None:
        return OpenBaoUserKeyStore(db, bao)
    return DbUserKeyStore(db, get_key_provider())


async def _key_row(db: AsyncSession, user_id: UUID) -> bytes | None:
    blob = (await db.execute(bound_text("select user_key_get(:u)"), {"u": user_id})).scalar_one()
    return bytes(blob) if blob is not None else None


async def _put_row(db: AsyncSession, user_id: UUID, wrapped: bytes) -> None:
    await db.execute(bound_text("select user_key_put(:u, :w)"), {"u": user_id, "w": wrapped})


def _provider_for(user_id: UUID, key: bytes) -> LocalKeyProvider:
    kek_id = kek_id_for(user_id)
    return LocalKeyProvider({kek_id: key}, kek_id)


async def seal_for_user(user_id: UUID, key: bytes, plaintext: str, aad: bytes) -> bytes:
    return await encrypt_field(_provider_for(user_id, key), plaintext, aad)


async def encrypt_user_field(
    store: UserKeyStore, user_id: UUID, plaintext: str, aad: bytes
) -> bytes:
    return await encrypt_field(await store.create(user_id), plaintext, aad)


async def decrypt_user_field(store: UserKeyStore, owner: UUID, blob: bytes, aad: bytes) -> str:
    """Decrypts `owner`'s field sealed under the owner's key.

    Raises EnvelopeError when the owner's key is gone (the account was purged), or the value
    was sealed under somebody else's key or the service KEK (either would survive the owner's
    purge; `just rewrap-user-keys` moves older values under user keys).
    """
    kek_id = parse(blob).kek_id
    if not kek_id.startswith(_PREFIX):
        raise EnvelopeError
    try:
        user_id = UUID(hex=kek_id[len(_PREFIX) :])
    except ValueError as exc:
        raise EnvelopeError from exc
    if user_id != owner:
        raise EnvelopeError
    provider = await store.provider(user_id)
    if provider is None:
        raise EnvelopeError  # shredded
    return await decrypt_field(provider, blob, aad)
