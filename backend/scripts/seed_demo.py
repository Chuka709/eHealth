"""Persistent demo accounts and records on the DEV stack (`just seed-demo`), for manual checks
and the fast emulator flows (`just e2e-mobile-fast`) - no new account per test run.

Everything goes through the API as the account itself (validation and RLS apply), except the
admin, created like `just create-admin`. Fictional people only - never real PHI.

Credentials: one shared password for the demo users, the admin's password and TOTP secret,
and a fresh activation token for `demo_pending` - kept in `.env.demo` at the repo root
(git-ignored: `.env.*`), never printed. Re-running keeps the accounts and their records; it
only mints a new token for `demo_pending`. `--reset` retires every demo account (disabled and
renamed, as nothing PHI-bearing is ever hard-deleted here) and seeds them anew.

Accounts (username - what it is for):
  demo_kidney  - kidney recipient: transplant (exact date), 3 medicines in "home" mode with
                 reminders, yesterday's doses recorded, vitals, allergy, contacts, appointments,
                 a question; shares with demo_carer (caregiver alerts after 30 min)
  demo_liver   - liver recipient: month-only date, a "local"-mode medicine, a stay in Seoul
  demo_carer   - caregiver of demo_kidney (accepted), with an own profile and nothing else
  demo_parent  - a parent: own profile and a child's profile with a kidney transplant
  demo_new     - signed up and consented, nothing recorded (onboarding and empty states)
  demo_pending - registered by the admin, not activated (the activation flow)
  demo_admin   - super admin (password + TOTP)
"""

import argparse
import secrets
import subprocess
import sys
import time
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pyotp
from fuzz_api import BASE, COMPOSE, ROOT, _create_admin, require_local_target

CREDENTIALS = ROOT / ".env.demo"
UB = ZoneInfo("Asia/Ulaanbaatar")
USERS = ("demo_kidney", "demo_liver", "demo_carer", "demo_parent", "demo_new")


def _sql(query: str) -> str:
    out = subprocess.run(  # noqa: S603 - fixed command, dev database only
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
        input=query,
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def _load() -> dict[str, str]:
    if not CREDENTIALS.exists():
        return {}
    lines = CREDENTIALS.read_text(encoding="utf8").splitlines()
    pairs = (line.split("=", 1) for line in lines if "=" in line and not line.startswith("#"))
    return dict(pairs)


def _save(values: dict[str, str]) -> None:
    lines = ["# Demo accounts on the dev stack (just seed-demo). Never commit, never real PHI."]
    lines += [f"{k}={v}" for k, v in sorted(values.items())]
    CREDENTIALS.write_text("\n".join(lines) + "\n", encoding="utf8")


def _ok(r: httpx.Response) -> Any:
    if r.status_code >= 300:  # noqa: PLR2004
        # status and error code only: a body could echo what was sent
        code = r.json().get("code") if r.headers.get("content-type", "").startswith("app") else ""
        raise SystemExit(
            f"seed-demo: {r.request.method} {r.request.url.path} -> {r.status_code} {code}"
        )
    return r.json() if r.content else None


def _today() -> date:
    return datetime.now(UB).date()


def _cid() -> str:
    return str(uuid.uuid4())


def _ub(day: date, hhmm: str) -> str:
    h, m = (int(x) for x in hhmm.split(":"))
    return datetime(day.year, day.month, day.day, h, m, tzinfo=UB).astimezone(UTC).isoformat()


class Admin:
    def __init__(self, c: httpx.Client, creds: dict[str, str]) -> None:
        if "DEMO_ADMIN_PASSWORD" not in creds:
            creds["DEMO_ADMIN_PASSWORD"] = f"Demo {secrets.token_urlsafe(12)} нууц"
            creds["DEMO_ADMIN_TOTP"] = pyotp.random_base32(length=32)
            _create_admin("demo_admin", creds["DEMO_ADMIN_PASSWORD"], creds["DEMO_ADMIN_TOTP"])
        totp = pyotp.TOTP(creds["DEMO_ADMIN_TOTP"])
        login = {"username": "demo_admin", "password": creds["DEMO_ADMIN_PASSWORD"]}
        r = c.post("/api/v1/admin/auth/login", json={**login, "totp_code": totp.now()})
        if r.status_code == 401:  # noqa: PLR2004 - a code is used once: a run in the same step
            time.sleep(31 - time.time() % 30)
            r = c.post("/api/v1/admin/auth/login", json={**login, "totp_code": totp.now()})
        session = _ok(r)["session_token"]
        self.c, self.h = c, {"Authorization": f"Bearer {session}"}

    def register(self, username: str, name: str) -> str | None:
        """The account's id, or None if it already exists (kept as it is)."""
        r = self.c.post(
            "/api/v1/admin/users", json={"username": username, "display_name": name}, headers=self.h
        )
        if r.status_code == 409:  # noqa: PLR2004
            return None
        return str(_ok(r)["id"])

    def activation_token(self, user_id: str) -> str:
        link = _ok(
            self.c.post(
                f"/api/v1/admin/users/{user_id}/tokens",
                json={"purpose": "activation", "channel": "in_person_qr"},
                headers=self.h,
            )
        )["link"]
        return str(link).split("#", 1)[1]


_CLIENT_ID_KINDS = {"allergies", "contacts", "appointments", "questions", "events"}


class User:
    def __init__(self, c: httpx.Client, username: str, password: str) -> None:
        r = _ok(
            c.post(
                "/api/v1/auth/login",
                json={"username": username, "password": password, "platform": "android"},
            )
        )
        self.c, self.h = c, {"Authorization": f"Bearer {r['access_token']}"}

    def get(self, path: str) -> Any:
        return _ok(self.c.get(f"/api/v1{path}", headers=self.h))

    def post(self, path: str, body: dict[str, Any]) -> Any:
        # health records are created with the phone's own id (a retried create finds its row)
        if path.rsplit("/", 1)[-1] in _CLIENT_ID_KINDS and "client_id" not in body:
            body = {**body, "client_id": _cid()}
        return _ok(self.c.post(f"/api/v1{path}", json=body, headers=self.h))

    def put(self, path: str, body: dict[str, Any]) -> Any:
        return _ok(self.c.put(f"/api/v1{path}", json=body, headers=self.h))

    def consent(self, *, caregiver: bool = False, patient_id: str | None = None) -> None:
        current = {i["kind"]: i["current_version"] for i in self.get("/me/consents")}
        kinds = ["terms", "privacy", "sensitive_data"] + (
            ["caregiver_sharing"] if caregiver else []
        )
        items = [{"kind": k, "version": current[k], "granted": True} for k in kinds if k in current]
        # a child's profile: the parent's consents given for it (Q9)
        extra = {"patient_id": patient_id} if patient_id else {}
        self.post("/me/consents", {"items": items, **extra})

    def profile(self, name: str) -> str:
        own = [p for p in self.get("/patients") if p["relation"] == "self"]
        if own:
            return str(own[0]["id"])
        return str(
            self.post("/patients", {"full_name": name, "relation": "self", "sex": "unknown"})["id"]
        )

    def medicine(
        self, pid: str, name: str, times: dict[str, str], unit: str = "mg", **extra: Any
    ) -> str:
        body = {
            "client_id": _cid(),
            "name": name,
            "reminders_enabled": True,
            "started_on": (_today() - timedelta(days=60)).isoformat(),
            "regimen": {
                "client_id": _cid(),
                "effective_from": (_today() - timedelta(days=60)).isoformat(),
                "dose_unit": unit,
                "schedule": {
                    "type": "daily",
                    "times": [{"at": t, "amount": a} for t, a in times.items()],
                },
            },
            **extra,
        }
        return str(self.post(f"/patients/{pid}/medications", body)["id"])


def _activate(c: httpx.Client, admin: Admin, username: str, name: str, password: str) -> bool:
    """True when the account was created now (its records are to be seeded)."""
    uid = admin.register(username, name)
    if uid is None:
        return False
    token = admin.activation_token(uid)
    _ok(
        c.post(
            "/api/v1/auth/activate",
            json={"token": token, "username": username, "new_password": password},
        )
    )
    return True


def _kidney(u: User) -> None:
    pid = u.profile("Батболд Дорж")
    t = u.post(
        f"/patients/{pid}/transplants",
        {
            "client_id": _cid(),
            "organ": "kidney",
            "transplant_date": "2023-05-12",
            "date_precision": "day",
            "country": "MN",
            "city": "Улаанбаатар",
            "hospital": "Улсын нэгдүгээр төв эмнэлэг",
            "donor_type": "living_related",
            "donor_relation": "ах",
            "recipient_blood_type": "A+",
            "graft_status": "functioning",
        },
    )
    tac = u.medicine(
        pid,
        "Такролимус",
        {"08:00": "2", "20:00": "1.5"},
        catalog_code="TACROLIMUS",
        strength="1 мг",
        form="капсул",
        transplant_id=t["id"],
    )
    myc = u.medicine(
        pid, "Микофенолат мофетил", {"08:00": "500", "20:00": "500"}, transplant_id=t["id"]
    )
    u.medicine(pid, "Преднизолон", {"08:00": "5"})
    yesterday = _today() - timedelta(days=1)
    for med, at, status in (
        (tac, "08:00", "taken"),
        (myc, "08:00", "taken"),
        (tac, "20:00", "taken"),
        (myc, "20:00", "skipped"),
    ):
        scheduled = _ub(yesterday, at)
        u.post(
            f"/patients/{pid}/intakes",
            {
                "client_id": _cid(),
                "medication_id": med,
                "scheduled_at": scheduled,
                "status": status,
                **({"taken_at": scheduled} if status == "taken" else {}),
            },
        )
    for days_ago, sys_, dia, weight in ((2, "128", "82", "71.4"), (1, "124", "80", "71.2")):
        u.post(
            f"/patients/{pid}/vitals",
            {
                "client_id": _cid(),
                "measured_at": _ub(_today() - timedelta(days=days_ago), "07:30"),
                "items": [
                    {"kind": "bp_systolic", "value": sys_},
                    {"kind": "bp_diastolic", "value": dia},
                    {"kind": "pulse", "value": "72"},
                ],
            },
        )
        # one kind per reading, except blood pressure (with its pulse)
        u.post(
            f"/patients/{pid}/vitals",
            {
                "client_id": _cid(),
                "measured_at": _ub(_today() - timedelta(days=days_ago), "07:35"),
                "items": [{"kind": "weight", "value": weight}],
            },
        )
    u.post(f"/patients/{pid}/allergies", {"substance": "Пенициллин", "reaction": "Тууралт"})
    u.post(f"/patients/{pid}/contacts", {"name": "Сараа (эхнэр)", "phone": "+976 0000 0000"})
    u.post(
        f"/patients/{pid}/contacts",
        {
            "name": "Шилжүүлэн суулгалтын төв",
            "phone": "+976 7011 0000",
            "is_transplant_center": True,
        },
    )
    nxt = u.post(
        f"/patients/{pid}/appointments",
        {
            "kind": "lab",
            "title": "Такролимусын түвшин",
            "place": "УНТЭ, лаборатори",
            "scheduled_at": _ub(_today() + timedelta(days=3), "09:00"),
            "reminder_offsets_min": [1440, 120],
        },
    )
    u.post(
        f"/patients/{pid}/appointments",
        {
            "kind": "clinic_visit",
            "title": "Нефрологийн үзлэг",
            "scheduled_at": _ub(_today() - timedelta(days=20), "10:00"),
            "status": "done",
        },
    )
    u.post(
        f"/patients/{pid}/questions",
        {"text": "Шинжилгээний өмнө эмээ уух уу?", "appointment_id": nxt["id"]},
    )
    u.post(
        f"/patients/{pid}/events",
        {
            "kind": "hospitalization",
            "title": "Халдвар, хэвтэн эмчлүүлсэн",
            "started_on": "2024-02-03",
            "ended_on": "2024-02-09",
        },
    )


def _liver(u: User) -> None:
    pid = u.profile("Оюун Ганбат")
    u.post(
        f"/patients/{pid}/transplants",
        {
            "client_id": _cid(),
            "organ": "liver",
            "transplant_date": "2024-03-01",
            "date_precision": "month",
            "country": "KR",
            "hospital": "Asan Medical Center",
            "donor_type": "deceased_dbd",
        },
    )
    u.medicine(
        pid,
        "Такролимус",
        {"09:00": "1", "21:00": "1"},
        catalog_code="TACROLIMUS",
        reminder_timezone_mode="local",
    )
    u.post(
        f"/patients/{pid}/timezone",
        {
            "client_id": _cid(),
            "timezone": "Asia/Seoul",
            "effective_at": datetime.now(UTC).isoformat(),
        },
    )


def _parent(u: User) -> None:
    u.profile("Энхтуяа Бат")
    child = u.post(
        "/patients",
        {"full_name": "Тэмүүлэн", "relation": "child", "sex": "male", "birth_date": "2015-06-01"},
    )
    u.consent(patient_id=child["id"])
    u.post(
        f"/patients/{child['id']}/transplants",
        {
            "client_id": _cid(),
            "organ": "kidney",
            "transplant_date": "2022-01-01",
            "date_precision": "year",
            "country": "IN",
            "hospital": "Medanta",
            "donor_type": "living_related",
        },
    )


_RETIRE_SQL = """
with r as (
  update users set account_status = 'disabled', token_version = token_version + 1,
    username = username || '_old' || substr(md5(random()::text), 1, 6)
  where username ~ '^demo_(kidney|liver|carer|parent|new|pending)$'
  returning id)
select count(*) from r;
"""


def _retire() -> None:
    n = _sql(_RETIRE_SQL)
    sys.stderr.write(f"seed-demo: retired {n} demo account(s)\n")


def _require_dev_stack() -> None:
    """The writes go through the compose stack's superuser and migration role, past RLS: the
    running API must say it is the dev environment (a localhost URL alone does not prove it)."""
    out = subprocess.run(  # noqa: S603 - fixed command
        [*COMPOSE, "exec", "-T", "api", "printenv", "ENVIRONMENT"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0 or out.stdout.strip() != "dev":
        raise SystemExit("seed-demo: the running stack is not ENVIRONMENT=dev - refusing")


def main() -> int:
    require_local_target()
    _require_dev_stack()
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="retire the demo accounts first")
    args = parser.parse_args()
    if args.reset:
        _retire()
    creds = _load()
    creds.setdefault("DEMO_PASSWORD", f"Demo {secrets.token_urlsafe(12)} lake")
    password = creds["DEMO_PASSWORD"]
    _save(creds)  # the password exists before any account uses it
    with httpx.Client(base_url=BASE, timeout=30) as c:
        admin = Admin(c, creds)
        _save(creds)
        names = {
            "demo_kidney": "Батболд",
            "demo_liver": "Оюун",
            "demo_carer": "Сараа",
            "demo_parent": "Энхтуяа",
            "demo_new": "Шинэ хэрэглэгч",
        }
        created = {u: _activate(c, admin, u, n, password) for u, n in names.items()}
        users = {u: User(c, u, password) for u in names}
        for name, u in users.items():
            if created[name]:
                u.consent(caregiver=name == "demo_kidney")
        if created["demo_kidney"]:
            _kidney(users["demo_kidney"])
        if created["demo_liver"]:
            _liver(users["demo_liver"])
        if created["demo_parent"]:
            _parent(users["demo_parent"])
        if created["demo_new"]:
            users["demo_new"].profile("Шинэ хэрэглэгч")
        if created["demo_carer"] or created["demo_kidney"]:
            owner = users["demo_kidney"]
            pid = owner.profile("Батболд Дорж")
            users["demo_carer"].profile("Сараа Бат")
            owner.post(f"/patients/{pid}/caregiver-invitations", {"username": "demo_carer"})
            for inv in users["demo_carer"].get("/me/caregiver-invitations"):
                users["demo_carer"].post(
                    "/me/caregiver-invitations/respond",
                    {"invitation_id": inv["id"], "accept": True},
                )
            users["demo_carer"].put(
                f"/patients/{pid}/caregiver-alerts",
                {"missed_dose_after_min": 30, "critical_result": False},
            )
        # demo_pending: registered, never activated - a fresh token on every run
        uid = admin.register("demo_pending", "Идэвхжүүлээгүй")
        if uid is None:
            uid = _sql("select id from users where username = 'demo_pending';")
        creds["DEMO_PENDING_TOKEN"] = admin.activation_token(uid)
        _save(creds)
    made = [u for u, v in created.items() if v]
    sys.stderr.write(
        f"seed-demo: ready ({len(made)} new, {len(names) - len(made)} kept); "
        f"credentials in {CREDENTIALS.name}\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
