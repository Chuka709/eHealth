"""A doctor's targets and notes on a profile shared with them (Phase 7.4; docs/03
patient_targets, docs/04 §2 "doctor: тэмдэглэл, зорилт ✓"; hazard H15; Q61 f).

- written only by a registered doctor (users.role = 'doctor') holding live 'doctor' access to
  the profile - never by the owner, a caregiver or a viewer; through definer functions,
  audited by id only;
- read by everyone who can read the profile (the row policies);
- a target is a range in the test's catalog unit, in force from a day; a new one ends the one
  before (no row is changed otherwise; ending one sets valid_to). It is shown as the doctor's
  target, apart from the lab's range, and never changes a flag (rule 5, core/flags.py);
- a note is short text (≤ 2000), removed only by its author while still treating (kept,
  marked removed).

Revision ID: 0043
Revises: 0042
Create Date: 2026-11-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0043"
down_revision: str | None = "0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEFINER = "security definer set search_path = pg_catalog, public, pg_temp"

_TABLES = [
    """
    create table patient_targets (
      id uuid primary key default gen_random_uuid(),
      patient_id uuid not null references patients on delete cascade,
      test_code text not null references test_catalog,
      low numeric check (low >= 0),
      high numeric check (high >= 0),
      unit text not null check (length(unit) between 1 and 20),
      valid_from date not null,
      valid_to date,
      note text check (length(note) <= 500),
      set_by uuid references users on delete set null,
      created_at timestamptz not null default now(),
      check (low is not null or high is not null),
      check (low is null or high is null or low <= high),
      check (valid_to is null or valid_to >= valid_from)
    )
    """,
    "create index on patient_targets (patient_id, test_code, valid_from desc)",
    """
    create table doctor_notes (
      id uuid primary key default gen_random_uuid(),
      patient_id uuid not null references patients on delete cascade,
      author_id uuid references users on delete set null,
      body text not null check (length(btrim(body)) between 1 and 2000),
      created_at timestamptz not null default now(),
      removed_at timestamptz
    )
    """,
    "create index on doctor_notes (patient_id, created_at desc)",
]

# the caller: a registered doctor with live doctor access to profile p (not a minor's, whose
# profile the API keeps closed to everyone but its owner)
_IS_TREATING = """public.can_read_patient({p}) and exists (
        select 1 from public.patient_access a
        join public.users u on u.id = a.user_id
        join public.patients x on x.id = a.patient_id and x.deleted_at is null
        where a.patient_id = {p} and a.user_id = public.app_user_id() and a.level = 'doctor'
          and a.revoked_at is null and (a.expires_at is null or a.expires_at > now())
          and u.role = 'doctor' and u.account_status = 'active' and u.deleted_at is null
          and not coalesce(x.birth_date > public.local_today() - interval '18 years', false))"""

_FUNCTIONS = [
    f"""
    create function is_treating_doctor(p uuid) returns boolean
    language sql stable {_DEFINER} as $$
      select {_IS_TREATING.format(p="p")}
    $$
    """,
    f"""
    create function set_patient_target(p_patient uuid, p_test text, p_low numeric,
                                       p_high numeric, p_from date, p_note text)
    returns uuid language plpgsql volatile {_DEFINER} as $$
    declare
      t uuid;
      catalog_unit text;
    begin
      if not public.is_treating_doctor(p_patient) then
        raise exception 'not a treating doctor' using errcode = '42501';
      end if;
      -- from yesterday to a year ahead: a target never rewrites the days already shown
      if p_from < public.local_today() - 1 or p_from > public.local_today() + 365 then
        raise exception 'target day out of range' using errcode = '22008';
      end if;
      perform pg_advisory_xact_lock(hashtextextended(p_patient::text || p_test, 0));
      select c.canonical_unit into catalog_unit from public.test_catalog c
        where c.code = p_test and c.canonical_unit is not null;
      if catalog_unit is null then
        raise exception 'no unit for this test' using errcode = '22023';
      end if;
      -- beyond what the catalog holds possible at all: a typing error (8 entered as 80),
      -- never a clinical limit (rule 5)
      if exists (select 1 from public.test_catalog c where c.code = p_test
                 and c.physio_max is not null
                 and (p_low > c.physio_max or p_high > c.physio_max)) then
        raise exception 'target beyond the possible' using errcode = '22003';
      end if;
      -- a target already in force on or after that day: it ends the day before
      update public.patient_targets set valid_to = p_from - 1
        where patient_id = p_patient and test_code = p_test
          and valid_from < p_from and (valid_to is null or valid_to >= p_from);
      if exists (select 1 from public.patient_targets
                 where patient_id = p_patient and test_code = p_test
                   and valid_from >= p_from) then
        raise exception 'a later target exists' using errcode = '23505';
      end if;
      insert into public.patient_targets (patient_id, test_code, low, high, unit, valid_from,
                                          note, set_by)
        values (p_patient, p_test, p_low, p_high, catalog_unit, p_from, nullif(btrim(p_note), ''),
                public.app_user_id())
        returning id into t;
      perform public.caregiver_audit('target.set', 'patient_target', t::text, p_patient,
        jsonb_build_object('fields', jsonb_build_array('low', 'high', 'valid_from')));
      return t;
    end $$
    """,
    f"""
    create function end_patient_target(p_target uuid, p_on date) returns boolean
    language plpgsql volatile {_DEFINER} as $$
    declare
      pid uuid;
      setter uuid;
    begin
      -- any treating doctor of the profile may end it (care is shared), from yesterday on
      update public.patient_targets set valid_to = p_on
        where id = p_target and valid_to is null and valid_from <= p_on
          and p_on >= public.local_today() - 1
          and public.is_treating_doctor(patient_id)
        returning patient_id, set_by into pid, setter;
      if pid is null then
        return false;
      end if;
      perform public.caregiver_audit('target.end', 'patient_target', p_target::text, pid,
        jsonb_build_object('set_by_other', setter is distinct from public.app_user_id()));
      return true;
    end $$
    """,
    f"""
    create function add_doctor_note(p_patient uuid, p_body text) returns uuid
    language plpgsql volatile {_DEFINER} as $$
    declare
      n uuid;
    begin
      if not public.is_treating_doctor(p_patient) then
        raise exception 'not a treating doctor' using errcode = '42501';
      end if;
      insert into public.doctor_notes (patient_id, author_id, body)
        values (p_patient, public.app_user_id(), btrim(p_body))
        returning id into n;
      perform public.caregiver_audit('note.add', 'doctor_note', n::text, p_patient, null);
      return n;
    end $$
    """,
    f"""
    create function remove_doctor_note(p_note uuid) returns boolean
    language plpgsql volatile {_DEFINER} as $$
    declare
      pid uuid;
    begin
      update public.doctor_notes set removed_at = now()
        where id = p_note and removed_at is null and author_id = public.app_user_id()
          and public.is_treating_doctor(patient_id)
        returning patient_id into pid;
      if pid is null then
        return false;
      end if;
      perform public.caregiver_audit('note.remove', 'doctor_note', p_note::text, pid, null);
      return true;
    end $$
    """,
    # what readers see, with the doctor's name (users is not readable to them directly)
    f"""
    create function profile_targets(p uuid)
    returns table (id uuid, test_code text, low numeric, high numeric, unit text,
                   valid_from date, valid_to date, note text, set_by_name text,
                   created_at timestamptz)
    language sql stable {_DEFINER} as $$
      select t.id, t.test_code, t.low, t.high, t.unit, t.valid_from, t.valid_to, t.note,
             case when u.deleted_at is null then u.display_name end, t.created_at
      from public.patient_targets t
      left join public.users u on u.id = t.set_by
      where public.can_read_patient(p) and t.patient_id = p
      order by t.test_code, t.valid_from desc
    $$
    """,
    f"""
    create function profile_doctor_notes(p uuid)
    returns table (id uuid, body text, created_at timestamptz, author_name text, mine boolean)
    language sql stable {_DEFINER} as $$
      select n.id, n.body, n.created_at,
             case when u.deleted_at is null then u.display_name end,
             coalesce(n.author_id = public.app_user_id(), false)
      from public.doctor_notes n
      left join public.users u on u.id = n.author_id
      where public.can_read_patient(p) and n.patient_id = p and n.removed_at is null
      order by n.created_at desc limit 200
    $$
    """,
]

_APP = [
    "is_treating_doctor(uuid)",
    "set_patient_target(uuid, text, numeric, numeric, date, text)",
    "end_patient_target(uuid, date)",
    "add_doctor_note(uuid, text)",
    "remove_doctor_note(uuid)",
    "profile_targets(uuid)",
    "profile_doctor_notes(uuid)",
]


def upgrade() -> None:
    for sql in _TABLES:
        op.execute(sql)
    for table in ("patient_targets", "doctor_notes"):
        op.execute(f"alter table {table} enable row level security")
        op.execute(f"alter table {table} force row level security")
        op.execute(
            f"create policy {table}_owner on {table} for all to labtrack_owner"
            " using (true) with check (true)"
        )
        op.execute(f"revoke truncate on {table} from public")
    # read by whoever reads the profile; written only through the functions
    op.execute(
        "create policy patient_targets_select on patient_targets for select to labtrack_app"
        " using (can_read_patient(patient_id))"
    )
    op.execute(
        "create policy doctor_notes_select on doctor_notes for select to labtrack_app"
        " using (can_read_patient(patient_id) and removed_at is null)"
    )
    op.execute("grant select on patient_targets, doctor_notes to labtrack_app")
    for sql in _FUNCTIONS:
        op.execute(sql)
    for name in _APP:
        op.execute(f"revoke execute on function {name} from public")
    op.execute(f"grant execute on function {', '.join(_APP)} to labtrack_app")


def downgrade() -> None:
    for name in reversed(_APP):
        op.execute(f"drop function {name}")
    op.execute("drop table doctor_notes")
    op.execute("drop table patient_targets")
