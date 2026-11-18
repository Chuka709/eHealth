"""The app store review account (docs/STORE_RELEASE.md §4): one made-up kidney recipient with
records, reminders and six months of confirmed results, for Google Play / App Store reviewers.

    just seed-review                                  # the dev stack (demo admin from .env.demo)
    just seed-review https://beta.example.mn          # a beta server: an admin signs in by hand

Everything goes through the API as the account itself (validation, RLS, audit apply); the admin
only registers the account and mints its one-time activation token, as for any user. The
account is not a person, so the one running this sets its password (CLAUDE.md rule 2 is about
people's accounts); it goes to `.env.review` (git-ignored), never to the terminal or the logs,
and is pasted into the store's "App access" form. Re-running keeps the account and its records.
Retire it after review like any account (admin web: disable; a new password = a new token).
"""

import getpass
import os
import re
import secrets
import sys

import httpx
from fuzz_api import ROOT
from seed_demo import Admin, User, _activate, _kidney, _lab_history, _load, _ok

CREDENTIALS = ROOT / ".env.review"
# another name after a retired one: REVIEW_USERNAME=review_store2 just seed-review ...
USERNAME = os.environ.get("REVIEW_USERNAME", "review_store")
LOCAL = {"localhost", "127.0.0.1", "::1"}


def _admin(c: httpx.Client, local: bool) -> Admin:
    if local:
        demo = _load()  # `just seed-demo` made the dev admin
        if "DEMO_ADMIN_PASSWORD" not in demo:
            raise SystemExit("seed-review: run `just seed-demo` first (the dev admin)")
        return Admin(c, demo)
    sys.stderr.write("seed-review: sign in as a super admin of this server\n")
    body = {
        "username": input("admin username: ").strip(),
        "password": getpass.getpass("admin password: "),
        "totp_code": input("TOTP code: ").strip(),
    }
    return Admin.signed_in(c, _ok(c.post("/api/v1/admin/auth/login", json=body))["session_token"])


def _save(password: str, base: str) -> None:
    CREDENTIALS.write_text(
        "# Store review account (just seed-review). Never commit. Made-up data only.\n"
        f"REVIEW_BASE_URL={base}\nREVIEW_USERNAME={USERNAME}\nREVIEW_PASSWORD={password}\n",
        encoding="utf8",
        newline="\n",
    )


def main() -> int:
    if not re.fullmatch(r"review_[a-z0-9_]{1,25}", USERNAME):
        raise SystemExit("seed-review: REVIEW_USERNAME must start with review_")
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080"
    url = httpx.URL(base)
    local = url.host in LOCAL
    if not local and url.scheme != "https":
        raise SystemExit("seed-review: a server other than this machine must be https")
    saved = dict(
        line.split("=", 1)
        for line in (
            CREDENTIALS.read_text(encoding="utf8").splitlines() if CREDENTIALS.exists() else []
        )
        if "=" in line and not line.startswith("#")
    )
    if saved and saved.get("REVIEW_BASE_URL") != base:
        raise SystemExit(
            f"seed-review: {CREDENTIALS.name} belongs to another server - move it first"
        )
    fresh = "REVIEW_PASSWORD" not in saved
    password = saved.get("REVIEW_PASSWORD") or f"Review {secrets.token_urlsafe(12)} river"
    _save(password, base)  # the password exists before the account uses it
    with httpx.Client(base_url=base, timeout=30) as c:
        admin = _admin(c, local)
        try:
            created = _activate(c, admin, USERNAME, "Туршилт Хэрэглэгч", password)
        finally:
            if not local:  # the super admin session ends with the script (security review M3)
                c.post("/api/v1/admin/auth/logout", headers=admin.h)
        if fresh and not created:
            CREDENTIALS.unlink()  # a new password for an account that has another one
            raise SystemExit(
                f"seed-review: {USERNAME} exists but {CREDENTIALS.name} was missing - disable it "
                "in the admin web and run again with REVIEW_USERNAME=<a new review_ name>"
            )
        u = User(c, USERNAME, password)
        if created:
            u.consent()
            _kidney(u)
        pid = u.profile("Батболд Дорж")
        _lab_history(u, pid, 6)
    state = "created" if created else "kept"
    sys.stderr.write(f"seed-review: {USERNAME} {state}; credentials in {CREDENTIALS.name}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
