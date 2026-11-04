"""Clinical events, vitals, allergies, emergency contacts, appointments, questions (Phase 2.6).

docs/03 (ЭМЧИЛГЭЭ, АМИН ҮЗҮҮЛЭЛТ, ХАРШИЛ, ТОВЛОЛ, АСУУЛТ, ЯАРАЛТАЙ ХОЛБОО), as in 0014:

- every row has `client_id` + unique (patient_id, client_id): a retried offline write finds
  the stored row;
- columns are granted one by one: id, created_at/updated_at, recorded_by/updated_by are the
  database's (set_row_writer, touch_updated_at); id, patient_id, client_id never change;
- links to another PHI row are composite (child, patient_id) -> parent (id, patient_id), so a
  row never points at another profile's row;
- vitals: a fixed unit per kind and a plausibility range per kind (user decision 2026-11-04):
  catches a typo (1200 mmHg), never a "normal range" - the app does not judge a value
  (CLAUDE.md rule 5/10). Glucose in mmol/L only. A wrong vital is deleted and entered again
  (no update). The ranges are repeated in the API (core/vitals.py) - one source for messages.
- links to documents/lab reports (clinical_events.related_document_id,
  appointments.linked_report_id) come with Phase 3/4.

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TYPES = [
    """create type clinical_event_kind as enum (
         'biopsy','rejection','infection','hospitalization','dialysis','plasmapheresis','ivig',
         'surgery','procedure','vaccination','complication','other')""",
    """create type vital_kind as enum ('bp_systolic','bp_diastolic','pulse','weight',
         'temperature','glucose','spo2','urine_output','fluid_intake')""",
]

# (kind, unit, low, high, max decimals) - plausibility only, never a normal range
VITALS = [
    ("bp_systolic", "mmHg", 40, 300, 0),
    ("bp_diastolic", "mmHg", 20, 200, 0),
    ("pulse", "bpm", 20, 300, 0),
    ("weight", "kg", 1, 400, 2),
    ("temperature", "C", 30, 45, 1),
    ("glucose", "mmol_L", "0.5", 50, 1),
    ("spo2", "percent", 50, 100, 0),
    ("urine_output", "ml", 0, 20000, 0),
    ("fluid_intake", "ml", 0, 20000, 0),
]
_VITAL_CHECK = " or ".join(
    f"(kind = '{k}' and unit = '{u}' and value between {lo} and {hi} and scale(value) <= {d})"
    for k, u, lo, hi, d in VITALS
)

_TABLES = [
    """
    create table clinical_events (
      id uuid primary key default gen_random_uuid(),
      patient_id uuid not null references patients on delete cascade,
      client_id uuid not null,
      transplant_id uuid,
      kind clinical_event_kind not null,
      title short_text not null,
      started_on date not null check (started_on >= date '1950-01-01'),
      ended_on date,
      place short_text,
      description long_text,
      outcome long_text,
      recorded_by uuid references users on delete set null,
      updated_by uuid references users on delete set null,
      created_at timestamptz not null default now(),
      updated_at timestamptz,
      unique (patient_id, client_id),
      foreign key (transplant_id, patient_id) references transplants (id, patient_id)
        on delete set null (transplant_id),
      check (ended_on is null or ended_on >= started_on)
    )
    """,
    "create index on clinical_events (patient_id, started_on desc)",
    f"""
    create table vitals (
      id uuid primary key default gen_random_uuid(),
      patient_id uuid not null references patients on delete cascade,
      client_id uuid not null,
      kind vital_kind not null,
      value numeric not null,
      unit text not null,
      measured_at timestamptz not null check (measured_at >= timestamptz '2000-01-01 00:00Z'),
      -- one blood-pressure reading: systolic + diastolic (+ pulse) share it
      group_id uuid,
      source text not null default 'manual'
        check (source in ('manual','apple_health','health_connect')),
      note short_text,
      recorded_by uuid references users on delete set null,
      created_at timestamptz not null default now(),
      unique (patient_id, client_id),
      check ({_VITAL_CHECK})
    )
    """,
    "create index on vitals (patient_id, kind, measured_at desc)",
    """create unique index vitals_one_kind_per_reading on vitals (patient_id, group_id, kind)
       where group_id is not null""",
    """
    create table allergies (
      id uuid primary key default gen_random_uuid(),
      patient_id uuid not null references patients on delete cascade,
      client_id uuid not null,
      substance short_text not null,
      reaction short_text,
      severity text check (severity in ('mild','moderate','severe','unknown')),
      noted_on date check (noted_on >= date '1900-01-01'),
      recorded_by uuid references users on delete set null,
      updated_by uuid references users on delete set null,
      created_at timestamptz not null default now(),
      updated_at timestamptz,
      unique (patient_id, client_id)
    )
    """,
    "create index on allergies (patient_id)",
    """
    create table emergency_contacts (
      id uuid primary key default gen_random_uuid(),
      patient_id uuid not null references patients on delete cascade,
      client_id uuid not null,
      name short_text not null,
      relation short_text,
      -- digits with an optional leading +, spaces, dashes, brackets: dialled as written
      phone text not null check (phone ~ '^\\+?[0-9][0-9 ()-]{3,22}[0-9]$'),
      is_transplant_center boolean not null default false,
      sort_order int not null default 0 check (sort_order between 0 and 100),
      recorded_by uuid references users on delete set null,
      updated_by uuid references users on delete set null,
      created_at timestamptz not null default now(),
      updated_at timestamptz,
      unique (patient_id, client_id)
    )
    """,
    "create index on emergency_contacts (patient_id, sort_order)",
    """
    create table appointments (
      id uuid primary key default gen_random_uuid(),
      patient_id uuid not null references patients on delete cascade,
      client_id uuid not null,
      kind text not null check (kind in ('lab','clinic_visit','biopsy','imaging','other')),
      title short_text not null,
      scheduled_at timestamptz not null check (scheduled_at >= timestamptz '2000-01-01 00:00Z'),
      place short_text,
      notes long_text,
      -- minutes before: 1 day and 2 hours by default; at most 4, at most 7 days before
      reminder_offsets_min int[] not null default '{1440,120}'
        check (cardinality(reminder_offsets_min) <= 4
               and 0 <= all(reminder_offsets_min) and 10080 >= all(reminder_offsets_min)),
      status text not null default 'planned' check (status in ('planned','done','cancelled')),
      recorded_by uuid references users on delete set null,
      updated_by uuid references users on delete set null,
      created_at timestamptz not null default now(),
      updated_at timestamptz,
      unique (patient_id, client_id),
      unique (id, patient_id)
    )
    """,
    "create index on appointments (patient_id, scheduled_at)",
    """
    create table doctor_questions (
      id uuid primary key default gen_random_uuid(),
      patient_id uuid not null references patients on delete cascade,
      client_id uuid not null,
      text long_text not null,
      answer long_text,
      appointment_id uuid,
      status text not null default 'open' check (status in ('open','answered','dropped')),
      recorded_by uuid references users on delete set null,
      updated_by uuid references users on delete set null,
      created_at timestamptz not null default now(),
      updated_at timestamptz,
      unique (patient_id, client_id),
      foreign key (appointment_id, patient_id) references appointments (id, patient_id)
        on delete set null (appointment_id)
    )
    """,
    "create index on doctor_questions (patient_id, status)",
]

_EDITABLE = {
    "clinical_events": "transplant_id, kind, title, started_on, ended_on, place, description,"
    " outcome",
    "allergies": "substance, reaction, severity, noted_on",
    "emergency_contacts": "name, relation, phone, is_transplant_center, sort_order",
    "appointments": "kind, title, scheduled_at, place, notes, reminder_offsets_min, status",
    "doctor_questions": "text, answer, appointment_id, status",
}
_VITAL_INSERT = "patient_id, client_id, kind, value, unit, measured_at, group_id, note"
# History and the emergency card's data are erased only by the profile's owner or by whoever
# wrote the row (a caregiver corrects their own entry, never the owner's) - as intakes (H20).
_WRITER_DELETES = {"clinical_events", "allergies", "emergency_contacts", "vitals"}
_RLS_TABLES = [
    "clinical_events",
    "vitals",
    "allergies",
    "emergency_contacts",
    "appointments",
    "doctor_questions",
]


def upgrade() -> None:
    for sql in _TYPES:
        op.execute(sql)
    for sql in _TABLES:
        op.execute(sql)
    for table in _RLS_TABLES:
        op.execute(f"alter table {table} enable row level security")
        op.execute(f"alter table {table} force row level security")
        op.execute(
            f"create policy {table}_owner on {table} for all to labtrack_owner"
            " using (true) with check (true)"
        )
        op.execute(
            f"""create policy {table}_select on {table} for select to labtrack_app
                using (can_read_patient(patient_id))"""
        )
        op.execute(
            f"""create policy {table}_insert on {table} for insert to labtrack_app
                with check (can_write_patient(patient_id))"""
        )
        check = (
            "can_write_patient(patient_id) and (is_owner(patient_id)"
            " or recorded_by = app_user_id())"
            if table in _WRITER_DELETES
            else "can_write_patient(patient_id)"
        )
        op.execute(
            f"create policy {table}_delete on {table} for delete to labtrack_app using ({check})"
        )
        op.execute(f"grant select, delete on {table} to labtrack_app")
        op.execute(f"revoke truncate on {table} from public")
        op.execute(
            f"""create trigger {table}_writer before insert or update on {table}
                for each row execute function set_row_writer()"""
            if table != "vitals"
            else f"""create trigger {table}_writer before insert on {table}
                for each row execute function set_row_writer()"""
        )
    for table, cols in _EDITABLE.items():
        op.execute(
            f"""create policy {table}_update on {table} for update to labtrack_app
                using (can_write_patient(patient_id)) with check (can_write_patient(patient_id))"""
        )
        op.execute(f"grant insert (patient_id, client_id, {cols}) on {table} to labtrack_app")
        op.execute(f"grant update ({cols}) on {table} to labtrack_app")
        op.execute(
            f"""create trigger {table}_touch before update on {table}
                for each row execute function touch_updated_at()"""
        )
    # vitals: entered, or deleted when wrong - never edited
    op.execute(f"grant insert ({_VITAL_INSERT}) on vitals to labtrack_app")


def downgrade() -> None:
    for table in reversed(_RLS_TABLES):
        op.execute(f"drop table {table}")
    op.execute("drop type vital_kind")
    op.execute("drop type clinical_event_kind")
