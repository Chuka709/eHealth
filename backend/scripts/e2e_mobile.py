"""Maestro flows against a development build on the Android emulator (`just e2e-mobile`).

Phase 1.12. Provisions a throwaway user with an activation token the same way `just fuzz-api`
does (dev stack only), runs the flows in mobile/.maestro, then disables every throwaway account.
Values reach Maestro as MAESTRO_* environment variables, never on a command line. Maestro's
debug output records typed text and opened links (the password, the activation link), so it goes
to a temporary directory that is deleted afterwards; E2E_KEEP_DEBUG=1 keeps it for a failing run
(the accounts in it are disabled by then).
"""

import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable

import httpx
from fuzz_api import BASE, ROOT, cleanup, provision_user, require_local_target

MAESTRO = os.environ.get("MAESTRO_BIN", "F:/tools/maestro/bin/maestro.bat")
APP_ID = os.environ.get("APP_ID", "mn.munkhly.labtrack.development")


def _run(flows: list[str]) -> int:
    with httpx.Client(base_url=BASE, timeout=30) as c:
        user, token = provision_user(c)
        # Phase 2.8f: a second person, invited as caregiver by the first in the flow. Activated
        # here: an invitation reaches only an active account (the answer is the same either way)
        carer, carer_token = provision_user(c)
        carer_password = f"Maestro {secrets.token_urlsafe(12)} lake"
        c.post(
            "/api/v1/auth/activate",
            json={"token": carer_token, "username": carer, "new_password": carer_password},
        ).raise_for_status()
    env = {
        **os.environ,
        # Windows JVMs default to cp1252, which turns the flows' Cyrillic text into "?".
        "JAVA_TOOL_OPTIONS": "-Dfile.encoding=UTF-8 -Dstdout.encoding=UTF-8",
        "MAESTRO_APP_ID": APP_ID,
        # URL-encoded Metro address for the dev launcher: the emulator's alias for the host. Not
        # `adb reverse` to localhost - Maestro's adb setup leaves that tunnel dead mid-run.
        "MAESTRO_DEV_SERVER": os.environ.get("DEV_SERVER", "http%3A%2F%2F10.0.2.2%3A8081"),
        "MAESTRO_USERNAME": user,
        # ASCII only: Android text input from Maestro cannot type Cyrillic reliably.
        "MAESTRO_PASSWORD": f"Maestro {secrets.token_urlsafe(12)} river",
        "MAESTRO_ACTIVATION_TOKEN": token,
        "MAESTRO_CAREGIVER_USERNAME": carer,
        "MAESTRO_CAREGIVER_PASSWORD": carer_password,
    }
    debug = tempfile.mkdtemp(prefix="maestro-")

    def maestro(paths: list[str]) -> int:
        cmd = [MAESTRO, "test", "--debug-output", debug, "--flatten-debug-output", *paths]
        return subprocess.run(cmd, cwd=ROOT, env=env, check=False).returncode  # noqa: S603

    flows_dir = ROOT / "mobile" / ".maestro"
    try:
        if flows:
            return maestro(flows)
        # 1. activation, a medicine, the emergency card: the medicine's reminders are scheduled
        code = maestro([str(flows_dir / "activation.yaml")]) or _reminders(expect_some=True)
        if code:
            return code
        # 2.10d (Phase 2 DoD): the transplant wizard within 3 minutes, a time-zone change that
        # keeps "home" doses where they were, and a reminder arriving with the app closed and
        # the phone offline
        code = _timed(lambda: maestro([str(flows_dir / "wizard.yaml")]), "wizard", limit_s=180)
        code = code or _travel(lambda: maestro([str(flows_dir / "travel.yaml")]))
        code = code or _offline_reminder()
        if code:
            return code
        # 2. the caregiver flow on the same app state: the owner's sign-out takes their
        #    reminders off the phone (rule 8) - none left at the end
        return maestro([str(flows_dir / "caregiver.yaml")]) or _reminders(expect_some=False)
    finally:
        if os.environ.get("E2E_KEEP_DEBUG") == "1":
            sys.stderr.write(f"e2e-mobile: Maestro debug output kept in {debug}\n")
        else:
            shutil.rmtree(debug, ignore_errors=True)


def _adb(*args: str) -> str:
    adb = shutil.which("adb") or "adb"
    serial = os.environ.get("ANDROID_SERIAL")
    target = ["-s", serial] if serial else []
    return subprocess.run(  # noqa: S603
        [adb, *target, "shell", *args],
        capture_output=True,
        encoding="utf-8",  # dumpsys prints UTF-8 (Windows would read it as cp1252)
        errors="replace",
        check=False,
    ).stdout


def _alarm_instants() -> list[int]:
    """The app's wall-clock alarms (epoch ms) on the OS schedule - instants only, no text."""
    pattern = re.compile(r"Alarm\{\S+ type [01] origWhen (\d+) .*" + re.escape(APP_ID) + r"\}")
    return sorted(int(m.group(1)) for m in pattern.finditer(_adb("dumpsys", "alarm")))


def _timed(run: Callable[[], int], name: str, *, limit_s: int) -> int:
    started = time.monotonic()
    code = run()
    took = time.monotonic() - started
    sys.stderr.write(f"e2e-mobile: {name} flow took {took:.0f} s (limit {limit_s} s)\n")
    return code or (0 if took <= limit_s else 1)


def _travel(run: Callable[[], int]) -> int:
    """H7: the phone moves to Seoul; a "home"-mode medicine's reminders keep their instants."""
    before = _alarm_instants()
    zone = _adb("getprop", "persist.sys.timezone").strip() or "Asia/Ulaanbaatar"
    try:
        _adb("cmd", "alarm", "set-timezone", "Asia/Seoul")
        code = run()
        time.sleep(5)  # the app re-plans on resume (one sync at a time)
        after = _alarm_instants()
    finally:
        _adb("cmd", "alarm", "set-timezone", zone)
    moved = before != after
    sys.stderr.write(
        f"e2e-mobile: time zone Seoul - {len(before)} reminders, "
        f"{'MOVED' if moved else 'same instants'}\n"
    )
    return code or (1 if moved or not before else 0)


def _reopen() -> int:
    """The app back in the foreground through the dev launcher (a plain launch restarts it
    without the bundle): it starts and re-plans its reminders."""
    server = os.environ.get("DEV_SERVER", "http%3A%2F%2F10.0.2.2%3A8081")
    _adb("input", "keyevent", "3")  # to the background first: coming back is what re-plans
    time.sleep(3)
    _adb("am", "start", "-a", "android.intent.action.VIEW",
         "-d", f"'exp+labtrack://expo-development-client/?url={server}'")  # fmt: skip
    time.sleep(45)
    return 0


def _exact_alarms() -> bool:
    """Whether every app alarm is exact (no delivery window) - read from the OS schedule."""
    lines = _adb("dumpsys", "alarm").splitlines()
    head = re.compile(r"Alarm\{\S+ type [01] origWhen \d+ .*" + re.escape(APP_ID) + r"\}")
    windows = []
    for i, line in enumerate(lines):
        if head.search(line):
            # the alarm's details follow on the next lines: "... window=<duration> ..."
            found = re.search(r"window=(\S+)", " ".join(lines[i + 1 : i + 3]))
            windows.append(found.group(1) if found else "?")
    return bool(windows) and all(w == "0" for w in windows)


def _renew(sign_in: Callable[[], int]) -> int:
    """H18: reminders set without the exact-alarm permission are set anew once it is given
    (the user grants it on the explanation screen and comes back to the app)."""
    _adb("appops", "set", APP_ID, "SCHEDULE_EXACT_ALARM", "default")
    code = sign_in()
    before = _exact_alarms()
    _adb("appops", "set", APP_ID, "SCHEDULE_EXACT_ALARM", "allow")
    try:
        code = code or _reopen()
        after = _exact_alarms()
    finally:
        _adb("appops", "set", APP_ID, "SCHEDULE_EXACT_ALARM", "default")
    sys.stderr.write(
        f"e2e-mobile: permission given - reminders {'exact' if before else 'inexact'} before, "
        f"{'exact' if after else 'NOT exact'} after\n"
    )
    return code or (0 if after and not before else 1)


def _offline_reminder(start: Callable[[], int] = _reopen) -> int:
    """H6: with the app closed and the phone in airplane mode, the next reminder still shows.
    The clock is set to just before it and restored afterwards. Counts notifications only.
    Without the exact-alarm permission (Android 14+ default) Android may hold a reminder back
    by up to an hour (H18): it is allowed first, as the explanation screen asks the user to,
    and the app (`start`) schedules its reminders under it."""
    _adb("appops", "set", APP_ID, "SCHEDULE_EXACT_ALARM", "allow")
    try:
        code = start()
        exact = _exact_alarms()
        sys.stderr.write(f"e2e-mobile: reminders {'exact' if exact else 'NOT exact'}\n")
        return code or (_offline_reminder_exact() if exact else 1)
    finally:
        # taking the permission back makes Android drop the app's exact alarms (its next start
        # re-plans them inexact)
        _adb("appops", "set", APP_ID, "SCHEDULE_EXACT_ALARM", "default")


def _offline_reminder_exact() -> int:
    upcoming = [t for t in _alarm_instants() if t > time.time() * 1000]
    if not upcoming:
        sys.stderr.write("e2e-mobile: no upcoming reminder to wait for\n")
        return 1
    posted = re.compile(r"NotificationRecord\(.*pkg=" + re.escape(APP_ID))

    def count() -> int:
        return len(posted.findall(_adb("dumpsys", "notification")))

    _adb("input", "keyevent", "3")  # Home: the app goes to the background
    time.sleep(2)
    _adb("am", "kill", APP_ID)  # its process ends, as when the system reclaims it
    auto_time = _adb("settings", "get", "global", "auto_time").strip() or "1"
    shown_before = count()
    try:
        _adb("cmd", "connectivity", "airplane-mode", "enable")
        _adb("settings", "put", "global", "auto_time", "0")
        _adb("cmd", "alarm", "set-time", str(upcoming[0] - 20_000))
        arrived = False
        for _ in range(60):
            time.sleep(2)
            if count() > shown_before:
                arrived = True
                break
    finally:
        _adb("cmd", "alarm", "set-time", str(int(time.time() * 1000)))
        _adb("settings", "put", "global", "auto_time", auto_time)
        _adb("cmd", "connectivity", "airplane-mode", "disable")
    sys.stderr.write(
        f"e2e-mobile: offline, app closed - reminder {'shown' if arrived else 'NOT shown'}\n"
    )
    return 0 if arrived else 1


def _reminders(*, expect_some: bool) -> int:
    """Phase 2.5 DoD: after the flow added a medicine, its reminders are on the OS schedule
    (the app's alarms in AlarmManager); Phase 2.8f: after that user signed out, none are left.
    Reads counts only, never notification text."""
    adb = shutil.which("adb") or "adb"
    serial = os.environ.get("ANDROID_SERIAL")
    target = ["-s", serial] if serial else []
    out = subprocess.run(  # noqa: S603
        [adb, *target, "shell", "dumpsys", "alarm"], capture_output=True, text=True, check=False
    ).stdout
    count = sum(1 for line in out.splitlines() if APP_ID in line and "RTC" in line)
    sys.stderr.write(f"e2e-mobile: {count} alarm entries for {APP_ID}\n")
    return 0 if (count > 0) == expect_some else 1


FAST_STAGES = ("reminders", "wizard", "travel", "renew", "offline")


def _demo_credentials() -> dict[str, str]:
    path = ROOT / ".env.demo"
    if not path.exists():
        raise SystemExit("e2e-mobile: no .env.demo - run `just seed-demo` first")
    lines = path.read_text(encoding="utf8").splitlines()
    return dict(line.split("=", 1) for line in lines if "=" in line and not line.startswith("#"))


def _drop_transplants(username: str, password: str) -> None:
    """The wizard stage leaves the demo account as it was: its transplants are deleted."""
    with httpx.Client(base_url=BASE, timeout=30) as c:
        r = c.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password, "platform": "android"},
        )
        r.raise_for_status()
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        for p in c.get("/api/v1/patients", headers=h).json():
            for t in c.get(f"/api/v1/patients/{p['id']}/transplants", headers=h).json():
                c.delete(
                    f"/api/v1/patients/{p['id']}/transplants/{t['id']}", headers=h
                ).raise_for_status()


def _run_fast(stages: list[str]) -> int:
    """`just e2e-mobile-fast [stage ...]`: the 2.10d device checks on the seeded demo accounts
    (`just seed-demo`) - a sign-in instead of a new, activated account per run."""
    creds = _demo_credentials()
    password = creds["DEMO_PASSWORD"]
    flows_dir = ROOT / "mobile" / ".maestro"
    debug = tempfile.mkdtemp(prefix="maestro-")

    def maestro(user: str, flow: str) -> int:
        env = {
            **os.environ,
            "JAVA_TOOL_OPTIONS": "-Dfile.encoding=UTF-8 -Dstdout.encoding=UTF-8",
            "MAESTRO_APP_ID": APP_ID,
            "MAESTRO_DEV_SERVER": os.environ.get("DEV_SERVER", "http%3A%2F%2F10.0.2.2%3A8081"),
            "MAESTRO_USERNAME": user,
            "MAESTRO_PASSWORD": password,
        }
        cmd = [
            MAESTRO,
            "test",
            "--debug-output",
            debug,
            "--flatten-debug-output",
            str(flows_dir / flow),
        ]
        return subprocess.run(cmd, cwd=ROOT, env=env, check=False).returncode  # noqa: S603

    try:
        code = 0
        if "wizard" in stages:
            code = maestro("demo_new", "demo-login.yaml") or _timed(
                lambda: maestro("demo_new", "wizard.yaml"), "wizard", limit_s=180
            )
            _drop_transplants("demo_new", password)
        if code:
            return code
        # the kidney recipient: three medicines with reminders in "home" mode
        if set(stages) & {"reminders", "travel", "offline"}:
            code = maestro("demo_kidney", "demo-login.yaml")
            code = code or (_reminders(expect_some=True) if "reminders" in stages else 0)
        if not code and "travel" in stages:
            code = _travel(lambda: maestro("demo_kidney", "travel.yaml"))
        if not code and "renew" in stages:
            code = _renew(lambda: maestro("demo_kidney", "demo-login.yaml"))
        if not code and "offline" in stages:
            # signed in afresh under the permission: the reminders are set exact from the start
            code = _offline_reminder(lambda: maestro("demo_kidney", "demo-login.yaml"))
        return code
    finally:
        if os.environ.get("E2E_KEEP_DEBUG") == "1":
            sys.stderr.write(f"e2e-mobile: Maestro debug output kept in {debug}\n")
        else:
            shutil.rmtree(debug, ignore_errors=True)


def main() -> int:
    require_local_target()
    args = [f for f in sys.argv[1:] if f]  # `just` passes '' when none given
    if args[:1] == ["--fast"]:
        stages = " ".join(args[1:]).split() or list(FAST_STAGES)  # one quoted string from `just`
        unknown = set(stages) - set(FAST_STAGES)
        if unknown:
            raise SystemExit(f"e2e-mobile: unknown stage(s) {sorted(unknown)}; {FAST_STAGES}")
        return _run_fast(stages)
    result = 1
    try:
        result = _run(args)
    finally:
        cleaned = cleanup()
    return result if cleaned else 1


if __name__ == "__main__":
    sys.exit(main())
