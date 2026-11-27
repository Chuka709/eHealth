"""Phase 6 DoD measurement, server side: the requests the app's Home makes for the demo_perf
profile (seed_perf.py), each repeated, with p50/p95, and Home as the app loads it (all at
once). The phone's part (rendering) is measured on the device; see docs/PROGRESS.md 6.10.

    uv run python scripts/perf_home.py [--rounds 40]
"""

import argparse
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import httpx
from seed_demo import BASE, _load, require_local_target

USERNAME = "demo_perf"


def _p(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(q * (len(ordered) - 1)))]


def main() -> int:
    require_local_target()
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=40)
    args = parser.parse_args()
    password = _load()["DEMO_PASSWORD"]
    # 127.0.0.1, not localhost: Windows tries ::1 first and waits 2 s on each new connection
    with httpx.Client(base_url=BASE.replace("//localhost", "//127.0.0.1"), timeout=60) as c:
        r = c.post(
            "/api/v1/auth/login",
            json={"username": USERNAME, "password": password, "platform": "android"},
        )
        r.raise_for_status()
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        refresh_token = r.json()["refresh_token"]
        pid = c.get("/api/v1/patients", headers=h).json()[0]["id"]
        now = datetime.now(UTC)

        def iso(t: datetime) -> str:  # "Z", never "+00:00" (a "+" in a query is a space)
            return t.strftime("%Y-%m-%dT%H:%M:%SZ")

        start, end = iso(now - timedelta(days=1)), iso(now + timedelta(days=1))
        p = f"/api/v1/patients/{pid}"
        calls = {
            "me": "/api/v1/me",
            "notifications": "/api/v1/me/notifications",
            "patients": "/api/v1/patients",
            "transplants": f"{p}/transplants",
            "medications": f"{p}/medications",
            "intakes (today)": f"{p}/intakes?from={start}&to={end}",
            "timezone": f"{p}/timezone",
            "appointments": f"{p}/appointments",
            "dashboard": f"{p}/dashboard",
            "trend TAC (1y)": f"{p}/trends/TAC?since={iso(now - timedelta(days=365))}",
            "timeline (first page)": f"{p}/timeline",
        }
        home = [k for k in calls if not k.startswith(("trend", "timeline"))]
        lines = []
        for name, path in calls.items():
            times = []
            for _ in range(args.rounds):
                t = time.perf_counter()
                resp = c.get(path, headers=h)
                times.append((time.perf_counter() - t) * 1000)
                resp.raise_for_status()
            lines.append(
                f"{name:24} p50 {statistics.median(times):7.1f} ms   p95 {_p(times, 0.95):7.1f} ms"
                f"   {len(resp.content):7d} B"
            )
        walls = []
        with ThreadPoolExecutor(max_workers=6) as pool:  # the app's concurrent requests
            for _ in range(args.rounds):
                t = time.perf_counter()
                for resp in pool.map(lambda k: c.get(calls[k], headers=h), home):
                    resp.raise_for_status()
                walls.append((time.perf_counter() - t) * 1000)
        lines.append(
            f"{'HOME (all at once)':24} p50 {statistics.median(walls):7.1f} ms"
            f"   p95 {_p(walls, 0.95):7.1f} ms"
        )
        # no session left behind on the dev stack
        c.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
