"""0006: admin sessions, TOTP replay, reasons, identity enrolment, lockout clearing and the
issuing admin using their own token (docs/04 §1, §6.1)."""

import hashlib
import secrets
import time
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.db.sql import bound_text
from tests.admin_support import open_admin_session, set_admin_context

from .conftest import as_user, make_user, scalar

pytestmark = pytest.mark.db

PEPPER = "test-pepper-0123456789"
ARGON = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"
NID = "УБ90010101"
ADMIN_IP = "203.0.113.7"


def _hash() -> str:
    return hashlib.sha256(secrets.token_bytes(16)).hexdigest()


def _step() -> int:
    return int(time.time()) // 30


async def _as_admin(admin_engine: AsyncEngine, session: str, sql: str, **p: Any) -> Any:
    async with admin_engine.connect() as conn, conn.begin():
        await set_admin_context(conn, session)
        return (await conn.execute(bound_text(sql), p)).all()  # type: ignore[arg-type]


async def _owner(owner_engine: AsyncEngine, sql: str, **p: Any) -> None:
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(bound_text(sql), p)  # type: ignore[arg-type]


async def _new_admin(owner_engine: AsyncEngine, role: str = "super_admin") -> UUID:
    admin = await make_user(owner_engine, role)
    await _owner(owner_engine, "update users set totp_secret_enc = '\\x01' where id = :a", a=admin)
    return admin


_NOW: Any = object()


async def _create_session(login_engine: AsyncEngine, admin: UUID, step: int | None = _NOW) -> str:
    token = _hash()
    async with login_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text("select admin_session_create(:a, :h, null, cast(:s as bigint))"),
            {"a": admin, "h": token, "s": _step() if step is _NOW else step},
        )
    return token


async def _pending_user(admin_engine: AsyncEngine, admin: UUID, *, nid: str | None) -> UUID:
    uid = uuid4()
    async with as_user(admin_engine, admin) as conn:
        await conn.execute(
            bound_text(
                "select admin_create_user(:id, :u, 'Бат', 'user', null, '1234', :nid, :pep)"
            ),
            {"id": uid, "u": f"n{uuid4().hex[:10]}", "nid": nid, "pep": PEPPER},
        )
    return uid


# --- admin_actor needs the acting admin's session, begun in this transaction ------------------


async def _forged(admin_engine: AsyncEngine, settings: dict[str, str], begin: str = "") -> None:
    async with admin_engine.connect() as conn, conn.begin():
        if begin:
            await set_admin_context(conn, begin)
        await conn.execute(
            bound_text(
                "select set_config('app.user_id', :a, true),"
                " set_config('app.admin_sid', case when :s = '' then"
                " current_setting('app.admin_sid', true) else :s end, true)"
            ),
            settings,
        )
        await conn.execute(bound_text("select admin_log_import(:h, 0)"), {"h": _hash()})


async def test_set_config_alone_never_acts_as_an_admin(
    owner_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    admin = await _new_admin(owner_engine)
    session = await open_admin_session(owner_engine, admin)
    async with owner_engine.connect() as conn:
        sid = await scalar(
            conn, bound_text("select id from admin_sessions where token_hash = :h"), {"h": session}
        )
    await _as_admin(admin_engine, session, "select admin_log_import(:h, 0)", h=_hash())
    # A session id learnt in one transaction is useless in the next one (no begin there).
    for settings in ({"a": str(admin), "s": ""}, {"a": str(admin), "s": str(sid)}):
        with pytest.raises(DBAPIError, match="admin not allowed"):
            await _forged(admin_engine, settings)


async def test_another_admins_session_does_not_act_for_me(
    owner_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    admin, other = await _new_admin(owner_engine), await _new_admin(owner_engine)
    other_session = await open_admin_session(owner_engine, other)
    with pytest.raises(DBAPIError, match="admin not allowed"):
        await _forged(admin_engine, {"a": str(admin), "s": ""}, begin=other_session)


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (
            "update admin_sessions set last_seen_at = now() - interval '16 minutes'"
            " where token_hash = :h",
            "idle",
        ),
        (
            "update admin_sessions set expires_at = now() - interval '1 second'"
            " where token_hash = :h",
            "expired",
        ),
        (
            "update users set account_status = 'disabled'"
            " where id = (select admin_id from admin_sessions where token_hash = :h)",
            "account_inactive",
        ),
    ],
)
async def test_idle_expired_or_inactive_sessions_end(
    owner_engine: AsyncEngine, admin_engine: AsyncEngine, change: str, reason: str
) -> None:
    admin = await _new_admin(owner_engine)
    session = await open_admin_session(owner_engine, admin)
    await _owner(owner_engine, change, h=session)
    async with admin_engine.connect() as conn, conn.begin():  # the API commits this
        await set_admin_context(conn, session)
        assert await scalar(conn, bound_text("select app_user_id()")) is None
    async with owner_engine.connect() as conn:
        stored = await scalar(
            conn,
            bound_text("select revoked_reason from admin_sessions where token_hash = :h"),
            {"h": session},
        )
    assert stored == reason


# --- sign-in (labtrack_admin_login) ------------------------------------------------------------


async def test_session_lifecycle(
    owner_engine: AsyncEngine, admin_engine: AsyncEngine, admin_login_engine: AsyncEngine
) -> None:
    admin = await _new_admin(owner_engine)
    token = await _create_session(admin_login_engine, admin)
    async with admin_engine.connect() as conn, conn.begin():
        row = (
            await conn.execute(bound_text("select * from admin_session_begin(:h)"), {"h": token})
        ).one()
        assert row.admin_id == admin
        await conn.execute(bound_text("select admin_log_import(:h, 0)"), {"h": _hash()})
    async with admin_engine.connect() as conn, conn.begin():
        await conn.execute(bound_text("select admin_session_end(:h)"), {"h": token})
    async with admin_engine.connect() as conn, conn.begin():
        gone = (
            await conn.execute(bound_text("select * from admin_session_begin(:h)"), {"h": token})
        ).all()
    assert gone == []


async def test_a_totp_step_is_accepted_once_and_only_near_now(
    owner_engine: AsyncEngine, admin_login_engine: AsyncEngine
) -> None:
    admin = await _new_admin(owner_engine)
    now = _step()
    await _create_session(admin_login_engine, admin, now)
    for step, message in (
        (now, "already used"),
        (now - 1, "already used"),
        (None, "invalid totp step"),
        (now + 5, "invalid totp step"),
        (9_000_000_000_000_000_000 // 1000, "invalid totp step"),
    ):
        with pytest.raises(DBAPIError, match=message):
            await _create_session(admin_login_engine, admin, step)
    await _create_session(admin_login_engine, admin, now + 1)


@pytest.mark.parametrize("kind", ["user", "no_totp", "disabled", "missing"])
async def test_only_active_admins_with_totp_get_sessions(
    owner_engine: AsyncEngine, admin_login_engine: AsyncEngine, kind: str
) -> None:
    if kind == "user":
        target = await make_user(owner_engine)
    elif kind == "missing":
        target = uuid4()
    else:
        target = await make_user(owner_engine, "super_admin")
        if kind == "disabled":
            await _owner(
                owner_engine,
                "update users set account_status = 'disabled', totp_secret_enc = '\\x01'"
                " where id = :a",
                a=target,
            )
    with pytest.raises(DBAPIError, match="admin not allowed"):
        await _create_session(admin_login_engine, target)


async def test_ten_failures_block_sessions_even_if_the_api_does_not(
    owner_engine: AsyncEngine, admin_login_engine: AsyncEngine
) -> None:
    admin = await _new_admin(owner_engine)
    async with owner_engine.connect() as conn:
        username = await scalar(
            conn, bound_text("select username from users where id = :a"), {"a": admin}
        )
    async with admin_login_engine.connect() as conn, conn.begin():
        for _ in range(10):
            await conn.execute(bound_text("select admin_login_failure(:u, null)"), {"u": username})
    with pytest.raises(DBAPIError, match="admin not allowed"):
        await _create_session(admin_login_engine, admin)


async def test_at_most_three_live_sessions(
    owner_engine: AsyncEngine, admin_login_engine: AsyncEngine
) -> None:
    admin = await _new_admin(owner_engine)
    now = _step()
    for step in (now - 1, now, now + 1):
        await _create_session(admin_login_engine, admin, step)
    await _owner(
        owner_engine, "update users set totp_last_step = :s - 2 where id = :a", s=now, a=admin
    )
    await _create_session(admin_login_engine, admin, now - 1)
    async with owner_engine.connect() as conn:
        live = await scalar(
            conn,
            bound_text(
                "select count(*) from admin_sessions where admin_id = :a and revoked_at is null"
            ),
            {"a": admin},
        )
    assert live == 3


@pytest.mark.parametrize(
    "sql",
    [
        "select * from admin_login_lookup('x')",
        "select admin_session_create(gen_random_uuid(), :h, null, 1)",
        "select admin_login_failure('x', null)",
    ],
)
async def test_admin_api_role_cannot_sign_in_by_itself(
    owner_engine: AsyncEngine, admin_engine: AsyncEngine, sql: str
) -> None:
    admin = await _new_admin(owner_engine)
    with pytest.raises(DBAPIError, match="permission denied"):
        async with as_user(admin_engine, admin) as conn:
            await conn.execute(bound_text(sql), {"h": _hash()})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "sql",
    [
        "select * from admin_session_begin('x')",
        "select admin_log_import('x', 1)",
        "select token_hash from admin_sessions",
        "select id from users",
    ],
)
async def test_sign_in_role_can_do_nothing_else(admin_login_engine: AsyncEngine, sql: str) -> None:
    with pytest.raises(DBAPIError, match="permission denied"):
        async with admin_login_engine.connect() as conn, conn.begin():
            await conn.execute(bound_text(sql))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "sql",
    [
        "select token_hash from admin_sessions",
        "update admin_sessions set revoked_at = null",
        "update users set totp_last_step = 1",
        "select totp_secret_enc from users",
    ],
)
async def test_admin_role_has_no_direct_access_to_admin_secrets(
    owner_engine: AsyncEngine, admin_engine: AsyncEngine, sql: str
) -> None:
    admin = await _new_admin(owner_engine)
    with pytest.raises(DBAPIError, match="permission denied"):
        async with as_user(admin_engine, admin) as conn:
            await conn.execute(bound_text(sql))  # type: ignore[arg-type]


async def test_admin_accounts_never_hold_user_sessions(
    owner_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    admin = await _new_admin(owner_engine)
    async with owner_engine.connect() as conn, conn.begin():
        username = await scalar(
            conn, bound_text("select username from users where id = :a"), {"a": admin}
        )
        # a user session an admin might hold from before 0006
        sid = await scalar(
            conn,
            bound_text(
                "insert into sessions (user_id, family_id, token_hash, expires_at,"
                " family_expires_at) values (:a, gen_random_uuid(), :h,"
                " now() + interval '1 day', now() + interval '1 day') returning id"
            ),
            {"a": admin, "h": _hash()},
        )
    async with app_engine.connect() as conn, conn.begin():
        assert (
            await conn.execute(bound_text("select * from auth_login_lookup(:u)"), {"u": username})
        ).all() == []
        assert (
            await scalar(
                conn, bound_text("select session_check(:s, :a, 0)"), {"s": sid, "a": admin}
            )
            is False
        )
        with pytest.raises(DBAPIError, match="account not active"):
            await conn.execute(
                bound_text(
                    "select * from session_create(:a, :h, null, 'web', null, false, null,"
                    " interval '1 day')"
                ),
                {"a": admin, "h": _hash()},
            )


@pytest.mark.parametrize(
    "sql",
    [
        "select * from admin_login_lookup('x')",
        "select admin_session_create(gen_random_uuid(), 'x', null, 1)",
        "select * from admin_session_begin('x')",
    ],
)
async def test_app_role_cannot_use_admin_sign_in(
    owner_engine: AsyncEngine, app_engine: AsyncEngine, sql: str
) -> None:
    me = await make_user(owner_engine)
    with pytest.raises(DBAPIError, match="permission denied"):
        async with as_user(app_engine, me) as conn:
            await conn.execute(bound_text(sql))  # type: ignore[arg-type]


# --- reasons, identity enrolment, lockout ------------------------------------------------------


async def test_reset_and_status_changes_need_a_reason_code(
    owner_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    admin = await _new_admin(owner_engine)
    user = await make_user(owner_engine)
    for reason in (None, "because the patient has hepatitis"):
        with pytest.raises(DBAPIError, match="reason required"):
            async with as_user(admin_engine, admin) as conn:
                await conn.execute(
                    bound_text("select admin_set_status(:u, 'locked', :r)"),
                    {"u": user, "r": reason},
                )
        with pytest.raises(DBAPIError, match="reason required"):
            async with as_user(admin_engine, admin) as conn:
                await conn.execute(
                    bound_text(
                        "select admin_issue_token(:u, 'admin_reset', 'sms', :h, null, :r, null)"
                    ),
                    {"u": user, "h": _hash(), "r": reason},
                )


async def test_status_change_checks_the_admin_first(
    owner_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    # Without an admin session nothing about the target is revealed (no 'target not allowed').
    async with admin_engine.connect() as conn, conn.begin():
        with pytest.raises(DBAPIError, match="admin not allowed"):
            await conn.execute(
                bound_text("select admin_set_status(gen_random_uuid(), 'locked', null)")
            )
    del owner_engine


async def test_support_cannot_lift_a_compromise_lock(
    owner_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    admin = await _new_admin(owner_engine)
    support = await _new_admin(owner_engine, "support")
    user, other = await make_user(owner_engine), await make_user(owner_engine)
    async with as_user(admin_engine, admin) as conn:
        await conn.execute(
            bound_text("select admin_set_status(:u, 'locked', 'suspected_compromise')"),
            {"u": user},
        )
        await conn.execute(
            bound_text("select admin_set_status(:u, 'locked', 'user_request')"), {"u": other}
        )
    with pytest.raises(DBAPIError, match="admin not allowed"):
        async with as_user(admin_engine, support) as conn:
            await conn.execute(
                bound_text("select admin_set_status(:u, 'active', 'identity_verified')"),
                {"u": user},
            )
    async with as_user(admin_engine, support) as conn:
        await conn.execute(
            bound_text("select admin_set_status(:u, 'active', 'identity_verified')"), {"u": other}
        )


async def test_identity_is_enrolled_once_and_the_user_is_told(
    owner_engine: AsyncEngine, admin_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    admin = await _new_admin(owner_engine)
    user = await _pending_user(admin_engine, admin, nid=None)
    async with as_user(admin_engine, admin) as conn:
        await conn.execute(
            bound_text("select admin_set_identity(:u, :n, :p)"), {"u": user, "n": NID, "p": PEPPER}
        )
    async with as_user(admin_engine, admin) as conn:
        ok = (
            await conn.execute(
                bound_text("select success from admin_identity_check(:u, :n, :p)"),
                {"u": user, "n": NID, "p": PEPPER},
            )
        ).scalar_one()
    assert ok is True
    with pytest.raises(DBAPIError, match="identity already set"):
        async with as_user(admin_engine, admin) as conn:
            await conn.execute(
                bound_text("select admin_set_identity(:u, 'УБ00000000', :p)"),
                {"u": user, "p": PEPPER},
            )
    async with as_user(app_engine, user) as conn:
        kinds = (await conn.execute(bound_text("select kind from notifications"))).scalars().all()
    assert "admin_action" in kinds


async def test_the_enrolling_admin_cannot_also_reset(
    owner_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    admin, second = await _new_admin(owner_engine), await _new_admin(owner_engine)
    user = await make_user(owner_engine)
    async with as_user(admin_engine, admin) as conn:
        await conn.execute(
            bound_text("select admin_set_identity(:u, :n, :p)"), {"u": user, "n": NID, "p": PEPPER}
        )

    async def reset_by(actor: UUID) -> None:
        async with as_user(admin_engine, actor) as conn:
            check = (
                await conn.execute(
                    bound_text("select check_id from admin_identity_check(:u, :n, :p)"),
                    {"u": user, "n": NID, "p": PEPPER},
                )
            ).scalar_one()
            await conn.execute(
                bound_text(
                    "select admin_issue_token(:u, 'admin_reset', 'sms', :h, :c,"
                    " 'forgot_password', '198.51.100.1')"
                ),
                {"u": user, "h": _hash(), "c": check},
            )

    with pytest.raises(DBAPIError, match="another admin must reset"):
        await reset_by(admin)
    await reset_by(second)


async def test_clearing_a_lockout_resets_the_failure_counts(
    owner_engine: AsyncEngine, admin_engine: AsyncEngine, admin_login_engine: AsyncEngine
) -> None:
    support = await _new_admin(owner_engine, "support")
    user = await make_user(owner_engine)
    async with owner_engine.connect() as conn, conn.begin():
        username = await scalar(
            conn, bound_text("select username from users where id = :u"), {"u": user}
        )
        for _ in range(6):
            await conn.execute(
                bound_text("select auth_record_failure('login', :u, null, null, false)"),
                {"u": username},
            )

    async def untrusted_failures() -> int:
        async with admin_login_engine.connect() as conn:
            row = (
                await conn.execute(
                    bound_text(
                        "select * from auth_failure_counts('login', :u, null, null,"
                        " interval '1 day')"
                    ),
                    {"u": username},
                )
            ).one()
        return int(row.by_username_untrusted)

    assert await untrusted_failures() == 6
    async with as_user(admin_engine, support) as conn:  # support may unlock
        await conn.execute(bound_text("select admin_clear_lockout(:u)"), {"u": user})
    assert await untrusted_failures() == 0


async def test_security_events_are_for_super_admins(
    owner_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    support = await _new_admin(owner_engine, "support")
    with pytest.raises(DBAPIError, match="admin not allowed"):
        async with as_user(admin_engine, support) as conn:
            await conn.execute(bound_text("select * from admin_security_events(10)"))


# --- docs/04 §6.1: the issuing admin uses the token --------------------------------------------


async def _issue_from(
    owner_engine: AsyncEngine, admin_engine: AsyncEngine, channel: str, admin_ip: str
) -> tuple[UUID, str]:
    admin = await _new_admin(owner_engine)
    session = await open_admin_session(owner_engine, admin)
    user = await _pending_user(admin_engine, admin, nid=None)
    token_hash = _hash()
    await _as_admin(
        admin_engine,
        session,
        "select admin_issue_token(:u, 'activation', :c, :h, null, null, cast(:ip as inet))",
        u=user,
        c=channel,
        h=token_hash,
        ip=admin_ip,
    )
    return user, token_hash


async def _consume(app_engine: AsyncEngine, token_hash: str, ip: str | None, admin: bool) -> str:
    async with app_engine.connect() as conn, conn.begin():
        status: str = await scalar(
            conn,
            bound_text("select status from activation_consume(:h, :pw, cast(:ip as inet), :adm)"),
            {"h": token_hash, "pw": ARGON, "ip": ip, "adm": admin},
        )
    return status


async def _events(owner_engine: AsyncEngine, user: UUID) -> list[str]:
    async with owner_engine.connect() as conn:
        rows = await conn.execute(
            bound_text(
                "select action from audit_logs where target_user_id = :u"
                " and action like 'security.%'"
            ),
            {"u": user},
        )
        return list(rows.scalars().all())


@pytest.mark.parametrize(
    ("channel", "ip", "admin_present", "expected", "event"),
    [
        ("sms", ADMIN_IP, False, "refused", "security.admin_token_self_use"),
        ("sms", "198.51.100.9", True, "refused", "security.admin_token_self_use"),
        ("in_person_qr", "198.51.100.9", True, "refused", "security.admin_token_self_use"),
        ("in_person_qr", ADMIN_IP, False, "ok", "security.admin_network_activation"),
        ("sms", "198.51.100.9", False, "ok", None),
    ],
)
async def test_the_issuing_admin_cannot_use_the_token(
    owner_engine: AsyncEngine,
    admin_engine: AsyncEngine,
    app_engine: AsyncEngine,
    channel: str,
    ip: str,
    admin_present: bool,
    expected: str,
    event: str | None,
) -> None:
    user, token_hash = await _issue_from(owner_engine, admin_engine, channel, ADMIN_IP)
    assert await _consume(app_engine, token_hash, ip, admin_present) == expected
    assert await _events(owner_engine, user) == ([event] if event else [])
    if expected == "refused":  # revoked: the real user needs a new token
        assert await _consume(app_engine, token_hash, "192.0.2.1", False) == "invalid"


async def test_ipv6_admin_network_is_matched_by_prefix(
    owner_engine: AsyncEngine, admin_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    _, h = await _issue_from(owner_engine, admin_engine, "sms", "2001:db8:1:2::10")
    assert await _consume(app_engine, h, "2001:db8:1:2:ffff::1", False) == "refused"


async def test_failed_activations_are_counted(
    owner_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    ip = f"192.0.2.{secrets.randbelow(200) + 20}"
    assert await _consume(app_engine, _hash(), ip, False) == "invalid"
    async with owner_engine.connect() as conn:
        n = await scalar(
            conn,
            bound_text(
                "select count(*) from auth_attempts where kind = 'activation'"
                " and ip = cast(:ip as inet) and not success"
            ),
            {"ip": ip},
        )
    assert n >= 1


async def test_locking_revokes_tokens_issued_before_the_lock(
    owner_engine: AsyncEngine, admin_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    admin, second = await _new_admin(owner_engine), await _new_admin(owner_engine)
    user = await _pending_user(admin_engine, admin, nid=NID)
    h = _hash()
    async with as_user(admin_engine, admin) as conn:
        await conn.execute(
            bound_text(
                "select admin_issue_token(:u, 'activation', 'in_person_qr', :h, null, null, null)"
            ),
            {"u": user, "h": h},
        )
    assert await _consume(app_engine, h, None, False) == "ok"
    async with as_user(admin_engine, second) as conn:
        check = (
            await conn.execute(
                bound_text("select check_id from admin_identity_check(:u, :n, :p)"),
                {"u": user, "n": NID, "p": PEPPER},
            )
        ).scalar_one()
        reset = _hash()
        await conn.execute(
            bound_text(
                "select admin_issue_token(:u, 'admin_reset', 'in_person_qr', :h, :c,"
                " 'lost_device', null)"
            ),
            {"u": user, "h": reset, "c": check},
        )
    async with as_user(admin_engine, admin) as conn:
        await conn.execute(
            bound_text("select admin_set_status(:u, 'locked', 'suspected_compromise')"),
            {"u": user},
        )
    assert await _consume(app_engine, reset, None, False) == "invalid"
    async with owner_engine.connect() as conn:
        status = await scalar(
            conn, bound_text("select account_status from users where id = :u"), {"u": user}
        )
    assert status == "locked"
