"""Operator commands: `python -m labtrack.cli <command>`."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path


def _openapi(out: Path) -> None:
    # Schema generation needs no database; a placeholder URL satisfies settings validation.
    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://openapi@localhost/openapi")
    from labtrack.main import create_app  # noqa: PLC0415 - after env is set

    schema = create_app().openapi()
    text = json.dumps(schema, ensure_ascii=False, indent=2) + "\n"
    out.write_text(text, encoding="utf-8", newline="\n")  # LF on Windows too


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="labtrack")
    sub = parser.add_subparsers(dest="command", required=True)
    p_openapi = sub.add_parser("openapi", help="write the OpenAPI schema as UTF-8 JSON")
    p_openapi.add_argument("out", type=Path)
    p_seed = sub.add_parser("seed", help="load seed/ catalogs as labtrack_owner (idempotent)")
    p_seed.add_argument("--dir", type=Path, default=Path(os.environ.get("SEED_DIR", "/seed")))
    p_admin = sub.add_parser("create-admin", help="create a super admin with TOTP (Phase 1)")
    p_admin.add_argument("username")

    args = parser.parse_args(argv)
    if args.command == "openapi":
        _openapi(args.out)
        return 0
    if args.command == "seed":
        return _seed(args.dir)
    sys.stderr.write(f"'{args.command}' is implemented in Phase 1\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
