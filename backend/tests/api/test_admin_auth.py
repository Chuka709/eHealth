"""Admin sign-in (password + TOTP), sessions, network allowlist and the create-admin CLI."""

import asyncio
import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.admin.cli import create_admin, run
from labtrack.core.security import hash_password
from labtrack.core.totp import PERIOD, code_at, new_secret
from labtrack.db.sql import bound_text
from labtrack.keys import get_key_provider

from .conftest import PASSWORD, ClientFactory, login_body, make_active_user

pytestmark = pytest.mark.db

OFFICE = "10.20.0.5"


def _now_step() -> int:
    return int(datetime.now(UTC).timestamp()) // PERIOD


async def make_admin(role: str = "super_admin") -> tuple[str, str]:
    """An admin as the CLI creates it; returns (username, totp secret)."""
    username = f"adm{uuid4().hex[:10]}"
    secret = new_secret()
    await create_admin(
        os.environ["MIGRATION_DATABASE_URL"],
        get_key_provider(),
        username=username,
        display_name="Админ",
        role=role,
        password_hash=hash_password(PASSWORD),
        totp_secret=secret,
    )
    return username, secret


async def admin_login(
    c: AsyncClient, username: str, secret: str, *, step: int | None = None, password: str = PASSWORD
) -> tuple[int, dict[str, object]]:
    r = await c.post(
        "/api/v1/admin/auth/login",
        json={
            "username": username,
            "password": password,
            "totp_code": code_at(secret, _now_step() if step is None else step),
        },
    )
    return r.status_code, r.json()


def bearer(token: object) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_sign_in_me_and_sign_out(client_from: ClientFactory) -> None:
    username, secret = await make_admin()
    async with client_from(OFFICE) as c:
        status, body = await admin_login(c, username, secret)
        assert status == 200
        token = body["session_token"]
        me = await c.get("/api/v1/admin/auth/me", headers=bearer(token))
        assert me.status_code == 200
        assert me.json()["role"] == "super_admin"
        assert (await c.post("/api/v1/admin/auth/logout", headers=bearer(token))).status_code == 204
        assert (await c.get("/api/v1/admin/auth/me", headers=bearer(token))).status_code == 401


async def test_every_failure_looks_the_same(client_from: ClientFactory) -> None:
    username, secret = await make_admin()
    async with client_from(OFFICE) as c:
        wrong_code = await admin_login(c, username, secret, step=_now_step() - 5)
        wrong_password = await admin_login(c, username, secret, password="Буруу нууц үг 2026!")
        unknown = await admin_login(c, f"nobody{uuid4().hex[:6]}", secret)
    for status, body in (wrong_code, wrong_password, unknown):
        assert status == 401
        assert body == {
            "code": "auth.invalid_credentials",
            "message_key": "error.auth.invalid_credentials",
        }


async def test_user_accounts_cannot_use_admin_sign_in(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    _, username = await make_active_user(owner_engine)
    async with client_from(OFFICE) as c:
        status, _ = await admin_login(c, username, new_secret())
    assert status == 401


async def test_a_totp_code_cannot_be_replayed(client_from: ClientFactory) -> None:
    username, secret = await make_admin()
    step = _now_step()
    async with client_from(OFFICE) as c:
        assert (await admin_login(c, username, secret, step=step))[0] == 200
        assert (await admin_login(c, username, secret, step=step))[0] == 401


async def test_admin_sign_in_locks_after_repeated_failures(client_from: ClientFactory) -> None:
    username, secret = await make_admin()
    async with client_from(OFFICE) as c:
        for _ in range(5):
            assert (await admin_login(c, username, secret, password="Буруу 2026 нууц!"))[0] == 401
        status, body = await admin_login(c, username, secret)
    assert (status, body["code"]) == (429, "auth.locked")


async def test_admin_surface_is_hidden_outside_the_allowlist(client_from: ClientFactory) -> None:
    username, secret = await make_admin()
    async with client_from("203.0.113.50") as c:
        status, body = await admin_login(c, username, secret)
    assert (status, body["code"]) == (404, "not_found")


async def test_idle_admin_session_ends(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    username, secret = await make_admin()
    async with client_from(OFFICE) as c:
        token = (await admin_login(c, username, secret))[1]["session_token"]
        async with owner_engine.connect() as conn, conn.begin():
            await conn.execute(
                bound_text(
                    "update admin_sessions set last_seen_at = now() - interval '16 minutes'"
                    " where admin_id = (select id from users where username = :u)"
                ),
                {"u": username},
            )
        assert (await c.get("/api/v1/admin/auth/me", headers=bearer(token))).status_code == 401


async def test_admins_cannot_sign_in_to_the_user_api(client_from: ClientFactory) -> None:
    username, secret = await make_admin()
    async with client_from(OFFICE) as c:
        r = await c.post("/api/v1/auth/login", json=login_body(username))
        assert r.status_code == 401
        token = (await admin_login(c, username, secret))[1]["session_token"]
        # an admin session token is not a user token (CLAUDE.md 2a)
        assert (await c.get("/api/v1/me", headers=bearer(token))).status_code == 401


# Routes anyone may call without a user token (sign-in, activation, health).
_ANONYMOUS = {
    "/api/v1/healthz",
    "/api/v1/readyz",
    "/api/v1/auth/login",
    "/api/v1/auth/activate",
    "/api/v1/auth/refresh",
    "/api/v1/auth/logout",
    # a share link's viewer has no account: the link's own session, never a user token (0041)
    "/api/v1/share/open",
    "/api/v1/share/profile",
    "/api/v1/share/record",
    "/api/v1/share/close",
}
# A well-formed value per path parameter type, so the request reaches the auth check.
_PATH_SAMPLES = {"uuid": "00000000-0000-0000-0000-000000000000", "integer": "1", "string": "x"}


async def test_an_admin_token_opens_no_user_route(client_from: ClientFactory) -> None:
    """CLAUDE.md 2a for every user route, taken from the OpenAPI schema, so future PHI routes
    are covered the day they are added: an admin session token is refused (401), not served."""
    from labtrack.main import create_app  # noqa: PLC0415

    paths = create_app().openapi()["paths"]
    username, secret = await make_admin()
    async with client_from(OFFICE) as c:
        token = (await admin_login(c, username, secret))[1]["session_token"]
        checked = 0
        for path, operations in paths.items():
            if path.startswith("/api/v1/admin") or path in _ANONYMOUS:
                continue
            for method, operation in operations.items():
                url = path
                for p in operation.get("parameters", []):
                    if p["in"] == "path":
                        sample = _PATH_SAMPLES[p["schema"].get("format", p["schema"]["type"])]
                        url = url.replace(f"{{{p['name']}}}", sample)
                assert "{" not in url, (method, path)
                r = await c.request(method.upper(), url, headers=bearer(token), json={})
                assert r.status_code == 401, (method, path, r.status_code)
                checked += 1
    assert checked >= 10  # the user API is really there


async def test_stored_totp_secret_is_encrypted_and_bound_to_its_row(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    username, secret = await make_admin()
    other, other_secret = await make_admin()
    async with owner_engine.connect() as conn, conn.begin():
        blob = (
            await conn.execute(
                bound_text("select totp_secret_enc from users where username = :u"),
                {"u": username},
            )
        ).scalar_one()
        assert secret.encode() not in bytes(blob)
        # move one admin's secret onto another row: it must not decrypt there
        await conn.execute(
            bound_text("update users set totp_secret_enc = :b where username = :u"),
            {"b": blob, "u": other},
        )
    async with client_from(OFFICE) as c:
        assert (await admin_login(c, other, secret))[0] == 401
        assert (await admin_login(c, other, other_secret))[0] == 401


# --- create-admin CLI ----------------------------------------------------------------------------


def _cli(username: str, answers: list[str], secrets_: list[str]) -> tuple[int, str]:
    out: list[str] = []
    asked = iter(answers)
    hidden = iter(secrets_)
    seen_secret: list[str] = []

    def ask(prompt: str) -> str:
        if prompt.startswith("Code"):
            key = next(line for line in out if "manual key:" in line).split("manual key:")[1]
            seen_secret.append(key.split()[0])
            return code_at(seen_secret[0], _now_step())
        return next(asked)

    code = run(
        os.environ["MIGRATION_DATABASE_URL"],
        username,
        "support",
        ask=ask,
        ask_secret=lambda _: next(hidden),
        out=out.append,
    )
    return code, "".join(out)


async def test_cli_creates_an_admin(owner_engine: AsyncEngine) -> None:
    username = f"cli{uuid4().hex[:8]}"
    code, output = await asyncio.to_thread(_cli, username, ["Дэмжлэг"], [PASSWORD, PASSWORD])
    assert code == 0, output
    async with owner_engine.connect() as conn:
        row = (
            await conn.execute(
                bound_text(
                    "select role, account_status, password_hash is not null as has_pw"
                    " from users where username = :u"
                ),
                {"u": username},
            )
        ).one()
    assert (row.role, row.account_status, row.has_pw) == ("support", "active", True)
    again, _ = await asyncio.to_thread(_cli, username, ["Дэмжлэг"], [PASSWORD, PASSWORD])
    assert again == 1  # never overwrites an existing account


@pytest.mark.parametrize(
    ("passwords", "reason"),
    [([PASSWORD, PASSWORD + "x"], "differ"), (["password12", "password12"], "rejected")],
)
async def test_cli_refuses_bad_passwords(passwords: list[str], reason: str) -> None:
    code, output = await asyncio.to_thread(_cli, f"cli{uuid4().hex[:8]}", ["Х"], passwords)
    assert code == 1
    assert reason in output


async def test_admin_role_value_is_checked() -> None:
    with pytest.raises(ValueError, match="role"):
        await create_admin(
            os.environ["MIGRATION_DATABASE_URL"],
            get_key_provider(),
            username="x" + uuid4().hex[:8],
            display_name="X",
            role="user",
            password_hash=hash_password(PASSWORD),
            totp_secret=new_secret(),
        )


async def test_cli_unlocks_a_locked_out_admin(client_from: ClientFactory) -> None:
    from labtrack.admin.cli import unlock_admin  # noqa: PLC0415

    username, secret = await make_admin()
    async with client_from(OFFICE) as c:
        for _ in range(5):
            await admin_login(c, username, secret, password="Буруу 2026 нууц!")
        assert (await admin_login(c, username, secret))[0] == 429
        assert await unlock_admin(os.environ["MIGRATION_DATABASE_URL"], username)
        assert (await admin_login(c, username, secret))[0] == 200
