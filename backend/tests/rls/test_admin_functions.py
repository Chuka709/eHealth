"""Admin and activation functions (0004): the admin can administer accounts but never take
one over, never change another admin, and never read patient data (docs/04 §1, §6)."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.db.sql import bound_text

from .conftest import as_user, make_user, scalar

pytestmark = pytest.mark.db

PEPPER = "test-pepper-0123456789"
ARGON = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"
NID = "УБ90010101"


def _token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    return raw, hashlib.sha256(raw.encode()).hexdigest()


async def _create(admin_engine: AsyncEngine, admin: UUID, *, nid: str | None = NID) -> UUID:
    async with as_user(admin_engine, admin) as conn:
        uid: UUID = await scalar(
            conn,
            bound_text(
                "select admin_create_user(gen_random_uuid(), :u, 'Бат', 'user', null, '1234',"
                " :nid, :pep)"
            ),
            {"u": f"n{uuid4().hex[:10]}", "nid": nid, "pep": PEPPER},
        )
    return uid


async def _check(
    admin_engine: AsyncEngine, admin: UUID, user: UUID, candidate: str
) -> tuple[int, bool]:
    async with as_user(admin_engine, admin) as conn:
        row = (
            await conn.execute(
                bound_text("select * from admin_identity_check(:u, :c, :p)"),
                {"u": user, "c": candidate, "p": PEPPER},
            )
        ).one()
    return int(row.check_id), bool(row.success)


async def _issue(
    admin_engine: AsyncEngine,
    admin: UUID,
    user: UUID,
    purpose: str,
    token_hash: str,
    check_id: int | None = None,
    channel: str = "in_person_qr",
) -> datetime:
    async with as_user(admin_engine, admin) as conn:
        expires: datetime = await scalar(
            conn,
            bound_text("select admin_issue_token(:u, :p, :c, :h, :ic, :r, cast(:ip as inet))"),
            {
                "u": user,
                "p": purpose,
                "c": channel,
                "h": token_hash,
                "ic": check_id,
                "r": "forgot_password" if purpose == "admin_reset" else None,
                "ip": "198.51.100.1",
            },
        )
    return expires


@pytest.fixture
async def admin(owner_engine: AsyncEngine) -> UUID:
    return await make_user(owner_engine, "super_admin")


# --- C1: no direct writes for the admin role -------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        bound_text("update users set password_hash = 'x'"),
        bound_text("update users set identity_check_hash = 'x'"),
        bound_text("update users set contact_phone_enc = 'x'"),
        bound_text("update users set role = 'super_admin'"),
        bound_text("update users set account_status = 'active'"),
        bound_text("insert into users (username, display_name) values ('evil1', 'E')"),
        bound_text(
            "insert into identity_checks (user_id, admin_id, success) values (null, null, true)"
        ),
        bound_text("update activation_tokens set expires_at = now()"),
        bound_text("update sessions set revoked_at = null"),
    ],
)
async def test_admin_role_has_no_direct_write_on_account_tables(
    admin_engine: AsyncEngine, admin: UUID, sql: object
) -> None:
    with pytest.raises(DBAPIError, match="permission denied"):
        async with as_user(admin_engine, admin) as conn:
            await conn.execute(sql)  # type: ignore[call-overload]


async def test_admin_cannot_read_token_or_identity_hashes(
    admin_engine: AsyncEngine, admin: UUID
) -> None:
    for sql in (
        bound_text("select token_hash from activation_tokens"),
        bound_text("select identity_check_hash from users"),
        bound_text("select contact_phone_enc from users"),
    ):
        with pytest.raises(DBAPIError, match="permission denied"):
            async with as_user(admin_engine, admin) as conn:
                await conn.execute(sql)


# --- full activation path ---------------------------------------------------------------------


async def test_new_account_is_activated_by_the_user_not_the_admin(
    app_engine: AsyncEngine, admin_engine: AsyncEngine, admin: UUID
) -> None:
    user = await _create(admin_engine, admin)
    raw, h = _token()
    expires = await _issue(admin_engine, admin, user, "activation", h)
    assert expires - datetime.now(UTC) <= timedelta(minutes=15)
    async with app_engine.connect() as conn, conn.begin():
        uid = await scalar(
            conn,
            bound_text("select user_id from activation_consume(:h, :pw, null, false)"),
            {"h": h, "pw": ARGON},
        )
    assert uid == user
    async with as_user(app_engine, user) as conn:
        status = await scalar(conn, bound_text("select account_status from users"))
        profiles = await scalar(conn, bound_text("select count(*) from patients"))
    assert (status, profiles) == ("active", 1)
    # single use
    async with app_engine.connect() as conn, conn.begin():
        again = await scalar(
            conn,
            bound_text("select status from activation_consume(:h, :pw, null, false)"),
            {"h": h, "pw": ARGON},
        )
    assert again == "invalid"
    assert raw  # the raw token only ever lives in the QR / SMS


async def test_admin_gets_no_access_to_the_self_profile(
    app_engine: AsyncEngine, admin_engine: AsyncEngine, admin: UUID
) -> None:
    await _create(admin_engine, admin)
    async with as_user(app_engine, admin) as conn:
        assert await scalar(conn, bound_text("select count(*) from patients")) == 0


async def test_activation_token_only_for_pending_accounts(
    owner_engine: AsyncEngine, admin_engine: AsyncEngine, admin: UUID
) -> None:
    active_user = await make_user(owner_engine)
    with pytest.raises(DBAPIError, match="already activated"):
        await _issue(admin_engine, admin, active_user, "activation", _token()[1])


async def test_activation_requires_an_argon2id_hash(
    app_engine: AsyncEngine, admin_engine: AsyncEngine, admin: UUID
) -> None:
    user = await _create(admin_engine, admin)
    h = _token()[1]
    await _issue(admin_engine, admin, user, "activation", h)
    with pytest.raises(DBAPIError, match="argon2id"):
        async with app_engine.connect() as conn, conn.begin():
            await conn.execute(
                bound_text("select * from activation_consume(:h, 'plaintext', null, false)"),
                {"h": h},
            )


# --- identity check and reset -------------------------------------------------------------------


async def test_identity_check_is_computed_by_the_database(
    admin_engine: AsyncEngine, admin: UUID
) -> None:
    user = await _create(admin_engine, admin)
    assert (await _check(admin_engine, admin, user, "УБ00000000"))[1] is False
    assert (await _check(admin_engine, admin, user, NID.lower()))[1] is True  # case-insensitive


async def test_identity_checks_are_rate_limited(admin_engine: AsyncEngine, admin: UUID) -> None:
    user = await _create(admin_engine, admin)
    for _ in range(5):
        await _check(admin_engine, admin, user, "УБ00000000")
    with pytest.raises(DBAPIError, match="limit reached"):
        await _check(admin_engine, admin, user, NID)


async def test_reset_needs_a_fresh_successful_check_of_the_same_user_by_the_same_admin(
    owner_engine: AsyncEngine, admin_engine: AsyncEngine, admin: UUID
) -> None:
    user, other = await _create(admin_engine, admin), await _create(admin_engine, admin)
    second_admin = await make_user(owner_engine, "super_admin")
    failed, _ = await _check(admin_engine, admin, user, "УБ00000000")
    other_ok, _ = await _check(admin_engine, admin, other, NID)
    for check_id, actor in ((None, admin), (failed, admin), (other_ok, admin)):
        with pytest.raises(DBAPIError, match="identity check is required"):
            await _issue(admin_engine, actor, user, "admin_reset", _token()[1], check_id, "sms")
    ok, _ = await _check(admin_engine, admin, user, NID)
    with pytest.raises(DBAPIError, match="identity check is required"):  # another admin's check
        await _issue(admin_engine, second_admin, user, "admin_reset", _token()[1], ok, "sms")
    async with owner_engine.connect() as conn, conn.begin():  # age the check past 10 minutes
        await conn.execute(
            bound_text(
                "update identity_checks set at = now() - interval '11 minutes' where id = :i"
            ),
            {"i": ok},
        )
    with pytest.raises(DBAPIError, match="identity check is required"):
        await _issue(admin_engine, admin, user, "admin_reset", _token()[1], ok, "sms")


async def test_reset_kills_the_old_password_and_every_session(
    owner_engine: AsyncEngine, app_engine: AsyncEngine, admin_engine: AsyncEngine, admin: UUID
) -> None:
    user = await _create(admin_engine, admin)
    h1 = _token()[1]
    await _issue(admin_engine, admin, user, "activation", h1)
    async with app_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text("select user_id from activation_consume(:h, :pw, null, false)"),
            {"h": h1, "pw": ARGON},
        )
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "insert into sessions (user_id, family_id, token_hash, expires_at)"
                " values (:u, gen_random_uuid(), :h, now() + interval '1 day')"
            ),
            {"u": user, "h": uuid4().hex},
        )
    # a different admin than the one who enrolled the national id at creation (0006)
    second = await make_user(owner_engine, "super_admin")
    check_id, ok = await _check(admin_engine, second, user, NID)
    assert ok
    expires = await _issue(admin_engine, second, user, "admin_reset", _token()[1], check_id, "sms")
    assert expires - datetime.now(UTC) <= timedelta(hours=24)
    async with owner_engine.connect() as conn:
        row = (
            await conn.execute(
                bound_text(
                    "select password_hash, token_version,"
                    " (select count(*) from sessions where user_id = u.id and revoked_at is null)"
                    " as live from users u where id = :u"
                ),
                {"u": user},
            )
        ).one()
    assert row.password_hash is None
    assert row.token_version >= 1
    assert row.live == 0
    async with as_user(app_engine, user) as conn:  # the user is told
        kinds = (await conn.execute(bound_text("select kind from notifications"))).scalars().all()
    assert "admin_reset" in kinds


# --- H3: no escalation among admins -----------------------------------------------------------


async def test_admins_cannot_target_other_admins_or_create_them(
    owner_engine: AsyncEngine, admin_engine: AsyncEngine, admin: UUID
) -> None:
    other_admin = await make_user(owner_engine, "super_admin")
    with pytest.raises(DBAPIError, match="target not allowed"):
        async with as_user(admin_engine, admin) as conn:
            await conn.execute(
                bound_text("select admin_set_status(:u, 'disabled', 'other')"), {"u": other_admin}
            )
    with pytest.raises(DBAPIError, match="CLI only"):
        async with as_user(admin_engine, admin) as conn:
            await conn.execute(
                bound_text(
                    "select admin_create_user(gen_random_uuid(), 'newboss', 'B', 'super_admin',"
                    " null, null, null, null)"
                )
            )


async def test_support_can_only_unlock(
    owner_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    support = await make_user(owner_engine, "support")
    user = await make_user(owner_engine)
    for status in ("disabled", "locked"):
        with pytest.raises(DBAPIError, match="admin not allowed"):
            async with as_user(admin_engine, support) as conn:
                await conn.execute(
                    bound_text("select admin_set_status(:u, :s, 'other')"), {"u": user, "s": status}
                )
    with pytest.raises(DBAPIError, match="admin not allowed"):
        async with as_user(admin_engine, support) as conn:
            await conn.execute(
                bound_text(
                    "select admin_create_user(gen_random_uuid(), 'x1x', 'X', 'user',"
                    " null, null, null, null)"
                )
            )


async def test_admin_functions_need_an_active_admin_in_context(
    owner_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    plain = await make_user(owner_engine)
    for actor in (None, plain):
        with pytest.raises(DBAPIError, match="admin not allowed"):
            async with as_user(admin_engine, actor) as conn:
                await conn.execute(
                    bound_text(
                        "select admin_create_user(gen_random_uuid(), 'x2x', 'X', 'user',"
                        " null, null, null, null)"
                    )
                )


# --- H1: function ACLs --------------------------------------------------------------------------


async def test_no_security_definer_function_is_executable_by_public(
    owner_engine: AsyncEngine,
) -> None:
    async with owner_engine.connect() as conn:
        leaked = (
            (
                await conn.execute(
                    bound_text(
                        "select p.proname from pg_proc p"
                        " join pg_namespace n on n.oid = p.pronamespace"
                        " where n.nspname = 'public' and p.prosecdef and exists ("
                        "  select 1 from aclexplode("
                        "    coalesce(p.proacl, acldefault('f', p.proowner)))"
                        "  a where a.grantee = 0 and a.privilege_type = 'EXECUTE')"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert leaked == []


@pytest.mark.parametrize(
    "sql",
    [
        bound_text("select admin_set_status(gen_random_uuid(), 'locked', 'other')"),
        bound_text("select admin_reveal_phone(gen_random_uuid())"),
        bound_text("select revoke_user_sessions(gen_random_uuid(), 'disabled')"),
        bound_text("select admin_audit(gen_random_uuid(), 'admin.x', null, null)"),
    ],
)
async def test_app_role_cannot_call_admin_functions(
    owner_engine: AsyncEngine, app_engine: AsyncEngine, sql: object
) -> None:
    me = await make_user(owner_engine)
    with pytest.raises(DBAPIError, match="permission denied"):
        async with as_user(app_engine, me) as conn:
            await conn.execute(sql)  # type: ignore[call-overload]


# --- M4: sharing only with active users/doctors -----------------------------------------------


async def test_profiles_cannot_be_shared_with_admins_or_pending_accounts(
    owner_engine: AsyncEngine, app_engine: AsyncEngine, admin_engine: AsyncEngine, admin: UUID
) -> None:
    from .conftest import grant, make_patient  # noqa: PLC0415

    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    pending = await _create(admin_engine, admin)
    for target in (admin, pending):
        with pytest.raises(DBAPIError, match="row-level security"):
            await grant(app_engine, owner, patient, target, "viewer", direct=True)


async def test_consents_cannot_be_backdated(
    owner_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    me = await make_user(owner_engine)
    with pytest.raises(DBAPIError, match="permission denied"):
        async with as_user(app_engine, me) as conn:
            await conn.execute(
                bound_text(
                    "insert into consents (user_id, kind, version, granted, created_at)"
                    " values (:u, 'terms', '1', true, '2020-01-01')"
                ),
                {"u": me},
            )
