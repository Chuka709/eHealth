"""RLS and column privileges for accounts, sessions and the audit log (docs/03, docs/04 §6)."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import TextClause
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.db.sql import bound_text

from .conftest import as_user, make_patient, make_user, scalar

pytestmark = pytest.mark.db


async def test_users_are_not_enumerable(app_engine: AsyncEngine, admin_engine: AsyncEngine) -> None:
    me = await make_user(admin_engine)
    await make_user(admin_engine)
    async with as_user(app_engine, me) as conn:
        assert await scalar(conn, bound_text("select count(*) from users")) == 1


@pytest.mark.parametrize(
    "sql",
    [
        bound_text("select password_hash from users"),
        bound_text("select totp_secret_enc from users"),
        bound_text("select contact_phone_enc from users"),
        bound_text("select identity_check_hash from users"),
    ],
)
async def test_secret_columns_are_unreadable_by_the_app_role(
    app_engine: AsyncEngine, admin_engine: AsyncEngine, sql: TextClause
) -> None:
    me = await make_user(admin_engine)
    with pytest.raises(DBAPIError, match="permission denied"):
        async with as_user(app_engine, me) as conn:
            await conn.execute(sql)


async def test_admin_cannot_read_password_hash(admin_engine: AsyncEngine) -> None:
    with pytest.raises(DBAPIError, match="permission denied"):
        async with admin_engine.connect() as conn:
            await conn.execute(bound_text("select password_hash from users"))


@pytest.mark.parametrize(
    "sql",
    [
        bound_text("update users set role = 'super_admin' where id = :id"),
        bound_text("update users set account_status = 'active' where id = :id"),
        bound_text("update users set token_version = 0 where id = :id"),
        bound_text("update users set username = 'x' where id = :id"),
    ],
)
async def test_users_cannot_escalate_their_own_account(
    app_engine: AsyncEngine, admin_engine: AsyncEngine, sql: TextClause
) -> None:
    me = await make_user(admin_engine)
    with pytest.raises(DBAPIError, match="permission denied"):
        async with as_user(app_engine, me) as conn:
            await conn.execute(sql, {"id": me})


async def test_users_can_edit_harmless_profile_fields(
    app_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    me = await make_user(admin_engine)
    async with as_user(app_engine, me) as conn:
        r = await conn.execute(
            bound_text("update users set locale = 'en', emergency_card_unlocked = true")
        )
        assert r.rowcount == 1  # own row only


async def test_pending_activation_account_cannot_hold_a_password(admin_engine: AsyncEngine) -> None:
    async with admin_engine.connect() as conn, conn.begin():
        uid = await scalar(
            conn,
            bound_text("insert into users (username, display_name) values (:u, 'P') returning id"),
            {"u": f"p{uuid4().hex[:10]}"},
        )
    set_password = bound_text("update users set password_hash = 'x' where id = :id")
    async with admin_engine.connect() as conn:
        with pytest.raises(DBAPIError, match="users_pending_has_no_password"):
            await conn.execute(set_password, {"id": uid})


async def test_sessions_are_private_and_token_hash_is_unreadable(
    app_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    me = await make_user(admin_engine)
    with pytest.raises(DBAPIError, match="permission denied"):
        async with as_user(app_engine, me) as conn:
            await conn.execute(bound_text("select token_hash from sessions"))
    with pytest.raises(DBAPIError, match="permission denied"):
        async with as_user(app_engine, me) as conn:
            await conn.execute(
                bound_text(
                    "insert into sessions (user_id, family_id, token_hash, expires_at)"
                    " values (:u, gen_random_uuid(), 'h', now())"
                ),
                {"u": me},
            )


async def test_activation_tokens_are_admin_only(
    app_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    me = await make_user(admin_engine)
    with pytest.raises(DBAPIError, match="permission denied"):
        async with as_user(app_engine, me) as conn:
            await conn.execute(bound_text("select count(*) from activation_tokens"))


async def test_admin_reset_token_requires_an_identity_check(admin_engine: AsyncEngine) -> None:
    admin, user = await make_user(admin_engine, "super_admin"), await make_user(admin_engine)
    with pytest.raises(DBAPIError, match="reset_needs_identity_check"):
        async with admin_engine.connect() as conn, conn.begin():
            await conn.execute(
                bound_text(
                    "insert into activation_tokens (user_id, token_hash, purpose, channel,"
                    " issued_by, expires_at) values (:u, :h, 'admin_reset', 'sms', :a,"
                    " now() + interval '1 day')"
                ),
                {"u": user, "h": uuid4().hex, "a": admin},
            )


async def test_audit_actor_cannot_be_forged(
    app_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    me, victim = await make_user(admin_engine), await make_user(admin_engine)
    with pytest.raises(DBAPIError, match="permission denied"):
        async with as_user(app_engine, me) as conn:
            await conn.execute(
                bound_text(
                    "insert into audit_logs (actor_id, action, target_user_id)"
                    " values (:v, 'admin.password_reset', :v)"
                ),
                {"v": victim},
            )
    async with as_user(app_engine, me) as conn:
        # audit_write refuses admin.* actions and always records the real caller.
        await conn.execute(
            bound_text("select audit_write('admin.password_reset', 'user', null, null, null)")
        )
        await conn.execute(
            bound_text("select audit_write('profile.view', 'patient', 'x', null, null)")
        )
    async with as_user(app_engine, victim) as conn:
        assert await scalar(conn, bound_text("select count(*) from my_admin_actions()")) == 0


async def test_admin_actions_are_visible_to_their_target_only(
    app_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    admin, user, other = (
        await make_user(admin_engine, "super_admin"),
        await make_user(admin_engine),
        await make_user(admin_engine),
    )
    async with admin_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text("select admin_audit_write(:a, 'admin.unlock', :u, null, null)"),
            {"a": admin, "u": user},
        )
        # a non-admin id is rejected silently (nothing written)
        await conn.execute(
            bound_text("select admin_audit_write(:x, 'admin.unlock', :u, null, null)"),
            {"x": other, "u": user},
        )
    async with as_user(app_engine, user) as conn:
        assert await scalar(conn, bound_text("select count(*) from my_admin_actions()")) == 1
    async with as_user(app_engine, other) as conn:
        assert await scalar(conn, bound_text("select count(*) from my_admin_actions()")) == 0


async def test_audit_log_is_immutable_even_for_admin_and_maint(
    admin_engine: AsyncEngine, maint_engine: AsyncEngine
) -> None:
    for engine in (admin_engine, maint_engine):
        for sql in ("update audit_logs set action = 'x'", "delete from audit_logs"):
            with pytest.raises(DBAPIError, match="permission denied"):
                async with engine.connect() as conn, conn.begin():
                    await conn.execute(bound_text(sql))


async def test_share_lookup_returns_only_an_id_for_an_exact_active_username(
    app_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    me, doctor = await make_user(admin_engine), await make_user(admin_engine, "doctor")
    async with admin_engine.connect() as conn:
        name = await scalar(
            conn, bound_text("select username from users where id = :id"), {"id": doctor}
        )
    async with as_user(app_engine, me) as conn:
        found: UUID | None = await scalar(
            conn, bound_text("select lookup_user_for_share(:n)"), {"n": name}
        )
        partial = await scalar(
            conn, bound_text("select lookup_user_for_share(:n)"), {"n": str(name)[:-2]}
        )
    assert found == doctor
    assert partial is None


async def test_definer_functions_are_not_callable_by_admin_or_maint(
    admin_engine: AsyncEngine, maint_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    patient = await make_patient(app_engine, await make_user(admin_engine))
    for engine in (admin_engine, maint_engine):
        with pytest.raises(DBAPIError, match="permission denied"):
            async with engine.connect() as conn:
                await conn.execute(bound_text("select can_read_patient(:p)"), {"p": patient})
