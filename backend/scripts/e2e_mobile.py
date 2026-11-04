"""Maestro flows against a development build on the Android emulator (`just e2e-mobile`).

Phase 1.12. Provisions a throwaway user with an activation token the same way `just fuzz-api`
does (dev stack only), runs the flows in mobile/.maestro, then disables every throwaway account.
Values reach Maestro as MAESTRO_* environment variables, never on a command line. Maestro's
debug output records typed text and opened links (the password, the activation link), so it goes
to a temporary directory that is deleted afterwards; E2E_KEEP_DEBUG=1 keeps it for a failing run
(the accounts in it are disabled by then).
"""

import os
import secrets
import shutil
import subprocess
import sys
import tempfile

import httpx
from fuzz_api import BASE, ROOT, cleanup, provision_user, require_local_target

MAESTRO = os.environ.get("MAESTRO_BIN", "F:/tools/maestro/bin/maestro.bat")
APP_ID = os.environ.get("APP_ID", "mn.labtrack.app.development")


def _run(flows: list[str]) -> int:
    with httpx.Client(base_url=BASE, timeout=30) as c:
        user, token = provision_user(c)
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
    }
    debug = tempfile.mkdtemp(prefix="maestro-")
    cmd = [MAESTRO, "test", "--debug-output", debug, "--flatten-debug-output",
           *(flows or [str(ROOT / "mobile" / ".maestro")])]  # fmt: skip
    try:
        code = subprocess.run(cmd, cwd=ROOT, env=env, check=False).returncode  # noqa: S603
        return code or _reminders_scheduled()
    finally:
        if os.environ.get("E2E_KEEP_DEBUG") == "1":
            sys.stderr.write(f"e2e-mobile: Maestro debug output kept in {debug}\n")
        else:
            shutil.rmtree(debug, ignore_errors=True)


def _reminders_scheduled() -> int:
    """Phase 2.5 DoD: after the flow added a medicine, its reminders are on the OS schedule
    (the app's alarms in AlarmManager). Reads counts only, never notification text."""
    adb = shutil.which("adb") or "adb"
    serial = os.environ.get("ANDROID_SERIAL")
    target = ["-s", serial] if serial else []
    out = subprocess.run(  # noqa: S603
        [adb, *target, "shell", "dumpsys", "alarm"], capture_output=True, text=True, check=False
    ).stdout
    count = sum(1 for line in out.splitlines() if APP_ID in line and "RTC" in line)
    sys.stderr.write(f"e2e-mobile: {count} alarm entries for {APP_ID}\n")
    return 0 if count > 0 else 1


def main() -> int:
    require_local_target()
    result = 1
    try:
        result = _run([f for f in sys.argv[1:] if f])  # `just` passes '' when none given
    finally:
        cleaned = cleanup()
    return result if cleaned else 1


if __name__ == "__main__":
    sys.exit(main())
