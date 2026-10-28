"""Operator commands: `python -m labtrack.cli <command>`."""

import argparse
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="labtrack")
    sub = parser.add_subparsers(dest="command", required=True)
    p_openapi = sub.add_parser("openapi", help="write the OpenAPI schema as UTF-8 JSON")
    p_openapi.add_argument("out", type=Path)
    sub.add_parser("seed", help="load seed/ catalogs (Phase 1)")
    p_admin = sub.add_parser("create-admin", help="create a super admin with TOTP (Phase 1)")
    p_admin.add_argument("username")

    args = parser.parse_args(argv)
    if args.command == "openapi":
        _openapi(args.out)
        return 0
    sys.stderr.write(f"'{args.command}' is implemented in Phase 1\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
