"""Property-based API fuzzing with schemathesis against the running dev stack (`just fuzz-api`).

Phase 1.12. Runs from the host (schemathesis lives in a uv tool environment on F:, not in the
API image): creates a throwaway super admin the way the web e2e does, uses it to register and
activate a throwaway user, then lets schemathesis generate requests from the OpenAPI schema:
  1. without credentials, every non-admin route;
  2. with that user's access token, every non-admin route except the ones that would end the
     test user's session or account mid-run (they have their own API tests).
Checks: no 5xx anywhere, responses match the schema. Afterwards the user is disabled and the
admin signed out. Passwords and TOTP secrets are random and never printed.
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
    compose = ["docker", "compose", "-f", "infra/docker-compose.yml", "--env-file", ".env"]
    subprocess.run(  # noqa: S603 - fixed command, values passed via the environment
        [
            *compose,
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


def _ok(r: httpx.Response) -> dict[str, object]:
    if r.status_code >= 300:  # noqa: PLR2004
        sys.exit(f"setup failed: {r.request.method} {r.request.url.path} -> {r.status_code}")
    return r.json() if r.content else {}


def _schemathesis(*extra: str, destructive: bool = False) -> int:
    # One exclusion regex: a second --exclude-path-regex replaces the first.
    exclude = f"^/api/v1/admin|{_DESTRUCTIVE}" if destructive else "^/api/v1/admin"
    cmd = [
        "uv", "tool", "run", "--from", "schemathesis==4.33.0", "schemathesis", "run",
        str(SCHEMA), "--url", BASE, "--checks", _CHECKS,
        "--exclude-path-regex", exclude, "--max-examples", os.environ.get("FUZZ_N", "25"),
        "--report", "junit", "--report-dir", str(REPORTS), *extra,
    ]  # fmt: skip
    # schemathesis prints Unicode; the Windows console default (cp1252) cannot encode it.
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    return subprocess.run(cmd, cwd=ROOT, env=env, check=False).returncode  # noqa: S603


def main() -> int:
    # Dev only: it creates a super admin through MIGRATION_DATABASE_URL and fuzzes the API.
    if httpx.URL(BASE).host not in {"localhost", "127.0.0.1", "::1"}:
        sys.exit("fuzz-api: refusing a non-local target")
    admin_user = f"fz{secrets.token_hex(4)}"
    admin_password = f"Fuzz {secrets.token_urlsafe(12)} нууц"
    secret = pyotp.random_base32(length=32)
    _create_admin(admin_user, admin_password, secret)

    user = f"fzu{secrets.token_hex(4)}"
    password = f"Fuzz {secrets.token_urlsafe(16)} цонх"
    with httpx.Client(base_url=BASE, timeout=30) as c:
        code = pyotp.TOTP(secret).at(time.time())
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

        try:
            anonymous = _schemathesis()
            signed_in = _schemathesis("-H", f"Authorization: Bearer {access}", destructive=True)
        finally:
            c.post(f"/api/v1/admin/users/{uid}/status", headers=admin,
                   json={"status": "disabled", "reason": "other"})  # fmt: skip
            c.post("/api/v1/admin/auth/logout", headers=admin)
    sys.stderr.write(f"anonymous run: exit {anonymous}; signed-in run: exit {signed_in}\n")
    return anonymous or signed_in


def _ok_list(r: httpx.Response) -> list[dict[str, str]]:
    if r.status_code != 200:  # noqa: PLR2004
        sys.exit(f"setup failed: {r.request.url.path} -> {r.status_code}")
    data: list[dict[str, str]] = r.json()
    return data


if __name__ == "__main__":
    sys.exit(main())
