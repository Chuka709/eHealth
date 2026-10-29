"""Operator commands: `python -m labtrack.cli <command>`."""

import argparse
import asyncio
import json
import os
import re
import sys
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
    from labtrack.keys import get_key_provider  # noqa: PLC0415

    url = os.environ.get("MIGRATION_DATABASE_URL")
    if not url:
        sys.stderr.write("MIGRATION_DATABASE_URL is not set (run in the migrate container)\n")
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="labtrack")
    sub = parser.add_subparsers(dest="command", required=True)
    p_openapi = sub.add_parser("openapi", help="write the OpenAPI schema as UTF-8 JSON")
    p_openapi.add_argument("out", type=Path)
    p_codes = sub.add_parser("error-codes", help="write the API error codes as JSON")
    p_codes.add_argument("out", type=Path)
    p_seed = sub.add_parser("seed", help="load seed/ catalogs as labtrack_owner (idempotent)")
    p_seed.add_argument("--dir", type=Path, default=Path(os.environ.get("SEED_DIR", "/seed")))
    p_admin = sub.add_parser("create-admin", help="create an admin account with TOTP")
    p_admin.add_argument("username")
    p_admin.add_argument("--role", choices=("super_admin", "support"), default="super_admin")
    sub.add_parser("rewrap-user-keys", help="move KEK-sealed phone numbers under user keys")
    p_unlock = sub.add_parser("unlock-admin", help="clear an admin's sign-in lockout")
    p_unlock.add_argument("username")

    args = parser.parse_args(argv)
    if args.command == "openapi":
        _openapi(args.out)
        return 0
    if args.command == "error-codes":
        _error_codes(args.out)
        return 0
    if args.command == "seed":
        return _seed(args.dir)
    if args.command == "rewrap-user-keys":
        return _rewrap()
    if args.command == "unlock-admin":
        return _unlock_admin(args.username)
    return _create_admin(args.username, args.role)


if __name__ == "__main__":
    raise SystemExit(main())
