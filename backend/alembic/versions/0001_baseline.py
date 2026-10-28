"""Baseline: extensions and schema hardening (docs/03_DATA_MODEL.md, RLS).

Roles are created by infra/postgres/init (they need passwords from the environment).

Revision ID: 0001
Revises:
Create Date: 2026-10-28
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("create extension if not exists pg_trgm")
    op.execute("create extension if not exists pgcrypto")
    op.execute("create extension if not exists citext")
    # Nobody but the owner creates objects in public; no temp tables (blocks pg_temp shadowing
    # of tables referenced by security definer functions).
    op.execute("revoke create on schema public from public")
    op.execute("grant usage on schema public to labtrack_app, labtrack_admin, labtrack_maint")
    op.execute(
        "do $$ begin execute format('revoke temporary on database %I from public', "
        "current_database()); end $$"
    )
    # Functions are not executable by default; each one is granted explicitly.
    op.execute("alter default privileges in schema public revoke execute on functions from public")


def downgrade() -> None:
    op.execute("alter default privileges in schema public grant execute on functions to public")
    op.execute(
        "do $$ begin execute format('grant temporary on database %I to public', "
        "current_database()); end $$"
    )
    op.execute("revoke usage on schema public from labtrack_app, labtrack_admin, labtrack_maint")
    op.execute("grant create on schema public to public")
    # Extensions are left installed: dropping them would break any later data.
