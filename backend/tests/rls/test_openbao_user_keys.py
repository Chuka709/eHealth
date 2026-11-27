"""User keys in OpenBao (production; user_keys.OpenBaoUserKeyStore): the database still gates
every use, and the daily purge destroys the key before the account's rows go."""

import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from labtrack.core.envelope import EnvelopeError, field_aad
from labtrack.db.sql import bound_text
from labtrack.keys import TransitKeyProvider, decrypt_field, encrypt_field
from labtrack.openbao import KeyServiceError, OpenBaoClient, OpenBaoConfig
from labtrack.user_keys import (
    OPENBAO_MARKER,
    OpenBaoUserKeyStore,
    decrypt_user_field,
    encrypt_user_field,
    kek_id_for,
    openbao_key_name,
)
from labtrack.worker.maintenance import run_daily
from tests.openbao_support import key_info, needs_openbao, role

from .conftest import as_user, make_user, scalar

pytestmark = [pytest.mark.db, needs_openbao]


async def _user_with_phone(owner_engine: AsyncEngine, api: OpenBaoClient) -> tuple[UUID, bytes]:
    """An account whose phone is sealed under its own OpenBao key (as admin_create_user leaves
    it: the marker row, the key, the sealed value)."""
    user = await make_user(owner_engine)
    await api.create_key(openbao_key_name(user))
    sealed = await encrypt_field(
        TransitKeyProvider(api, openbao_key_name(user), kek_id_for(user)),
        "99112233",
        field_aad("users", "contact_phone_enc", user),
    )
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text("insert into user_keys (user_id, wrapped_key) values (:u, :w)"),
            {"u": user, "w": OPENBAO_MARKER},
        )
        await conn.execute(
            bound_text("update users set contact_phone_enc = :b where id = :u"),
            {"u": user, "b": sealed},
        )
    return user, sealed


async def _delete_31_days_ago(owner_engine: AsyncEngine, user: UUID) -> None:
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text("update users set deleted_at = now() - interval '31 days' where id = :u"),
            {"u": user},
        )


async def test_a_new_account_gets_its_own_key_and_an_existing_one_none(
    owner_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    api = await role("api")
    admin, existing = await make_user(owner_engine, "super_admin"), await make_user(owner_engine)
    fresh = uuid4()
    aad = field_aad("users", "contact_phone_enc", fresh)
    async with as_user(admin_engine, admin) as conn:
        store = OpenBaoUserKeyStore(AsyncSession(bind=conn), api)
        blob = await encrypt_user_field(store, fresh, "99001122", aad)
    async with owner_engine.connect() as conn:  # the admin role cannot read the table at all
        row = await scalar(
            conn, bound_text("select wrapped_key from user_keys where user_id = :u"), {"u": fresh}
        )
    assert bytes(row) == OPENBAO_MARKER  # the key itself is not in the database (nor its backups)
    info = await key_info(openbao_key_name(fresh))
    assert info is not None
    assert info["exportable"] is False
    assert b"99001122" not in blob
    # the database refuses first: no key is made in OpenBao for an existing account
    with pytest.raises(DBAPIError, match="target not allowed"):
        async with as_user(admin_engine, admin) as conn:
            await OpenBaoUserKeyStore(AsyncSession(bind=conn), api).create(existing)
    assert await key_info(openbao_key_name(existing)) is None


async def test_reading_a_phone_still_needs_an_audited_reveal(
    owner_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    api = await role("api")
    support = await make_user(owner_engine, "support")
    user, sealed = await _user_with_phone(owner_engine, api)
    aad = field_aad("users", "contact_phone_enc", user)
    with pytest.raises(DBAPIError, match="admin not allowed"):
        async with as_user(admin_engine, support) as conn:
            await decrypt_user_field(
                OpenBaoUserKeyStore(AsyncSession(bind=conn), api), user, sealed, aad
            )
    async with as_user(admin_engine, support) as conn:
        await conn.execute(bound_text("select admin_reveal_phone(:u)"), {"u": user})
        store = OpenBaoUserKeyStore(AsyncSession(bind=conn), api)
        assert await decrypt_user_field(store, user, sealed, aad) == "99112233"
        with pytest.raises(EnvelopeError):  # never as somebody else's field
            await decrypt_user_field(store, uuid4(), sealed, aad)


async def test_the_purge_destroys_the_key_so_every_copy_is_noise(
    owner_engine: AsyncEngine,
) -> None:
    api, maint = await role("api"), await role("maint")
    user, sealed = await _user_with_phone(owner_engine, api)
    await _delete_31_days_ago(owner_engine, user)
    result = await run_daily(os.environ["TEST_MAINT_DATABASE_URL"], maint)
    assert result.purged_accounts >= 1
    assert await key_info(openbao_key_name(user)) is None
    async with owner_engine.connect() as conn:
        assert not await scalar(
            conn, bound_text("select exists (select 1 from users where id = :u)"), {"u": user}
        )
    # a backup's copy of the ciphertext, with the key gone
    with pytest.raises(EnvelopeError):
        await decrypt_field(
            TransitKeyProvider(api, openbao_key_name(user), kek_id_for(user)),
            sealed,
            field_aad("users", "contact_phone_enc", user),
        )


async def test_openbao_down_means_nothing_is_purged(owner_engine: AsyncEngine) -> None:
    user, _ = await _user_with_phone(owner_engine, await role("api"))
    await _delete_31_days_ago(owner_engine, user)
    down = OpenBaoClient(OpenBaoConfig("http://127.0.0.1:9", "r", "s"))
    with pytest.raises(KeyServiceError):
        await run_daily(os.environ["TEST_MAINT_DATABASE_URL"], down)
    async with owner_engine.connect() as conn:
        # the batch rolled back: the account (and its key) wait for the next run
        assert await scalar(
            conn, bound_text("select exists (select 1 from users where id = :u)"), {"u": user}
        )
    assert await key_info(openbao_key_name(user)) is not None
    await run_daily(os.environ["TEST_MAINT_DATABASE_URL"], await role("maint"))
    assert await key_info(openbao_key_name(user)) is None
