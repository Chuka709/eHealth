"""Catalogs: lab tests, synonyms, units, medications (docs/03; seed/*.json).

The test catalog holds recognition, unit conversion and implausible-value bounds ONLY - never
reference or critical ranges (those come from the uploaded document; CLAUDE.md rule 5).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-28
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UP = [
    "create type value_kind as enum ('numeric','qualitative','text')",
    """
    create table test_catalog (
      code text primary key check (code ~ '^[A-Z0-9_]{1,32}$'),
      loinc text check (loinc ~ '^[0-9]{1,7}-[0-9]$'),
      name_mn text not null,
      name_en text not null,
      name_ru text,
      category text not null,
      kind value_kind not null default 'numeric',
      canonical_unit text,
      decimals int not null default 2 check (decimals between 0 and 6),
      physio_min numeric,
      physio_max numeric,
      delta_check_pct numeric check (delta_check_pct > 0),
      is_active boolean not null default true,
      check (physio_min is null or physio_max is null or physio_min < physio_max)
    )
    """,
    """
    create table test_synonyms (
      id bigserial primary key,
      test_code text not null references test_catalog on delete cascade,
      synonym text not null,
      synonym_norm text not null,
      user_id uuid references users on delete cascade
    )
    """,
    # One mapping per normalised name globally, and one per user for learned synonyms.
    """create unique index test_synonyms_global on test_synonyms (synonym_norm)
       where user_id is null""",
    """create unique index test_synonyms_user on test_synonyms (user_id, synonym_norm)
       where user_id is not null""",
    "create index on test_synonyms using gin (synonym_norm gin_trgm_ops)",
    """
    create table unit_aliases (
      alias_norm text primary key,
      unit text not null
    )
    """,
    """
    create table unit_conversions (
      test_code text not null references test_catalog on delete cascade,
      from_unit text not null,
      to_unit text not null,
      factor numeric not null check (factor > 0),
      primary key (test_code, from_unit, to_unit)
    )
    """,
    """
    create table medication_catalog (
      code text primary key check (code ~ '^[A-Z0-9_]{1,40}$'),
      generic_mn text not null,
      generic_en text not null,
      brands text[] not null default '{}',
      category text not null,
      forms text[] not null default '{}',
      related_test_code text references test_catalog,
      is_active boolean not null default true
    )
    """,
    # Learned synonyms are per user (raw lab names may carry clinic-specific text).
    "alter table test_synonyms enable row level security",
    "alter table test_synonyms force row level security",
    """create policy test_synonyms_owner on test_synonyms for all to labtrack_owner
       using (true) with check (true)""",
    """create policy test_synonyms_select on test_synonyms for select to labtrack_app
       using (user_id is null or user_id = app_user_id())""",
    """create policy test_synonyms_insert on test_synonyms for insert to labtrack_app
       with check (user_id = app_user_id())""",
    """grant select on test_catalog, unit_aliases, unit_conversions, medication_catalog
       to labtrack_app""",
    "grant select, insert on test_synonyms to labtrack_app",
    "grant usage on sequence test_synonyms_id_seq to labtrack_app",
    "grant select on test_catalog, medication_catalog to labtrack_admin",
]


def upgrade() -> None:
    for sql in _UP:
        op.execute(sql)


def downgrade() -> None:
    for table in (
        "medication_catalog",
        "unit_conversions",
        "unit_aliases",
        "test_synonyms",
        "test_catalog",
    ):
        op.execute(f"drop table if exists {table} cascade")
    op.execute("drop type if exists value_kind")
