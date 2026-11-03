"""Property-based API fuzzing with schemathesis against the running dev stack (`just fuzz-api`).

Phase 1.12. Runs from the host (schemathesis lives in a uv tool environment on F:, not in the
API image): creates a throwaway super admin the way the web e2e does, uses it to register and
activate a throwaway user, then lets schemathesis generate requests from the OpenAPI schema:
  1. without credentials, every non-admin route;
  2. with that user's access token, every non-admin route except the ones that would end the
     test user's session or account mid-run (they have their own API tests).
Checks: no 5xx anywhere, responses match the schema. Afterwards, however the run ended, every
throwaway fuzz account (this run's and any left by an interrupted one) is disabled with all its
sessions and tokens revoked, directly in the database. Passwords, TOTP secrets and tokens are
random, never printed and never on a command line.
"""

import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pyotp

ROOT = Path(__file__).resolve().parents[2]
BASE = os.environ.get("FUZZ_BASE_URL", "http://localhost:8080")
SCHEMA = ROOT / "packages" / "shared" / "openapi.json"
REPORTS = ROOT / "backend" / ".fuzz-reports"
SIGNED_IN_CONFIG = ROOT / "backend" / "scripts" / "fuzz-signed-in.toml"
COMPOSE = ["docker", "compose", "-f", "infra/docker-compose.yml", "--env-file", ".env"]

# Throwaway names: admins `fz` + 8 hex, users `fzu` + 8 hex. Nothing else matches.
_CLEANUP_SQL = """
begin;
create temp table fz on commit drop as
  select id from users where username ~ '^fzu?[0-9a-f]{8}$' and account_status <> 'disabled';
update users set account_status = 'disabled', token_version = token_version + 1
  where id in (select id from fz);
update sessions set revoked_at = now(), revoked_reason = 'disabled'
  where revoked_at is null and user_id in (select id from fz);
update admin_sessions set revoked_at = now(), revoked_reason = 'account_inactive'
  where revoked_at is null and admin_id in (select id from fz);
update activation_tokens set revoked_at = now()
  where used_at is null and revoked_at is null and user_id in (select id from fz);
select count(*) from fz;
commit;
"""

# Ends the test user's session or account, or changes its password: covered by API tests.
_DESTRUCTIVE = (
    "^/api/v1/(me/delete|me/report-unwanted-admin-action|auth/password|auth/logout"
    "|auth/sessions/\\{session_id\\})$"
)
_CHECKS = "not_a_server_error,response_schema_conformance"


def _create_admin(username: str, password: str, secret: str) -> None:
    script = "\n".join(
        [
            "import asyncio, os",
            "from labtrack.admin.cli import create_admin",
            "from labtrack.core.security import hash_password",
            "from labtrack.keys import get_key_provider",
            "asyncio.run(create_admin(os.environ['MIGRATION_DATABASE_URL'], get_key_provider(),",
            "  username=os.environ['FZ_USER'], display_name='Fuzz', role='super_admin',",
            "  password_hash=hash_password(os.environ['FZ_PASSWORD']),",
            "  totp_secret=os.environ['FZ_SECRET']))",
        ]
    )
    subprocess.run(  # noqa: S603 - fixed command, values passed via the environment
        [
            *COMPOSE,
            "run",
            "--rm",
            "-e",
            "FZ_USER",
            "-e",
            "FZ_PASSWORD",
            "-e",
            "FZ_SECRET",
            "migrate",
            "python",
            "-c",
            script,
        ],
        cwd=ROOT,
        env={**os.environ, "FZ_USER": username, "FZ_PASSWORD": password, "FZ_SECRET": secret},
        check=True,
        stdout=subprocess.DEVNULL,
    )


def _cleanup() -> bool:
    """Disable every fuzz account still enabled, as the database superuser: an admin cannot
    disable another admin through the API, and a run cut short never reaches the API steps."""
    out = subprocess.run(  # noqa: S603 - fixed command and SQL
        [
            *COMPOSE,
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "postgres",
            "-d",
            "labtrack",
            "-v",
            "ON_ERROR_STOP=1",
            "-qtA",
        ],
        cwd=ROOT,
        input=_CLEANUP_SQL,
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        sys.stderr.write("fuzz-api: CLEANUP FAILED - disable the fz* accounts by hand\n")
        return False
    sys.stderr.write(f"fuzz-api: disabled {out.stdout.strip()} throwaway account(s)\n")
    return True


def _ok(r: httpx.Response) -> dict[str, object]:
    if r.status_code >= 300:  # noqa: PLR2004
        sys.exit(f"setup failed: {r.request.method} {r.request.url.path} -> {r.status_code}")
    return r.json() if r.content else {}


def _schemathesis(access_token: str | None = None) -> int:
    # One exclusion regex: a second --exclude-path-regex replaces the first. Signed in, the
    # routes that would end the test user's session are left out too.
    exclude = "^/api/v1/admin" if access_token is None else f"^/api/v1/admin|{_DESTRUCTIVE}"
    config = [] if access_token is None else ["--config-file", str(SIGNED_IN_CONFIG)]
    cmd = [
        "uv", "tool", "run", "--from", "schemathesis==4.33.0", "schemathesis", *config, "run",
        str(SCHEMA), "--url", BASE, "--checks", _CHECKS,
        "--exclude-path-regex", exclude, "--max-examples", os.environ.get("FUZZ_N", "25"),
        "--report", "junit", "--report-dir", str(REPORTS),
    ]  # fmt: skip
    # schemathesis prints Unicode; the Windows console default (cp1252) cannot encode it.
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    env.pop("FUZZ_ACCESS_TOKEN", None)
    if access_token is not None:
        env["FUZZ_ACCESS_TOKEN"] = access_token
    run = subprocess.run(  # noqa: S603
        cmd, cwd=ROOT, env=env, check=False, stdout=subprocess.PIPE, text=True, encoding="utf-8"
    )
    sys.stdout.buffer.write(run.stdout.encode("utf-8"))
    sys.stdout.flush()
    # 401 is a documented response, so a signed-in run whose header never applied would pass.
    if access_token is not None and "Authentication failed" in run.stdout:
        sys.stderr.write("fuzz-api: the signed-in run was not signed in\n")
        return 1
    return run.returncode


def main() -> int:
    # Dev only: it creates a super admin through MIGRATION_DATABASE_URL and fuzzes the API.
    if httpx.URL(BASE).host not in {"localhost", "127.0.0.1", "::1"}:
        sys.exit("fuzz-api: refusing a non-local target")
    result = 1
    try:
        result = _run()
    finally:
        cleaned = _cleanup()
    return result if cleaned else 1


def _run() -> int:
    admin_user = f"fz{secrets.token_hex(4)}"
    admin_password = f"Fuzz {secrets.token_urlsafe(12)} нууц"
    secret = pyotp.random_base32(length=32)
    _create_admin(admin_user, admin_password, secret)

    user = f"fzu{secrets.token_hex(4)}"
    password = f"Fuzz {secrets.token_urlsafe(16)} цонх"
    with httpx.Client(base_url=BASE, timeout=30) as c:
        code = pyotp.TOTP(secret).at(int(time.time()))
        session = _ok(
            c.post(
                "/api/v1/admin/auth/login",
                json={"username": admin_user, "password": admin_password, "totp_code": code},
            )
        )["session_token"]
        admin = {"Authorization": f"Bearer {session}"}
        uid = _ok(c.post("/api/v1/admin/users", json={"username": user, "display_name": "Fuzz"},
                         headers=admin))["id"]  # fmt: skip
        link = _ok(
            c.post(
                f"/api/v1/admin/users/{uid}/tokens",
                json={"purpose": "activation", "channel": "in_person_qr"},
                headers=admin,
            )
        )["link"]
        token = str(link).split("#", 1)[1]
        _ok(c.post("/api/v1/auth/activate",
                   json={"token": token, "username": user, "new_password": password}))  # fmt: skip
        access = _ok(
            c.post(
                "/api/v1/auth/login",
                json={"username": user, "password": password, "platform": "android"},
            )
        )["access_token"]
        bearer = {"Authorization": f"Bearer {access}"}
        versions = {s["kind"]: s["current_version"] for s in _ok_list(c.get(
            "/api/v1/me/consents", headers=bearer))}  # fmt: skip
        _ok(c.post("/api/v1/me/consents", headers=bearer, json={"items": [
            {"kind": k, "version": v, "granted": True} for k, v in versions.items()]}))  # fmt: skip

        anonymous = _schemathesis()
        signed_in = _schemathesis(str(access))
    sys.stderr.write(f"anonymous run: exit {anonymous}; signed-in run: exit {signed_in}\n")
    return anonymous or signed_in


def _ok_list(r: httpx.Response) -> list[dict[str, str]]:
    if r.status_code != 200:  # noqa: PLR2004
        sys.exit(f"setup failed: {r.request.url.path} -> {r.status_code}")
    data: list[dict[str, str]] = r.json()
    return data


if __name__ == "__main__":
    sys.exit(main())
