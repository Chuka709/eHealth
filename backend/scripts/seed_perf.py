"""Phase 6 DoD profile (docs/01: "3000 утга + 5 жилийн эмийн түүх"): one account, demo_perf,
with a kidney transplant five years back, three medicines with five years of dose changes and
of recorded doses, and 3000 confirmed lab values (250 typed-in reports of 12 tests, about
weekly). Reports go through the API as a person would (typed in, issues looked at, confirmed);
the 11 000 dose records are written in bulk by the database owner (the API records one dose
at a time). Made-up values, dev stack only. Re-running does nothing once the reports exist.

    uv run python scripts/seed_perf.py
"""

import random
import sys
import time
import uuid
from datetime import date, timedelta
from typing import Any

import httpx
from seed_demo import (
    BASE,
    Admin,
    User,
    _activate,
    _cid,
    _load,
    _require_dev_stack,
    _save,
    _sql,
    _today,
    _ub,
    require_local_target,
)

USERNAME = "demo_perf"
YEARS = 5
REPORTS = 250
# (code, printed name, unit, low, high, printed range)
TESTS: tuple[tuple[str, str, str, float, float, str], ...] = (
    ("CREA", "Креатинин", "мкмоль/л", 90, 140, "62-106"),
    ("UREA", "Мочевин", "ммоль/л", 4.5, 9.5, "2.5-7.5"),
    ("K", "Кали", "ммоль/л", 3.6, 5.6, "3.5-5.1"),
    ("NA", "Натри", "ммоль/л", 135, 145, "136-145"),
    ("HGB", "Гемоглобин", "г/л", 110, 150, "120-160"),
    ("PLT", "Тромбоцит", "10^9/л", 150, 350, "150-400"),
    ("ALT", "АЛТ", "U/L", 10, 50, "0-41"),
    ("AST", "АСТ", "U/L", 10, 45, "0-40"),
    ("GLU", "Глюкоз", "ммоль/л", 4.0, 7.5, "3.9-6.1"),
    ("TAC", "Такролимус", "нг/мл", 4.5, 11.5, "5-10"),
    ("CRP", "CRP", "мг/л", 0.5, 12, "0-5"),
    ("UA", "Шээсний хүчил", "мкмоль/л", 250, 450, "202-417"),
)


def _medicines(u: User, pid: str, start: str) -> list[str]:
    """Tacrolimus (a change every two months), mycophenolate, a prednisolone taper."""
    rnd = random.Random(11)  # noqa: S311 - made-up demo values, not a secret
    out = []
    for name, catalog, times, changes, step in (
        ("Такролимус", "TACROLIMUS", ("08:00", "20:00"), 30, 60),
        ("Микофенолат мофетил", None, ("08:00", "20:00"), 4, 300),
        ("Преднизолон", None, ("08:00",), 8, 90),
    ):
        body: dict[str, Any] = {
            "client_id": _cid(),
            "name": name,
            "reminders_enabled": False,
            "started_on": start,
            "regimen": {
                "client_id": _cid(),
                "effective_from": start,
                "dose_unit": "mg",
                "schedule": {"type": "daily", "times": [{"at": t, "amount": "2"} for t in times]},
            },
        }
        if catalog:
            body["catalog_code"] = catalog
        mid = str(u.post(f"/patients/{pid}/medications", body)["id"])
        day = _today() - timedelta(days=365 * YEARS)
        for _ in range(changes):
            day += timedelta(days=step)
            if day >= _today():
                break
            amount = str(rnd.choice(["1", "1.5", "2", "2.5", "3"]))
            u.post(
                f"/patients/{pid}/medications/{mid}/regimens",
                {
                    "client_id": _cid(),
                    "effective_from": day.isoformat(),
                    "dose_unit": "mg",
                    "schedule": {
                        "type": "daily",
                        "times": [{"at": t, "amount": amount} for t in times],
                    },
                },
            )
        out.append(mid)
    return out


def _intakes(pid: str, start: str, once_daily: str) -> None:
    """A dose record for each scheduled dose of every day until yesterday (one in 20 skipped)."""
    # both values are ours (a server UUID, an ISO date), checked again before they reach the SQL
    pid, start = str(uuid.UUID(pid)), date.fromisoformat(start).isoformat()
    once_daily = str(uuid.UUID(once_daily))
    _sql(
        "insert into medication_intakes (patient_id, medication_id, client_id, scheduled_at,"  # noqa: S608 - dev seed via psql, values checked above
        " taken_at, status)"
        " select m.patient_id, m.id, gen_random_uuid(), s.at,"
        " case when s.skip then null else s.at + interval '10 minutes' end,"
        " case when s.skip then 'skipped' else 'taken' end from medications m"
        " cross join lateral (select (d + t::time) at time zone 'Asia/Ulaanbaatar' as at,"
        " random() < 0.05 as skip"
        f" from generate_series(date '{start}', current_date - 1, interval '1 day') d,"
        f" unnest(case when m.id = '{once_daily}' then array['08:00']"
        " else array['08:00', '20:00'] end) t) s"
        f" where m.patient_id = '{pid}'"
        " on conflict do nothing;"
    )


def _send(u: User, method: str, path: str, body: dict[str, Any]) -> Any:
    """One API call; a 429 (the review write limit) waits and tries again."""
    while True:
        r = u.c.request(method, f"/api/v1{path}", json=body, headers=u.h)
        if r.status_code != 429:  # noqa: PLR2004 - HTTP 429
            r.raise_for_status()
            return r.json() if r.content else None
        time.sleep(float(r.headers.get("Retry-After", "5")))


def _reports(u: User, pid: str) -> None:
    rnd = random.Random(5)  # noqa: S311 - made-up demo values, not a secret
    first = _today() - timedelta(days=365 * YEARS - 30)
    every = (365 * YEARS - 40) / REPORTS
    tested = {t["test_code"]: t["results"] for t in u.get(f"/patients/{pid}/trends")}
    done = tested.get("CREA", 0)  # a run stopped half way goes on from there
    for n in range(REPORTS):
        if n < done:
            rnd.random()  # keep the same values for the rest
            continue
        day = first + timedelta(days=round(n * every))
        report = _send(
            u,
            "POST",
            f"/patients/{pid}/reports",
            {
                "lab_name": "Хувийн лаб" if n % 3 else "УНТЭ",
                "collected_at": _ub(day, "08:30"),
                "collected_precision": "minute",
                "results": [
                    {
                        "raw_name": name,
                        "raw_value": f"{rnd.uniform(lo, hi):.1f}",
                        "raw_unit": unit,
                        "ref_text": ref,
                        "test_code": code,
                    }
                    for code, name, unit, lo, hi, ref in TESTS
                ],
            },
        )
        for row in report["results"]:
            for issue in row["issues"]:
                if issue not in row["acknowledged"]:
                    _send(
                        u,
                        "PATCH",
                        f"/patients/{pid}/reports/{report['id']}/results/{row['id']}",
                        {"acknowledge": [issue]},
                    )
        _send(u, "POST", f"/patients/{pid}/reports/{report['id']}/confirm", {})
        if n % 25 == 0:
            sys.stdout.write(f"  {n}/{REPORTS} reports" + chr(10))


def main() -> int:
    require_local_target()
    _require_dev_stack()
    creds = _load()
    password = creds["DEMO_PASSWORD"]
    with httpx.Client(base_url=BASE, timeout=60) as c:
        admin = Admin(c, creds)
        _save(creds)
        created = _activate(c, admin, USERNAME, "Перф", password)
        u = User(c, USERNAME, password)
        if created:
            u.consent()
        pid = u.profile("Перф Тест")
        if {t["test_code"]: t["results"] for t in u.get(f"/patients/{pid}/trends")}.get(
            "CREA", 0
        ) >= REPORTS:
            sys.stdout.write("seed-perf: already there" + chr(10))
            return 0
        start = (_today() - timedelta(days=365 * YEARS)).isoformat()
        # a run stopped half way picks up where it was (nothing created twice)
        if not u.get(f"/patients/{pid}/transplants"):
            u.post(
                f"/patients/{pid}/transplants",
                {
                    "client_id": _cid(),
                    "organ": "kidney",
                    "transplant_date": start,
                    "date_precision": "day",
                    "country": "MN",
                    "hospital": "Улсын нэгдүгээр төв эмнэлэг",
                    "graft_status": "functioning",
                },
            )
        meds = u.get(f"/patients/{pid}/medications")
        if not meds:
            _medicines(u, pid, start)
            meds = u.get(f"/patients/{pid}/medications")
        once = next(m["id"] for m in meds if len(m["regimens"][0]["schedule"]["times"]) == 1)
        _intakes(pid, start, once)
        _reports(u, pid)
    sys.stdout.write(f"seed-perf: {USERNAME} ready ({REPORTS * len(TESTS)} values)" + chr(10))
    return 0


if __name__ == "__main__":
    sys.exit(main())
