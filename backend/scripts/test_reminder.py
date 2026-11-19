"""Real-phone reminder checks (docs/DEVICE_TEST.md): adds a made-up medicine "Туршилтын эм"
with reminders a few minutes from now to demo_kidney (dev stack only, `just seed-demo` first).

    cd backend && uv run python scripts/test_reminder.py 4 8 12      # minutes from now
Prints only the times (no credentials). Then bring the app to the foreground (or restart it)
so it reads the new medicine and schedules the reminders.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx
from seed_demo import BASE, User, _load

UB = ZoneInfo("Asia/Ulaanbaatar")


def main() -> int:
    minutes = [int(m) for m in sys.argv[1:]] or [4, 8, 12]
    now = datetime.now(UB)
    times = {(now + timedelta(minutes=m)).strftime("%H:%M"): "1" for m in minutes}
    creds = _load()
    with httpx.Client(base_url=BASE, timeout=30) as c:
        u = User(c, "demo_kidney", creds["DEMO_PASSWORD"])
        pid = u.profile("Батболд Дорж")
        u.medicine(pid, "Туршилтын эм", times, unit="mg")
    sys.stdout.write("reminders at " + ", ".join(times) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
