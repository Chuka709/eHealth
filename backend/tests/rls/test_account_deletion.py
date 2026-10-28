"""0008: deletion request, 30-day purge as labtrack_maint, cancellation, crypto-shredding."""

import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from labtrack.core.envelope import EnvelopeError, field_aad, parse
from labtrack.db.sql import bound_text
from labtrack.keys import get_key_provider
from labtrack.user_keys import DbUserKeyStore, decrypt_user_field, encrypt_user_field
from labtrack.worker.maintenance import run_daily

from .conftest import as_user, grant, make_patient, make_user, scalar

pytestmark = pytest.mark.db


async def _request(app_engine: AsyncEngine, user: UUID) -> object:
    async with as_user(app_engine, user) as conn:
        return await scalar(conn, bound_text("select request_account_deletion()"))


async def _age(owner_engine: AsyncEngine, user: UUID, days: int) -> None:
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "update users set deleted_at = now() - make_interval(days => :d) where id = :u"
            ),
            {"d": days, "u": user},
        )


async def _purge(maint_engine: AsyncEngine) -> list[UUID]:
    async with maint_engine.connect() as conn, conn.begin():
        return list(
            (await conn.execute(bound_text("select * from maint_purge_deleted_users(500)")))
            .scalars()
            .all()
        )


async def _exists(owner_engine: AsyncEngine, sql: str, **p: object) -> bool:
    async with owner_engine.connect() as conn:
        return bool(await scalar(conn, bound_text(f"select exists ({sql})"), p))


async def test_deletion_request_ends_access_at_once(
    owner_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    user = await make_user(owner_engine)
    async with owner_engine.connect() as conn, conn.begin():
        username = await scalar(
            conn, bound_text("select username from users where id = :u"), {"u": user}
        )
        sid = await scalar(
            conn,
            bound_text(
                "insert into sessions (user_id, family_id, token_hash, expires_at,"
                " family_expires_at) values (:u, gen_random_uuid(), :h, now() + interval '1 day',"
                " now() + interval '1 day') returning id"
            ),
            {"u": user, "h": uuid4().hex * 2},
        )
    await _request(app_engine, user)
    async with app_engine.connect() as conn, conn.begin():
        assert (
            await conn.execute(bound_text("select * from auth_login_lookup(:u)"), {"u": username})
        ).all() == []
        assert (
            await scalar(conn, bound_text("select session_check(:s, :u, 1)"), {"s": sid, "u": user})
            is False
        )
    with pytest.raises(DBAPIError, match="deletion not allowed"):  # once
        await _request(app_engine, user)
    with pytest.raises(DBAPIError, match="deletion not allowed"):  # no user context
        await _request(app_engine, None)  # type: ignore[arg-type]


async def test_purge_waits_30_days_then_erases_only_the_users_data(
    owner_engine: AsyncEngine, app_engine: AsyncEngine, maint_engine: AsyncEngine
) -> None:
    leaving, staying = await make_user(owner_engine), await make_user(owner_engine)
    own = await make_patient(app_engine, leaving)
    other = await make_patient(app_engine, staying)
    await grant(app_engine, staying, other, leaving, "viewer")
    async with as_user(app_engine, leaving) as conn:
        await conn.execute(
            bound_text(
                "insert into consents (user_id, kind, version, granted)"
                " values (app_user_id(), 'terms', '1', true)"
            )
        )
    await _request(app_engine, leaving)
    await _age(owner_engine, leaving, 29)
    assert leaving not in await _purge(maint_engine)
    assert await _exists(owner_engine, "select 1 from users where id = :u", u=leaving)

    await _age(owner_engine, leaving, 31)
    assert leaving in await _purge(maint_engine)
    for sql in (
        "select 1 from users where id = :u",
        "select 1 from patients where id = :p",
        "select 1 from patient_access where user_id = :u",
        "select 1 from consents where user_id = :u",
    ):
        assert not await _exists(owner_engine, sql, u=leaving, p=own), sql
    assert await _exists(owner_engine, "select 1 from patients where id = :p", p=other)
    assert await _exists(owner_engine, "select 1 from users where id = :u", u=staying)
    assert await _exists(
        owner_engine,
        "select 1 from audit_logs where action = 'account.purged' and target_user_id = :u",
        u=leaving,
    )


async def test_only_maintenance_purges(
    owner_engine: AsyncEngine, app_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    user, admin = await make_user(owner_engine), await make_user(owner_engine, "super_admin")
    for engine, actor in ((app_engine, user), (admin_engine, admin)):
        with pytest.raises(DBAPIError, match="permission denied"):
            async with as_user(engine, actor) as conn:
                await conn.execute(bound_text("select * from maint_purge_deleted_users(1)"))


async def test_maintenance_role_reads_no_accounts(maint_engine: AsyncEngine) -> None:
    with pytest.raises(DBAPIError, match="permission denied"):
        async with maint_engine.connect() as conn:
            await conn.execute(bound_text("select username from users"))


async def test_cancellation_restores_a_locked_account_needing_a_reset(
    owner_engine: AsyncEngine, app_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    admin, support = (
        await make_user(owner_engine, "super_admin"),
        await make_user(owner_engine, "support"),
    )
    user = await make_user(owner_engine)
    await _request(app_engine, user)
    with pytest.raises(DBAPIError, match="admin not allowed"):
        async with as_user(admin_engine, support) as conn:
            await conn.execute(bound_text("select admin_cancel_deletion(:u)"), {"u": user})
    async with as_user(admin_engine, admin) as conn:
        await conn.execute(bound_text("select admin_cancel_deletion(:u)"), {"u": user})
    async with owner_engine.connect() as conn:
        row = (
            await conn.execute(
                bound_text(
                    "select account_status, reset_required, deleted_at from users where id = :u"
                ),
                {"u": user},
            )
        ).one()
    assert (row.account_status, row.reset_required, row.deleted_at) == ("locked", True, None)
    with pytest.raises(DBAPIError, match="password reset required"):
        async with as_user(admin_engine, admin) as conn:
            await conn.execute(
                bound_text("select admin_set_status(:u, 'active', 'identity_verified')"),
                {"u": user},
            )


async def test_no_cancellation_after_30_days(
    owner_engine: AsyncEngine, app_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    admin, user = await make_user(owner_engine, "super_admin"), await make_user(owner_engine)
    await _request(app_engine, user)
    await _age(owner_engine, user, 31)
    with pytest.raises(DBAPIError, match="no pending deletion"):
        async with as_user(admin_engine, admin) as conn:
            await conn.execute(bound_text("select admin_cancel_deletion(:u)"), {"u": user})


async def test_purge_shreds_every_copy_of_the_users_encrypted_fields(
    owner_engine: AsyncEngine, app_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    admin, user = await make_user(owner_engine, "super_admin"), await make_user(owner_engine)
    aad = field_aad("users", "contact_phone_enc", user)
    provider = get_key_provider()
    async with as_user(admin_engine, admin) as conn:
        store = DbUserKeyStore(AsyncSession(bind=conn), provider)
        backup_copy = await encrypt_user_field(store, user, "99112233", aad)
        assert parse(backup_copy).kek_id == f"u:{user.hex}"
        assert await decrypt_user_field(store, provider, user, backup_copy, aad) == "99112233"
        # sealed under one user's key, it never decrypts as somebody else's field
        other = uuid4()
        with pytest.raises(EnvelopeError):
            await decrypt_user_field(
                store, provider, other, backup_copy, field_aad("users", "contact_phone_enc", other)
            )
    await _request(app_engine, user)
    await _age(owner_engine, user, 31)
    result = await run_daily(os.environ["TEST_MAINT_DATABASE_URL"])
    assert result.purged_accounts >= 1
    async with as_user(admin_engine, admin) as conn:
        store = DbUserKeyStore(AsyncSession(bind=conn), provider)
        with pytest.raises(EnvelopeError):  # the key is gone: the copy is noise
            await decrypt_user_field(store, provider, user, backup_copy, aad)


async def test_old_login_records_are_removed(
    owner_engine: AsyncEngine,
) -> None:
    name = f"old{uuid4().hex[:8]}"
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "insert into auth_attempts (kind, username, success, at) values"
                " ('login', :n, false, now() - interval '91 days'),"
                " ('login', :n, false, now() - interval '1 day')"
            ),
            {"n": name},
        )
    await run_daily(os.environ["TEST_MAINT_DATABASE_URL"])
    async with owner_engine.connect() as conn:
        left = await scalar(
            conn, bound_text("select count(*) from auth_attempts where username = :n"), {"n": name}
        )
    assert left == 1
