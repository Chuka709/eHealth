"""Load test of the dev stack with locust (`just load-test`; Phase 8.3, docs/LOAD_TEST.md).

Locust (MIT) runs from a uv tool environment on F:, as schemathesis does (k6 is AGPL - CLAUDE.md
rule 11). Steps:
  1. throwaway users the way `just fuzz-api` makes them (names `fzu` + 8 hex, so its cleanup
     disables them): activated, consents given, one profile with a twice-daily medicine;
     sign-ins are paced under the per-address limits (activation 10/min, login 20/min);
  2. locust, headless, with their refresh tokens (a temp file, deleted afterwards) - the home
     screen's reads, recording a dose, the timeline, the emergency card, now and then a small
     PDF upload;
  3. every throwaway account disabled with its sessions, however the run ended.
Prints locust's summary; the CSV goes to backend/.load-reports/. Passwords and tokens are random,
never printed and never on a command line. Dev only (a local target).
"""

import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fuzz_api import BASE, ROOT, _ok, cleanup, provision_user, require_local_target

USERS = int(os.environ.get("LOAD_USERS", "20"))
DURATION = os.environ.get("LOAD_DURATION", "3m")
SPAWN_RATE = os.environ.get("LOAD_SPAWN_RATE", "2")
REPORTS = ROOT / "backend" / ".load-reports"
LOCUSTFILE = Path(__file__).resolve().parent / "locustfile.py"
_UB = timezone(timedelta(hours=8))  # Ulaanbaatar, no DST (no tzdata needed on Windows)


def _user(c: httpx.Client) -> dict[str, str]:
    user, token = provision_user(c)
    password = f"Load {secrets.token_urlsafe(16)} цонх"
    _ok(c.post("/api/v1/auth/activate",
               json={"token": token, "username": user, "new_password": password}))  # fmt: skip
    time.sleep(3.5)  # login 20/min per address
    login = _ok(
        c.post(
            "/api/v1/auth/login",
            json={"username": user, "password": password, "platform": "android"},
        )
    )
    access = login["access_token"]  # fmt: skip
    h = {"Authorization": f"Bearer {access}"}
    versions = c.get("/api/v1/me/consents", headers=h).json()
    _ok(c.post("/api/v1/me/consents", headers=h, json={"items": [
        {"kind": s["kind"], "version": s["current_version"], "granted": True}
        for s in versions]}))  # fmt: skip
    # activation may already have made the user's own profile
    own = c.get("/api/v1/patients", headers=h).json()
    pid = own[0]["id"] if own else _ok(c.post("/api/v1/patients", headers=h, json={
        "full_name": "Ачаалал Тест", "relation": "self"}))["id"]  # fmt: skip
    start = (datetime.now(_UB).date() - timedelta(days=7)).isoformat()
    med = _ok(c.post(f"/api/v1/patients/{pid}/medications", headers=h, json={
        "client_id": str(uuid.uuid4()), "name": "Такролимус", "started_on": start,
        "regimen": {"client_id": str(uuid.uuid4()), "effective_from": start, "dose_unit": "mg",
                    "schedule": {"type": "daily",
                                 "times": [{"at": "08:00", "amount": "1"},
                                           {"at": "20:00", "amount": "1"}]}}}))["id"]  # fmt: skip
    # the run starts minutes later: each virtual user refreshes first (as the app on opening)
    return {"refresh": str(login["refresh_token"]), "patient": str(pid), "medication": str(med)}


def main() -> int:
    require_local_target()
    REPORTS.mkdir(exist_ok=True)
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    result = 1
    try:
        with httpx.Client(base_url=BASE, timeout=30) as c:
            users = []
            for i in range(USERS):
                users.append(_user(c))
                sys.stderr.write(f"\rusers ready: {i + 1}/{USERS}")
                time.sleep(3.5)  # activation 10/min per address
            sys.stderr.write("\n")
        Path(path).write_text(json.dumps(users), encoding="utf-8")
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        # 127.0.0.1: on Windows "localhost" tries ::1 first and every new connection waits ~2 s
        host = BASE.replace("localhost", "127.0.0.1")
        cmd = [
            "uv", "tool", "run", "--from", "locust>=2.32,<3", "locust", "-f", str(LOCUSTFILE),
            "--headless", "-u", str(USERS), "-r", SPAWN_RATE, "-t", DURATION, "--host", host,
            "--csv", str(REPORTS / stamp), "--only-summary",
        ]  # fmt: skip
        run = subprocess.run(  # noqa: S603 - fixed command, uv on PATH (as fuzz-api)
            cmd, cwd=ROOT, env={**os.environ, "LOAD_USERS_FILE": path}, check=False
        )
        result = run.returncode
    finally:
        Path(path).unlink(missing_ok=True)
        cleaned = cleanup()
    return result if cleaned else 1


if __name__ == "__main__":
    sys.exit(main())
