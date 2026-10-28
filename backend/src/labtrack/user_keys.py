"""Per-user keys for crypto-shredding (docs/04 §6.9; migration 0008).

A user's encrypted fields are sealed with data keys wrapped by that user's own key instead of
the service KEK. Destroying the user's key at purge makes every copy of those fields - backups
included - unreadable. Envelopes record the key as `u:<user id hex>` in their kek_id slot.

Where the user keys live is a `UserKeyStore`: in dev/test a database table (wrapped by the KEK,
so the rows are in database backups too); production stores them in OpenBao as named keys and
destroys them there, which is what makes backups unreadable.
"""

import base64
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from labtrack.core.envelope import EnvelopeError, field_aad, new_dek, parse
from labtrack.db.sql import bound_text
from labtrack.keys import KeyProvider, LocalKeyProvider, decrypt_field, encrypt_field

_PREFIX = "u:"


class UserKeyStore(Protocol):
    async def get(self, user_id: UUID) -> bytes | None: ...

    async def get_or_create(self, user_id: UUID) -> bytes: ...


class DbUserKeyStore:
    """Dev/test: user keys in `user_keys`, wrapped by the service KEK (admin_* context)."""

    def __init__(self, db: AsyncSession, provider: KeyProvider) -> None:
        self._db = db
        self._provider = provider

    @staticmethod
    def _aad(user_id: UUID) -> bytes:
        return field_aad("user_keys", "wrapped_key", user_id)

    async def _open(self, user_id: UUID, blob: bytes) -> bytes:
        return base64.b64decode(await decrypt_field(self._provider, blob, self._aad(user_id)))

    async def get(self, user_id: UUID) -> bytes | None:
        blob = (
            await self._db.execute(bound_text("select user_key_get(:u)"), {"u": user_id})
        ).scalar_one()
        return await self._open(user_id, blob) if blob is not None else None

    async def get_or_create(self, user_id: UUID) -> bytes:
        fresh = base64.b64encode(new_dek()).decode()
        wrapped = await encrypt_field(self._provider, fresh, self._aad(user_id))
        stored = (
            await self._db.execute(
                bound_text("select user_key_put(:u, :w)"), {"u": user_id, "w": wrapped}
            )
        ).scalar_one()
        return await self._open(user_id, stored)


def _provider_for(user_id: UUID, key: bytes) -> LocalKeyProvider:
    kek_id = f"{_PREFIX}{user_id.hex}"
    return LocalKeyProvider({kek_id: key}, kek_id)


async def encrypt_user_field(
    store: UserKeyStore, user_id: UUID, plaintext: str, aad: bytes
) -> bytes:
    return await encrypt_field(
        _provider_for(user_id, await store.get_or_create(user_id)), plaintext, aad
    )


async def decrypt_user_field(
    store: UserKeyStore, provider: KeyProvider, owner: UUID, blob: bytes, aad: bytes
) -> str:
    """Decrypts `owner`'s field: a user-key envelope, or an older one under the service KEK.

    Raises EnvelopeError when the owner's key is gone (the account was purged) or the value
    was sealed under somebody else's key (it would then survive the owner's purge).
    """
    kek_id = parse(blob).kek_id
    if not kek_id.startswith(_PREFIX):
        return await decrypt_field(provider, blob, aad)
    try:
        user_id = UUID(hex=kek_id[len(_PREFIX) :])
    except ValueError as exc:
        raise EnvelopeError from exc
    if user_id != owner:
        raise EnvelopeError
    key = await store.get(user_id)
    if key is None:
        raise EnvelopeError  # shredded
    return await decrypt_field(_provider_for(user_id, key), blob, aad)
