"""/auth API end to end against the real database (docs/04 §1, §6)."""

import asyncio
import hashlib
import secrets

import pytest
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.db.sql import bound_text

from .conftest import PASSWORD, ClientFactory, login_body, make_active_user

pytestmark = pytest.mark.db

NEW_PASSWORD = "Тэрэлжийн хад 1987 намар шар"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _login(c: AsyncClient, username: str, **kw: object) -> Response:
    return await c.post("/api/v1/auth/login", json=login_body(username, **kw))  # type: ignore[arg-type]


# --- login ---------------------------------------------------------------------------------


async def test_login_returns_tokens_and_me_works(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    _, username = await make_active_user(owner_engine)
    async with client_from() as c:
        r = await _login(c, username)
        assert r.status_code == 200
        body = r.json()
        assert body["token_type"] == "bearer"
        assert body["device_token"]  # first login from this device
        me = await c.get("/api/v1/auth/me", headers=_auth(body["access_token"]))
    assert me.status_code == 200
    assert me.json()["username"] == username


async def test_wrong_password_and_unknown_user_look_identical(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    _, username = await make_active_user(owner_engine)
    async with client_from() as c:
        wrong = await _login(c, username, password="definitely wrong")
        unknown = await _login(c, "nobody.here", password="definitely wrong")
    assert wrong.status_code == unknown.status_code == 401
    assert (
        wrong.json()
        == unknown.json()
        == {
            "code": "auth.invalid_credentials",
            "message_key": "error.auth.invalid_credentials",
        }
    )


async def test_validation_errors_never_echo_the_password(client_from: ClientFactory) -> None:
    async with client_from() as c:
        r = await c.post(
            "/api/v1/auth/login",
            json={"username": "X!", "password": "SECRET-VALUE", "platform": "android"},
        )
    assert r.status_code == 422
    assert "SECRET-VALUE" not in r.text


async def test_pending_and_disabled_accounts_cannot_log_in(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    uid, username = await make_active_user(owner_engine)
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text("update users set account_status = 'disabled' where id = :u"), {"u": uid}
        )
    async with client_from() as c:
        r = await _login(c, username)
    assert r.status_code == 401
    assert r.json()["code"] == "auth.invalid_credentials"


# --- lockout -------------------------------------------------------------------------------


async def test_five_failures_from_one_address_lock_that_address(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    _, username = await make_active_user(owner_engine)
    async with client_from("198.51.100.1") as c:
        for _ in range(5):
            assert (await _login(c, username, password="wrong-wrong")).status_code == 401
        locked = await _login(c, username)  # even the right password
    assert locked.status_code == 429
    assert int(locked.headers["Retry-After"]) > 0
    async with client_from("198.51.100.2") as other:  # another address is unaffected
        assert (await _login(other, username)).status_code == 200


async def test_rotating_addresses_blocks_untrusted_devices_but_not_a_trusted_one(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    _, username = await make_active_user(owner_engine)
    async with client_from("192.0.2.200") as c:
        device_token = (await _login(c, username)).json()["device_token"]
    for i in range(10):  # attacker: a new IP per attempt
        async with client_from(f"192.0.2.{i + 1}") as c:
            await _login(c, username, password="guess-guess")
    async with client_from("192.0.2.50") as c:
        assert (await _login(c, username)).status_code == 429  # new device: blocked
        trusted = await _login(c, username, device_token=device_token)
    assert trusted.status_code == 200  # the owner's phone still works


async def test_unknown_usernames_lock_the_same_way(client_from: ClientFactory) -> None:
    name = f"ghost{secrets.token_hex(4)}"
    async with client_from("198.51.100.77") as c:
        for _ in range(5):
            await _login(c, name, password="whatever-1")
        assert (await _login(c, name, password="whatever-1")).status_code == 429


# --- refresh rotation ----------------------------------------------------------------------


async def test_refresh_rotates_and_reuse_kills_the_family(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    _, username = await make_active_user(owner_engine)
    async with client_from() as c:
        first = (await _login(c, username)).json()
        second = await c.post(
            "/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}
        )
        assert second.status_code == 200
        new = second.json()
        assert new["refresh_token"] != first["refresh_token"]
        await asyncio.sleep(0)  # (grace covers truly concurrent retries; see next test)
        async with owner_engine.connect() as conn, conn.begin():  # the old token is now "stolen"
            await conn.execute(
                bound_text(
                    "update sessions set revoked_at = now() - interval '1 minute'"
                    " where token_hash = :h"
                ),
                {"h": hashlib.sha256(first["refresh_token"].encode()).hexdigest()},
            )
        reuse = await c.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
        assert reuse.status_code == 401
        # ... and the legitimate newer token died with the family
        after = await c.post("/api/v1/auth/refresh", json={"refresh_token": new["refresh_token"]})
        assert after.status_code == 401
        assert (
            await c.get("/api/v1/auth/me", headers=_auth(new["access_token"]))
        ).status_code == 401


async def test_concurrent_refresh_within_grace_does_not_log_the_user_out(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    _, username = await make_active_user(owner_engine)
    async with client_from() as c:
        token = (await _login(c, username)).json()["refresh_token"]
        a, b = await asyncio.gather(
            c.post("/api/v1/auth/refresh", json={"refresh_token": token}),
            c.post("/api/v1/auth/refresh", json={"refresh_token": token}),
        )
        assert a.status_code == b.status_code == 200
        for r in (a, b):
            again = await c.post(
                "/api/v1/auth/refresh", json={"refresh_token": r.json()["refresh_token"]}
            )
            assert again.status_code == 200


# --- revocation takes effect immediately ---------------------------------------------------


async def test_logout_and_disable_invalidate_access_tokens_at_once(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    uid, username = await make_active_user(owner_engine)
    async with client_from() as c:
        s1 = (await _login(c, username)).json()
        s2 = (await _login(c, username)).json()
        await c.post("/api/v1/auth/logout", json={"refresh_token": s1["refresh_token"]})
        assert (
            await c.get("/api/v1/auth/me", headers=_auth(s1["access_token"]))
        ).status_code == 401
        assert (
            await c.get("/api/v1/auth/me", headers=_auth(s2["access_token"]))
        ).status_code == 200
        async with owner_engine.connect() as conn, conn.begin():
            await conn.execute(
                bound_text("update users set account_status = 'disabled' where id = :u"),
                {"u": uid},
            )
        assert (
            await c.get("/api/v1/auth/me", headers=_auth(s2["access_token"]))
        ).status_code == 401


async def test_admin_reset_is_reported_to_the_old_device(
    owner_engine: AsyncEngine, admin_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    uid, username = await make_active_user(owner_engine)
    admin, _ = await make_active_user(owner_engine, role="super_admin")
    pepper = "test-pepper-0123456789"
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "update users set identity_check_hash ="
                " crypt('УБ90010101' || :p, gen_salt('bf', 4)) where id = :u"
            ),
            {"p": pepper, "u": uid},
        )
    async with client_from() as c:
        old = (await _login(c, username)).json()
        async with admin_engine.connect() as conn, conn.begin():
            await conn.execute(
                bound_text("select set_config('app.user_id', :a, true)"), {"a": str(admin)}
            )
            check = (
                await conn.execute(
                    bound_text("select * from admin_identity_check(:u, 'УБ90010101', :p)"),
                    {"u": uid, "p": pepper},
                )
            ).one()
            raw = secrets.token_urlsafe(32)
            await conn.execute(
                bound_text("select admin_issue_token(:u, 'admin_reset', 'sms', :h, :c)"),
                {"u": uid, "h": hashlib.sha256(raw.encode()).hexdigest(), "c": check.check_id},
            )
        r = await c.post("/api/v1/auth/refresh", json={"refresh_token": old["refresh_token"]})
        assert r.json()["code"] == "auth.admin_reset"
        assert (await _login(c, username)).status_code == 401  # the old password is gone
        act = await c.post(
            "/api/v1/auth/activate", json={"token": raw, "new_password": NEW_PASSWORD}
        )
        assert act.status_code == 204
        assert (await _login(c, username, password=NEW_PASSWORD)).status_code == 200


# --- activation and password change --------------------------------------------------------


async def test_activation_enforces_the_password_policy(client_from: ClientFactory) -> None:
    async with client_from() as c:
        weak = await c.post(
            "/api/v1/auth/activate", json={"token": "x" * 43, "new_password": "password123"}
        )
        bogus = await c.post(
            "/api/v1/auth/activate", json={"token": "x" * 43, "new_password": NEW_PASSWORD}
        )
    assert weak.status_code == 422
    assert weak.json()["code"].startswith("password.")
    assert bogus.status_code == 400
    assert bogus.json()["code"] == "auth.activation_invalid"


async def test_password_change_signs_out_other_devices(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    _, username = await make_active_user(owner_engine)
    async with client_from() as c:
        phone = (await _login(c, username)).json()
        tablet = (await _login(c, username)).json()
        wrong = await c.post(
            "/api/v1/auth/password",
            headers=_auth(phone["access_token"]),
            json={"current_password": "nope-nope-nope", "new_password": NEW_PASSWORD},
        )
        assert wrong.status_code == 401
        ok = await c.post(
            "/api/v1/auth/password",
            headers=_auth(phone["access_token"]),
            json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        )
        assert ok.status_code == 204
        # the tablet is signed out; the phone keeps its session (after a refresh)
        assert (
            await c.post("/api/v1/auth/refresh", json={"refresh_token": tablet["refresh_token"]})
        ).status_code == 401
        renewed = await c.post(
            "/api/v1/auth/refresh", json={"refresh_token": phone["refresh_token"]}
        )
        assert renewed.status_code == 200
        assert (await _login(c, username, password=NEW_PASSWORD)).status_code == 200


async def test_sessions_list_and_revoke_own_only(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    _, alice = await make_active_user(owner_engine)
    _, bob = await make_active_user(owner_engine)
    async with client_from() as c:
        a1 = (await _login(c, alice)).json()
        a2 = (await _login(c, alice)).json()
        b1 = (await _login(c, bob)).json()
        listed = (await c.get("/api/v1/auth/sessions", headers=_auth(a1["access_token"]))).json()
        assert len(listed) == 2
        assert sum(s["current"] for s in listed) == 1
        other = next(s["id"] for s in listed if not s["current"])
        bob_sessions = (
            await c.get("/api/v1/auth/sessions", headers=_auth(b1["access_token"]))
        ).json()
        stolen = await c.delete(
            f"/api/v1/auth/sessions/{bob_sessions[0]['id']}", headers=_auth(a1["access_token"])
        )
        assert stolen.status_code == 404
        assert (
            await c.delete(f"/api/v1/auth/sessions/{other}", headers=_auth(a1["access_token"]))
        ).status_code == 204
        assert (
            await c.get("/api/v1/auth/me", headers=_auth(a2["access_token"]))
        ).status_code == 401


# --- hardening from the commit review ----------------------------------------------------


async def test_grace_allows_one_sibling_only_and_dies_with_the_session(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    _, username = await make_active_user(owner_engine)
    async with client_from() as c:
        old = (await _login(c, username)).json()["refresh_token"]
        rotated = await c.post("/api/v1/auth/refresh", json={"refresh_token": old})
        assert rotated.status_code == 200
        sibling = await c.post("/api/v1/auth/refresh", json={"refresh_token": old})
        assert sibling.status_code == 200  # the concurrent retry
        third = await c.post("/api/v1/auth/refresh", json={"refresh_token": old})
        assert third.status_code == 401  # a second reuse is theft: family revoked
        for r in (rotated, sibling):
            dead = await c.post(
                "/api/v1/auth/refresh", json={"refresh_token": r.json()["refresh_token"]}
            )
            assert dead.status_code == 401


async def test_grace_does_not_survive_a_logout(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    _, username = await make_active_user(owner_engine)
    async with client_from() as c:
        stolen = (await _login(c, username)).json()["refresh_token"]
        fresh = (await c.post("/api/v1/auth/refresh", json={"refresh_token": stolen})).json()
        await c.post("/api/v1/auth/logout", json={"refresh_token": fresh["refresh_token"]})
        late = await c.post("/api/v1/auth/refresh", json={"refresh_token": stolen})
    assert late.status_code == 401


async def test_parallel_guesses_cannot_exceed_the_lockout(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    _, username = await make_active_user(owner_engine)
    async with client_from("198.51.100.200") as c:
        results = await asyncio.gather(
            *(_login(c, username, password=f"guess-{i:04d}") for i in range(15))
        )
    verified = sum(r.status_code == 401 for r in results)
    assert verified <= 5, verified  # the rest were refused before any password check
    assert all(r.status_code in {401, 429} for r in results)


async def test_current_password_check_is_rate_limited(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    _, username = await make_active_user(owner_engine)
    async with client_from() as c:
        access = (await _login(c, username)).json()["access_token"]
        codes = []
        for i in range(6):
            r = await c.post(
                "/api/v1/auth/password",
                headers=_auth(access),
                json={"current_password": f"wrong-{i}-pass", "new_password": NEW_PASSWORD},
            )
            codes.append(r.status_code)
    assert codes[:5] == [401] * 5
    assert codes[5] == 429
