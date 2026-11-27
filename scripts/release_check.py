"""Checks before a store build (`just release-check`; docs/STORE_RELEASE.md §5, 09 "Release бүрийн
шалгалт"). Every step runs, then the summary; exit 1 if any failed. Nothing here prints values
from .env or PHI.

Steps: legal pages without drafts left (LEGAL_RELEASE=1), the store app config tests, the
release manifest (expo introspect), dependency audits (pip-audit, pnpm audit), the extraction
eval (`--check`, synthetic cases + local ones if present), the hazard log's shape. The checks a
person signs off (phone matrix, medical-reviewer on new texts) are listed at the end.

    python scripts/release_check.py [--skip NAME ...]
"""

import argparse
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PNPM = shutil.which("pnpm.cmd") or shutil.which("pnpm") or "pnpm"
NPX = shutil.which("npx.cmd") or shutil.which("npx") or "npx"
UV = shutil.which("uv") or "uv"
PIP_AUDIT = "pip-audit==2.9.0"
MANUAL = (
    "Сануулгын тест матриц (B6: Android 3 брэнд, iOS сүүлийн 2) ногоон",
    "Шинэ функц hazard log-д нөлөөлсөн бол 09 шинэчлэгдсэн",
    "Хэрэглэгчид харагдах шинэ текст — medical-reviewer",
    "just restore-drill энэ сард (OPS_RUNBOOK §4)",
)


def _run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> bool:
    print(f"$ {' '.join(cmd)}  (in {cwd.relative_to(ROOT) or '.'})", flush=True)
    full = {**os.environ, **(env or {})}
    return subprocess.run(cmd, cwd=cwd, env=full, check=False).returncode == 0  # noqa: S603


def legal() -> bool:
    return _run([PNPM, "--filter", "web", "test"], ROOT, {"LEGAL_RELEASE": "1"})


def app_config() -> bool:
    return _run(
        [PNPM, "--filter", "mobile", "exec", "jest", "src/app-config.test.ts", "--forceExit"], ROOT
    )


def manifest() -> bool:
    return _run(["node", "scripts/release-manifest.mjs"], ROOT / "mobile")


def _uv_env() -> dict[str, str]:
    env = {"UV_PYTHON_DOWNLOADS": "never"} if os.name == "nt" else {}
    if os.name == "nt":  # the system drive is small on the dev machine (docs/11_TOOLING.md)
        env |= {"UV_CACHE_DIR": "F:/.uv-cache", "UV_TOOL_DIR": "F:/.uv-tools"}
    return env


def pip_audit() -> bool:
    backend = ROOT / "backend"
    with tempfile.TemporaryDirectory() as tmp:
        req = Path(tmp) / "requirements.txt"
        export = [UV, "export", "--frozen", "--no-dev", "--no-emit-project", "-q"]
        if not _run([*export, "--format", "requirements-txt", "-o", str(req)], backend, _uv_env()):
            return False
        audit = ["--require-hashes", "--disable-pip", "--progress-spinner", "off"]
        return _run(
            [UV, "tool", "run", "--from", PIP_AUDIT, "pip-audit", "-r", str(req), *audit],
            backend,
            _uv_env(),
        )


_REVIEW_BY = re.compile(r"review by (\d{4}-\d\d-\d\d)")


def pnpm_audit() -> bool:
    """Accepted advisories (pnpm-workspace.yaml auditConfig.ignoreGhsas, with reasons) hold only
    until their review date: after it the step fails until someone looks again."""
    workspace = (ROOT / "pnpm-workspace.yaml").read_text(encoding="utf8")
    dates = [date.fromisoformat(d) for d in _REVIEW_BY.findall(workspace)]
    if "ignoreGhsas" in workspace and not dates:
        print("pnpm-audit: FAIL ignored advisories without a 'review by YYYY-MM-DD' date")
        return False
    if any(d < date.today() for d in dates):
        print(f"pnpm-audit: FAIL the ignored advisories were due for review on {min(dates)}")
        return False
    return _run([PNPM, "audit", "--prod", "--audit-level", "moderate"], ROOT)


def eval_check() -> bool:
    args = ["../eval/cases", "../eval/local", "--seed", "../seed/lab_tests.json", "--check"]
    return _run(
        [UV, "run", "python", "-m", "labtrack.extraction.evaluate", *args],
        ROOT / "backend",
        _uv_env(),
    )


_ROW = re.compile(r"^\| (H\d+[a-z]?) \|")
_PLACEHOLDER = re.compile(r"TODO|TBD|\?\?\?|\[\.\.\.\]")


def hazard_log() -> bool:
    """Every hazard row is whole: seven cells, a control and a residual risk, no placeholder,
    and no number twice (a release does not ship with a hazard nobody controls)."""
    text = (ROOT / "docs" / "09_CLINICAL_SAFETY.md").read_text(encoding="utf8")
    seen: set[str] = set()
    problems: list[str] = []
    for line in text.splitlines():
        m = _ROW.match(line)
        if not m:
            continue
        hid = m.group(1)
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if hid in seen:
            problems.append(f"{hid} twice")
        seen.add(hid)
        if len(cells) < 7:  # noqa: PLR2004 - the table's columns
            problems.append(f"{hid}: {len(cells)} cells")
        elif not cells[5] or not cells[6]:
            problems.append(f"{hid}: no control or residual risk")
        if _PLACEHOLDER.search(line):
            problems.append(f"{hid}: a placeholder is left")
    for p in problems:
        print(f"hazard-log: FAIL {p}")
    print(f"hazard-log: {len(seen)} hazards checked")
    return bool(seen) and not problems


STEPS: dict[str, Callable[[], bool]] = {
    "legal": legal,
    "app-config": app_config,
    "manifest": manifest,
    "pip-audit": pip_audit,
    "pnpm-audit": pnpm_audit,
    "eval": eval_check,
    "hazard-log": hazard_log,
}


def main() -> int:
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")  # Mongolian text on a cp1252 Windows console
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip", nargs="*", default=[], choices=sorted(STEPS))
    args = parser.parse_args()
    results: dict[str, bool | None] = {}
    for name, step in STEPS.items():
        if name in args.skip:
            results[name] = None
            continue
        print(f"\n== {name}", flush=True)
        results[name] = step()
    print("\n== release-check")
    for name, ok in results.items():
        print(f"  {'SKIP' if ok is None else 'ok  ' if ok else 'FAIL'}  {name}")
    print("\nГараар баталгаажуулах (09 «Release бүрийн шалгалт»):")
    for item in MANUAL:
        print(f"  [ ] {item}")
    failed = [n for n, ok in results.items() if ok is False]
    skipped = [n for n, ok in results.items() if ok is None]
    if skipped:
        print(f"\nSKIPPED: {', '.join(skipped)} - not a release until they run")
    return 1 if failed or skipped else 0


if __name__ == "__main__":
    sys.exit(main())
