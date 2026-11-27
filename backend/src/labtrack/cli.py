"""Operator commands: `python -m labtrack.cli <command>`."""

import argparse
import asyncio
import json
import os
import re
import sys
from collections.abc import Callable
from pathlib import Path


def _openapi(out: Path) -> None:
    # Schema generation needs no database; a placeholder URL satisfies settings validation.
    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://openapi@localhost/openapi")
    os.environ.setdefault("ENVIRONMENT", "dev")
    from labtrack.main import create_app  # noqa: PLC0415 - after env is set

    schema = create_app().openapi()
    text = json.dumps(schema, ensure_ascii=False, indent=2) + "\n"
    out.write_text(text, encoding="utf-8", newline="\n")  # LF on Windows too


def _error_codes(out: Path) -> None:
    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://openapi@localhost/openapi")
    os.environ.setdefault("ENVIRONMENT", "dev")
    from labtrack.error_codes import error_codes, import_problem_fields  # noqa: PLC0415

    data = {"errors": error_codes(), "import_problems": import_problem_fields()}
    out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")


def _consent_versions(out: Path) -> None:
    """The consent text versions the app bundles next to its texts: the app sends these, not
    the server's, so a consent always names the text the user actually read."""
    from labtrack.consents import VERSIONS  # noqa: PLC0415

    out.write_text(json.dumps(VERSIONS, indent=2) + "\n", encoding="utf-8", newline="\n")


def _seed(seed_dir: Path) -> int:
    from labtrack.seed import SeedError, run  # noqa: PLC0415

    url = os.environ.get("MIGRATION_DATABASE_URL")
    if not url:
        sys.stderr.write("MIGRATION_DATABASE_URL is not set (role labtrack_owner)\n")
        return 2
    try:
        stats = asyncio.run(run(url, seed_dir))
    except SeedError as exc:
        sys.stderr.write(f"seed rejected, nothing written: {exc}\n")
        return 1
    sys.stdout.write(
        f"seeded: {stats.tests} tests, {stats.synonyms} synonyms, {stats.conversions} unit "
        f"conversions, {stats.unit_aliases} unit aliases, {stats.medications} medications\n"
    )
    return 0


def _create_admin(username: str, role: str) -> int:
    from labtrack.admin.cli import run  # noqa: PLC0415

    url = os.environ.get("MIGRATION_DATABASE_URL")
    if not url:
        sys.stderr.write("MIGRATION_DATABASE_URL is not set (run in the migrate container)\n")
        return 2
    if not re.fullmatch(r"[a-z0-9._]{3,32}", username):
        sys.stderr.write("username: a-z 0-9 . _ (3-32)\n")
        return 2
    return run(url, username, role)


def _rewrap() -> int:
    from labtrack.admin.cli import rewrap_user_fields  # noqa: PLC0415
    from labtrack.keys import get_key_provider, get_openbao  # noqa: PLC0415

    url = os.environ.get("MIGRATION_DATABASE_URL")
    if not url:
        sys.stderr.write("MIGRATION_DATABASE_URL is not set (run in the migrate container)\n")
        return 2
    if get_openbao() is not None:
        # values from before migration 0008 exist only in databases that began without OpenBao
        sys.stderr.write("not with OpenBao: user keys there are made with the account\n")
        return 2
    moved = asyncio.run(rewrap_user_fields(url, get_key_provider()))
    sys.stdout.write(f"re-sealed {moved} values under user keys\n")
    return 0


def _unlock_admin(username: str) -> int:
    from labtrack.admin.cli import unlock_admin  # noqa: PLC0415

    url = os.environ.get("MIGRATION_DATABASE_URL")
    if not url:
        sys.stderr.write("MIGRATION_DATABASE_URL is not set (run in the migrate container)\n")
        return 2
    if not asyncio.run(unlock_admin(url, username)):
        sys.stderr.write("no such admin\n")
        return 1
    sys.stdout.write("unlocked\n")
    return 0


def _redelete(since: str, apply: bool) -> int:
    from datetime import UTC, datetime  # noqa: PLC0415

    from labtrack.admin.redelete import Outcome, latest_events, reapply_deletions  # noqa: PLC0415

    url = os.environ.get("MIGRATION_DATABASE_URL")
    if not url:
        sys.stderr.write("MIGRATION_DATABASE_URL is not set (run in the migrate container)\n")
        return 2
    try:
        start = datetime.fromisoformat(since)
    except ValueError:
        sys.stderr.write("--since: the backup's ISO time with a zone, e.g. 2026-11-18T06:17:35Z\n")
        return 2
    if start.tzinfo is None:
        sys.stderr.write("--since needs a time zone (Z or +08:00)\n")
        return 2
    if start > datetime.now(UTC):
        sys.stderr.write("--since is in the future\n")
        return 2
    events = latest_events(sys.stdin, start)
    outcomes = asyncio.run(reapply_deletions(url, events, apply=apply))
    for uid, outcome in outcomes.items():  # ids and the event's time only (rule 3)
        sys.stdout.write(f"{outcome.value}\t{uid}\t{events[uid].at.isoformat()}\n")
    counts = {o: sum(1 for v in outcomes.values() if v is o) for o in Outcome}
    summary = ", ".join(f"{o.value} {n}" for o, n in counts.items() if n)
    sys.stdout.write(f"{len(outcomes)} account(s) in the logs since {since}: {summary or 'none'}\n")
    if counts[Outcome.WOULD_REAPPLY]:
        sys.stdout.write("dry run: nothing changed; run again with --apply\n")
    if counts[Outcome.CANCELLED_BUT_PENDING]:
        # the restored row still waits for the purge: keep the maintenance worker off until an
        # admin cancels it again (or it is meant to go) - OPS_RUNBOOK §5.6
        sys.stderr.write("cancelled_but_pending: decide each before the maintenance worker runs\n")
        return 3
    return 0


def _openbao_setup(out: Path, bound_cidrs: list[str], audit_file: str | None) -> int:
    """docs/SERVER_INSTALL_PLAN.md §3: BAO_ADDR, BAO_TOKEN (an admin token), BAO_CACERT. Each
    role's id and secret go to their own file (0600) - never to the terminal."""
    from labtrack.openbao_setup import bootstrap  # noqa: PLC0415

    addr, token = os.environ.get("BAO_ADDR"), os.environ.get("BAO_TOKEN")
    if not addr or not token:
        sys.stderr.write("BAO_ADDR and BAO_TOKEN are required\n")
        return 2
    if not addr.startswith("https://"):
        sys.stderr.write("BAO_ADDR must be https\n")
        return 2
    if not bound_cidrs:
        # a leaked secret id is useless from anywhere but the app's server (review S1 M3)
        sys.stderr.write("--bound-cidr is required (the app server's address)\n")
        return 2
    roles = asyncio.run(
        bootstrap(
            addr,
            token,
            ca_cert=os.environ.get("BAO_CACERT"),
            bound_cidrs=bound_cidrs,
            audit_file=audit_file,
            revoke_admin=True,
        )
    )
    out.mkdir(mode=0o700, parents=True, exist_ok=True)
    out.chmod(0o700)
    for cred in roles:
        for kind, value in (("role_id", cred.role_id), ("secret_id", cred.secret_id)):
            path = out / f"{cred.role}.{kind}"
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            os.fchmod(fd, 0o600)  # an existing file keeps its mode through O_TRUNC
            with os.fdopen(fd, "w", encoding="ascii", newline="\n") as f:
                f.write(value)
    sys.stdout.write(f"openbao ready: {len(roles)} roles, credentials in {out}\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="labtrack")
    sub = parser.add_subparsers(dest="command", required=True)
    p_openapi = sub.add_parser("openapi", help="write the OpenAPI schema as UTF-8 JSON")
    p_openapi.add_argument("out", type=Path)
    p_codes = sub.add_parser("error-codes", help="write the API error codes as JSON")
    p_codes.add_argument("out", type=Path)
    p_consents = sub.add_parser("consent-versions", help="write consent text versions as JSON")
    p_consents.add_argument("out", type=Path)
    p_seed = sub.add_parser("seed", help="load seed/ catalogs as labtrack_owner (idempotent)")
    p_seed.add_argument("--dir", type=Path, default=Path(os.environ.get("SEED_DIR", "/seed")))
    p_admin = sub.add_parser("create-admin", help="create an admin account with TOTP")
    p_admin.add_argument("username")
    p_admin.add_argument("--role", choices=("super_admin", "support"), default="super_admin")
    sub.add_parser("rewrap-user-keys", help="move KEK-sealed phone numbers under user keys")
    p_unlock = sub.add_parser("unlock-admin", help="clear an admin's sign-in lockout")
    p_unlock.add_argument("username")
    p_redel = sub.add_parser(
        "redelete", help="re-apply account deletions from API logs (stdin) after a restore"
    )
    p_redel.add_argument("--since", required=True, help="the backup's time (ISO, with a zone)")
    p_redel.add_argument("--apply", action="store_true", help="write (default: dry run)")

    p_bao = sub.add_parser("openbao-setup", help="transit, the KEK, policies and AppRoles")
    p_bao.add_argument("--out", type=Path, required=True, help="folder for the role secrets")
    p_bao.add_argument("--bound-cidr", action="append", default=[], help="allowed client CIDR")
    p_bao.add_argument("--audit-file", help="OpenBao's audit log path (on the OpenBao host)")

    args = parser.parse_args(argv)
    writers = {
        "openapi": _openapi,
        "error-codes": _error_codes,
        "consent-versions": _consent_versions,
    }
    if args.command in writers:
        writers[args.command](args.out)
        return 0
    commands: dict[str, Callable[[], int]] = {
        "seed": lambda: _seed(args.dir),
        "rewrap-user-keys": _rewrap,
        "unlock-admin": lambda: _unlock_admin(args.username),
        "openbao-setup": lambda: _openbao_setup(args.out, args.bound_cidr, args.audit_file),
        "redelete": lambda: _redelete(args.since, args.apply),
        "create-admin": lambda: _create_admin(args.username, args.role),
    }
    return commands[args.command]()


if __name__ == "__main__":
    raise SystemExit(main())
