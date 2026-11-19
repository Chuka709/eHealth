"""A profile's reminder time zone and its history (Phase 2.5; OPEN_QUESTIONS Q22; H7).

A medication's reminders follow `reminder_timezone_mode`: "home" - always Ulaanbaatar time;
"local" - the profile's current time zone. That zone lives here, not on the phone, so the
patient's phone, a caregiver's phone and the server's monthly summary all turn one "08:00"
into the same instant. Each switch is a new row (append-only): a summary of last month is not
rewritten by today's trip.

- `effective_at` comes from the phone (a switch accepted offline arrives later): at most a
  week before the row is written, never after (API and CHECK). Such a late switch does move
  that week's doses to the zone the user was actually in; older days are never rewritten.
  Ties are broken by `seq` (the database's insertion order).
- At most 20 switches per profile in 24 hours (API; the monthly summary reads them all).
- `timezone` is an IANA name; the API checks it against the zone database, the table only its
  shape.
- recorded_by is set by the database (set_row_writer), never by the caller.

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-04
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = """
create table patient_timezones (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references patients on delete cascade,
  client_id uuid not null,
  seq bigint generated always as identity,
  timezone text not null
    check (length(timezone) between 1 and 64
           and timezone ~ '^[A-Za-z][A-Za-z0-9_+-]*(/[A-Za-z0-9_+-]+){0,2}$'),
  effective_at timestamptz not null check (effective_at >= timestamptz '2020-01-01 00:00Z'),
  recorded_by uuid references users on delete set null,
  created_at timestamptz not null default now(),
  unique (patient_id, client_id),
  -- a switch accepted offline arrives late, at most a week; never ahead of its writing
  check (effective_at between created_at - interval '7 days 1 hour'
                          and created_at + interval '10 minutes')
)
"""


def upgrade() -> None:
    op.execute(_TABLE)
    op.execute("create index on patient_timezones (patient_id, effective_at desc, seq desc)")
    op.execute(
        """create trigger patient_timezones_writer before insert on patient_timezones
           for each row execute function set_row_writer()"""
    )
    op.execute("alter table patient_timezones enable row level security")
    op.execute("alter table patient_timezones force row level security")
    op.execute(
        "create policy patient_timezones_owner on patient_timezones for all to labtrack_owner"
        " using (true) with check (true)"
    )
    # append-only: no update/delete policy and no grant (a switch is undone by a new switch)
    op.execute(
        """create policy patient_timezones_select on patient_timezones for select
           to labtrack_app using (can_read_patient(patient_id))"""
    )
    op.execute(
        """create policy patient_timezones_insert on patient_timezones for insert
           to labtrack_app with check (can_write_patient(patient_id))"""
    )
    op.execute("grant select on patient_timezones to labtrack_app")
    op.execute(
        "grant insert (patient_id, client_id, timezone, effective_at) on patient_timezones"
        " to labtrack_app"
    )
    op.execute("revoke truncate on patient_timezones from public")


def downgrade() -> None:
    op.execute("drop table patient_timezones")
