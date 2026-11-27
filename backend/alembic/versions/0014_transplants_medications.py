"""Transplants, medications, dose history and intakes (Phase 2.1; docs/03 ШИЛЖҮҮЛЭН СУУЛГАЛТ, ЭМ).

All four are health data of one profile: ENABLE + FORCE RLS, policies on can_read_patient /
can_write_patient, nothing for the admin roles (CLAUDE.md 2a).

- Rows that point at another health row use a composite FK (child_id, patient_id) ->
  parent (id, patient_id): a row can never be linked to another patient's row (IDOR).
- Every create carries a device-made `client_id` (unique per patient): a retried request
  (offline queue, flaky network, the notification's "Уусан" button) finds the stored row.
- medication_regimens is append-only (CLAUDE.md rule 10): a dose change, or a correction, is a
  new row; the regimen in force on a day is the latest row with effective_from <= that day
  (by effective_from, then seq). No effective_to column - nothing to update.
- medication_regimens order: (effective_from, seq) - seq is the database's insertion order.
  Every table keeps who added a row (recorded_by) and, where rows change, who last changed it
  (updated_by); deleting a medication or a transplant (and with it its history) is the owner's
  alone, and a taken dose is deleted only by whoever recorded it or the owner.
- medication_intakes: one row per (patient, medication, scheduled time); the merge rule
  (`taken` wins, hazard H20) lives in core/intakes.py and is also enforced here (taken never
  becomes skipped). recorded_by (first writer) and updated_by are set by the database.
- Columns are granted one by one (INSERT and UPDATE): ids, timestamps and writers are the
  database's.
- Free text is bounded (domains) so a stolen session cannot fill the database.

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-04
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TYPES = [
    """create type organ as enum ('kidney','liver','heart','lung','pancreas','kidney_pancreas',
                                  'intestine','cornea','hsct','other')""",
    """create type donor_type as enum ('living_related','living_unrelated','deceased_dbd',
                                       'deceased_dcd','unknown')""",
    "create type graft_status as enum ('functioning','failed','removed','unknown')",
    "create domain short_text as text check (length(value) between 1 and 200)",
    "create domain long_text as text check (length(value) between 1 and 4000)",
    """create domain serostatus as text check (value in ('pos','neg','unknown'))""",
    """create domain blood_type as text
       check (value in ('O+','O-','A+','A-','B+','B-','AB+','AB-','unknown'))""",
]

_TABLES = [
    """
    create table transplants (
      id uuid primary key default gen_random_uuid(),
      patient_id uuid not null references patients on delete cascade,
      client_id uuid not null,
      organ organ not null,
      organ_detail short_text,
      transplant_date date not null,
      date_precision text not null default 'day'
        check (date_precision in ('day','month','year')),
      country text not null check (country ~ '^[A-Z]{2}$'),
      city short_text, hospital short_text not null, surgeon short_text,
      transplant_number int not null default 1 check (transplant_number between 1 and 20),
      donor_type donor_type not null default 'unknown',
      donor_relation short_text,
      recipient_blood_type blood_type, donor_blood_type blood_type,
      abo_incompatible boolean,
      cmv_donor serostatus, cmv_recipient serostatus,
      ebv_donor serostatus, ebv_recipient serostatus,
      hla_mismatch short_text,
      primary_disease short_text,
      pre_transplant_dialysis short_text,
      induction_therapy short_text,
      graft_status graft_status not null default 'functioning',
      graft_status_date date, graft_failure_reason short_text,
      follow_up_center short_text, follow_up_doctor short_text,
      notes long_text,
      recorded_by uuid references users on delete set null,
      updated_by uuid references users on delete set null,
      created_at timestamptz not null default now(), updated_at timestamptz,
      unique (id, patient_id),
      unique (patient_id, client_id),
      -- a month or a year only: stored as its first day, so sorting and "since" stay exact
      check (date_precision = 'day'
             or (date_precision = 'month' and extract(day from transplant_date) = 1)
             or (date_precision = 'year' and extract(doy from transplant_date) = 1)),
      check (transplant_date >= date '1950-01-01'),
      check (graft_status_date is null or graft_status_date >= transplant_date)
    )
    """,
    "create index on transplants (patient_id, transplant_date desc)",
    """
    create table medications (
      id uuid primary key default gen_random_uuid(),
      patient_id uuid not null references patients on delete cascade,
      client_id uuid not null,
      catalog_code text references medication_catalog,
      name short_text not null,
      brand short_text, form short_text, strength short_text,
      route short_text not null default 'oral',
      purpose short_text,
      prescribed_by short_text,
      transplant_id uuid,
      started_on date, stopped_on date, stop_reason short_text,
      is_long_term boolean not null default true,
      reminders_enabled boolean not null default false,
      reminder_timezone_mode text not null default 'home'
        check (reminder_timezone_mode in ('home','local')),
      notes long_text,
      recorded_by uuid references users on delete set null,
      updated_by uuid references users on delete set null,
      created_at timestamptz not null default now(), updated_at timestamptz,
      unique (id, patient_id),
      unique (patient_id, client_id),
      foreign key (transplant_id, patient_id) references transplants (id, patient_id)
        on delete set null (transplant_id),
      check (stopped_on is null or started_on is null or stopped_on >= started_on),
      check (stop_reason is null or stopped_on is not null)
    )
    """,
    "create index on medications (patient_id, stopped_on nulls first, started_on desc)",
    """
    create table medication_regimens (
      id uuid primary key default gen_random_uuid(),
      patient_id uuid not null references patients on delete cascade,
      medication_id uuid not null,
      client_id uuid not null,
      -- insertion order, set by the database: breaks ties between rows with the same
      -- effective_from even within one transaction (created_at is the transaction start)
      seq bigint generated always as identity,
      effective_from date not null check (effective_from >= date '1950-01-01'),
      dose_amount numeric
        check (dose_amount > 0 and dose_amount < 100000 and scale(dose_amount) <= 4),
      dose_unit short_text,
      schedule jsonb not null
        check (jsonb_typeof(schedule) = 'object'
               and pg_column_size(schedule) <= 2000
               -- coalesce: a missing key gives NULL, and a NULL check passes
               and coalesce(schedule->>'type' = 'prn'
                    or (schedule->>'type' in ('daily','weekly')
                        and jsonb_typeof(schedule->'times') = 'array'
                        and jsonb_array_length(schedule->'times') between 1 and 12), false)
               and coalesce(schedule->>'type' <> 'weekly'
                    or (jsonb_typeof(schedule->'days') = 'array'
                        and jsonb_array_length(schedule->'days') between 1 and 7), false)),
      instructions long_text,
      changed_by_note long_text,
      recorded_by uuid references users on delete set null,
      created_at timestamptz not null default now(),
      unique (patient_id, client_id),
      foreign key (medication_id, patient_id) references medications (id, patient_id)
        on delete cascade,
      check ((dose_amount is null) = (dose_unit is null))
    )
    """,
    "create index on medication_regimens (medication_id, effective_from desc, seq desc)",
    "create index on medication_regimens (patient_id)",
    """
    create table medication_intakes (
      id uuid primary key default gen_random_uuid(),
      patient_id uuid not null references patients on delete cascade,
      medication_id uuid not null,
      client_id uuid not null,
      scheduled_at timestamptz check (scheduled_at >= timestamptz '2000-01-01 00:00Z'),
      taken_at timestamptz check (taken_at >= timestamptz '2000-01-01 00:00Z'),
      status text not null check (status in ('taken','skipped','late')),
      note long_text,
      recorded_by uuid references users on delete set null,   -- who first wrote it
      updated_by uuid references users on delete set null,    -- who last changed it
      created_at timestamptz not null default now(), updated_at timestamptz,
      unique (patient_id, client_id),
      -- with patient_id: a conflict can only ever be with one's own rows (no oracle on another
      -- patient's intakes through a guessed medication id)
      unique (patient_id, medication_id, scheduled_at),
      foreign key (medication_id, patient_id) references medications (id, patient_id)
        on delete cascade,
      check ((status = 'skipped') = (taken_at is null)),
      check (scheduled_at is not null or status = 'taken')   -- as-needed (prn) doses
    )
    """,
    "create index on medication_intakes (patient_id, scheduled_at desc)",
    "create index on medication_intakes (medication_id, taken_at desc)",
]

_FUNCTIONS = [
    """
    create function touch_updated_at() returns trigger language plpgsql
    set search_path = pg_catalog, public, pg_temp as $$
    begin
      new.updated_at := now();
      return new;
    end $$
    """,
    # Who wrote a row is the database's to say, never the caller's (as for patient_access).
    # Whenever a user context is set - the app, or a definer function acting for the user -
    # the acting user is recorded; only migrations/maintenance (no user) keep what they give.
    """
    create function set_row_writer() returns trigger language plpgsql
    set search_path = pg_catalog, public, pg_temp as $$
    begin
      -- not for the database's own updates (a purged user's FK set null runs this at depth 2)
      if pg_trigger_depth() > 1 then
        return new;
      end if;
      if public.app_user_id() is not null or current_user = 'labtrack_app' then
        if tg_op = 'INSERT' then
          new.recorded_by := public.app_user_id();
        else
          new.recorded_by := old.recorded_by;
          new.updated_by := public.app_user_id();
        end if;
      end if;
      return new;
    end $$
    """,
    # H20 in the database too: a dose recorded as taken is never turned into skipped (a
    # second device's "алгассан" loses). A mistaken "Уусан" is undone by deleting the row.
    """
    create function medication_intakes_taken_stays() returns trigger language plpgsql
    set search_path = pg_catalog, public, pg_temp as $$
    begin
      if old.status in ('taken','late') and new.status = 'skipped' then
        raise exception 'a taken dose stays taken' using errcode = '23514';
      end if;
      return new;
    end $$
    """,
    """create trigger transplants_touch before update on transplants
       for each row execute function touch_updated_at()""",
    """create trigger medications_touch before update on medications
       for each row execute function touch_updated_at()""",
    """create trigger medication_intakes_touch before update on medication_intakes
       for each row execute function touch_updated_at()""",
    """create trigger medication_intakes_writer before insert or update on medication_intakes
       for each row execute function set_row_writer()""",
    """create trigger transplants_writer before insert or update on transplants
       for each row execute function set_row_writer()""",
    """create trigger medications_writer before insert or update on medications
       for each row execute function set_row_writer()""",
    """create trigger medication_regimens_writer before insert on medication_regimens
       for each row execute function set_row_writer()""",
    """create trigger medication_intakes_taken before update on medication_intakes
       for each row execute function medication_intakes_taken_stays()""",
]
_TRIGGER_FUNCTIONS = ("touch_updated_at", "set_row_writer", "medication_intakes_taken_stays")

_RLS_TABLES = ["transplants", "medications", "medication_regimens", "medication_intakes"]
# medication_regimens: append-only (no update/delete policy, no grant); rows go with their
# medication (FK cascade).
_APPEND_ONLY = {"medication_regimens"}
# Deleting a transplant or a medication erases its history (dose history, intakes): only the
# profile's owner may; a caregiver stops a medication (stopped_on) instead.
_OWNER_DELETES = {"transplants", "medications"}

# Columns are granted one by one, for INSERT as for UPDATE: id, created_at, updated_at, seq,
# recorded_by/updated_by are the database's (a caller-chosen id would probe for other rows'
# ids; a caller-chosen created_at would reorder history). id, patient_id, client_id never
# change. (A table-wide grant would cover every column; a column REVOKE after it does nothing.)
_TRANSPLANT_EDITABLE = (
    "organ, organ_detail, transplant_date, date_precision, country, city, hospital, surgeon,"
    " transplant_number, donor_type, donor_relation, recipient_blood_type, donor_blood_type,"
    " abo_incompatible, cmv_donor, cmv_recipient, ebv_donor, ebv_recipient, hla_mismatch,"
    " primary_disease, pre_transplant_dialysis, induction_therapy, graft_status,"
    " graft_status_date, graft_failure_reason, follow_up_center, follow_up_doctor, notes"
)
_MEDICATION_EDITABLE = (
    "catalog_code, name, brand, form, strength, route, purpose, prescribed_by, transplant_id,"
    " started_on, stopped_on, stop_reason, is_long_term, reminders_enabled,"
    " reminder_timezone_mode, notes"
)
_REGIMEN_INSERT = (
    "patient_id, medication_id, client_id, effective_from, dose_amount, dose_unit, schedule,"
    " instructions, changed_by_note"
)
_INTAKE_EDITABLE = "status, taken_at, note"

_GRANTS = [
    "grant select, delete on transplants to labtrack_app",
    f"grant insert (patient_id, client_id, {_TRANSPLANT_EDITABLE}) on transplants to labtrack_app",
    f"grant update ({_TRANSPLANT_EDITABLE}) on transplants to labtrack_app",
    "grant select, delete on medications to labtrack_app",
    f"grant insert (patient_id, client_id, {_MEDICATION_EDITABLE}) on medications to labtrack_app",
    f"grant update ({_MEDICATION_EDITABLE}) on medications to labtrack_app",
    "grant select on medication_regimens to labtrack_app",
    f"grant insert ({_REGIMEN_INSERT}) on medication_regimens to labtrack_app",
    "grant select, delete on medication_intakes to labtrack_app",
    "grant insert (patient_id, medication_id, client_id, scheduled_at,"
    f" {_INTAKE_EDITABLE}) on medication_intakes to labtrack_app",
    f"grant update ({_INTAKE_EDITABLE}) on medication_intakes to labtrack_app",
]


def _delete_check(table: str) -> str:
    if table in _OWNER_DELETES:
        return "is_owner(patient_id)"
    if table == "medication_intakes":
        # "Буцаах" undoes one's own tap; another device cannot erase a recorded dose (H20)
        return (
            "can_write_patient(patient_id) and (status = 'skipped'"
            " or recorded_by = app_user_id() or is_owner(patient_id))"
        )
    return "can_write_patient(patient_id)"


def _policies(table: str) -> list[str]:
    out = [
        f"""create policy {table}_select on {table} for select to labtrack_app
            using (can_read_patient(patient_id))""",
        f"""create policy {table}_insert on {table} for insert to labtrack_app
            with check (can_write_patient(patient_id))""",
    ]
    if table not in _APPEND_ONLY:
        out += [
            f"""create policy {table}_update on {table} for update to labtrack_app
                using (can_write_patient(patient_id)) with check (can_write_patient(patient_id))""",
            f"""create policy {table}_delete on {table} for delete to labtrack_app
                using ({_delete_check(table)})""",
        ]
    return out


def upgrade() -> None:
    for sql in _TYPES + _TABLES + _FUNCTIONS:
        op.execute(sql)
    for table in _RLS_TABLES:
        op.execute(f"alter table {table} enable row level security")
        op.execute(f"alter table {table} force row level security")
        op.execute(
            f"create policy {table}_owner on {table} for all to labtrack_owner "
            "using (true) with check (true)"
        )
        for sql in _policies(table):
            op.execute(sql)
    for sql in _GRANTS:
        op.execute(sql)
    for fn in _TRIGGER_FUNCTIONS:
        op.execute(f"revoke execute on function {fn}() from public")
    op.execute("revoke truncate on all tables in schema public from public")


def downgrade() -> None:
    for table in reversed(_RLS_TABLES):
        op.execute(f"drop table {table}")
    for fn in _TRIGGER_FUNCTIONS:
        op.execute(f"drop function {fn}()")
    for name in ("blood_type", "serostatus", "long_text", "short_text"):
        op.execute(f"drop domain {name}")
    for name in ("graft_status", "donor_type", "organ"):
        op.execute(f"drop type {name}")
