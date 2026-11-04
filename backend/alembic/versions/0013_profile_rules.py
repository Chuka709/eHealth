"""Profiles a user may create (Phase 2.0; docs/04 §2, Q9).

create_patient() (0002) accepted any relation and any number of profiles. An owner holds
exactly two kinds of profile: their own ('self', at most one, an adult's) and a minor child's
('child', born within the last 18 years). An adult relative is a person with their own account
who can share their profile (caregiver access) - nobody owns another adult's health record. A
cap on profiles per creator keeps a stolen session from filling the database.

Also (security review 2.0):
- "Today" is the Ulaanbaatar date everywhere (the database runs in UTC): a child turns 18 on
  their birthday in Mongolia, for consent and for the API alike (`local_today()`).
- is_minor_patient() answers only for profiles the caller can read (it was an oracle on any
  profile id).
- A birth date filled in later that is a minor's is invalid input (22023), not a lock (42501).
- `relation` is no longer writable: a 'child' could otherwise be relabelled around the rules.

The partial unique index is the backstop against two concurrent 'self' creations.

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-04
"""

import importlib.util
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MAX_PROFILES = 10


def _revision(filename: str) -> ModuleType:
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_M2 = _revision("0002_auth_and_profiles.py")

# Not a definer and not security sensitive: grant to the runtime roles that use it.
_LOCAL_TODAY = """
create function local_today() returns date language sql stable
set search_path = pg_catalog, public, pg_temp as
$$ select (now() at time zone 'Asia/Ulaanbaatar')::date $$
"""

_IS_MINOR = f"""
create or replace function is_minor_patient(p uuid) returns boolean language sql stable
{_M2._DEFINER} as $$
  -- Evaluated at check time: a child's profile stops being a minor's on the 18th birthday
  -- (Ulaanbaatar date). Only for profiles the caller can read.
  select public.can_read_patient(p)
     and coalesce((select birth_date > public.local_today() - interval '18 years'
                   from public.patients where id = p), false)
$$
"""

_BIRTH_DATE_ONCE = """
create or replace function patients_birth_date_once() returns trigger language plpgsql as $$
begin
  if current_user = 'labtrack_app' and new.birth_date is distinct from old.birth_date then
    if old.birth_date is not null then
      raise exception 'birth date cannot be changed' using errcode = '42501';
    end if;
    if new.birth_date is null
       or new.birth_date > public.local_today() - interval '18 years'
       or new.birth_date < date '1900-01-01' then
      raise exception 'invalid birth date' using errcode = '22023';
    end if;
  end if;
  return new;
end $$
"""

_CREATE_PATIENT = f"""
create or replace function create_patient(p_full_name text, p_relation text,
                                          p_birth_date date, p_sex sex)
returns uuid language plpgsql volatile {_M2._DEFINER} as $$
declare
  uid uuid := public.app_user_id();
  today date := public.local_today();
  adult_from date := today - interval '18 years';
  pid uuid;
begin
  if uid is null then
    raise exception 'no user context' using errcode = '42501';
  end if;
  if p_relation is null or p_relation not in ('self', 'child')
     or p_full_name is null or length(btrim(p_full_name)) not between 1 and 100
     or p_birth_date < date '1900-01-01' or p_birth_date > today
     or (p_relation = 'self' and p_birth_date > adult_from)
     or (p_relation = 'child' and (p_birth_date is null or p_birth_date <= adult_from)) then
    raise exception 'invalid profile' using errcode = '22023';
  end if;
  -- one creator at a time, so the count and the 'self' check hold
  perform pg_advisory_xact_lock(hashtext('create_patient'), hashtext(uid::text));
  if (select count(*) from public.patients
      where created_by = uid and deleted_at is null) >= {MAX_PROFILES} then
    raise exception 'too many profiles' using errcode = '54000';
  end if;
  if p_relation = 'self' and exists (select 1 from public.patients
      where created_by = uid and relation = 'self' and deleted_at is null) then
    raise exception 'own profile exists' using errcode = '23505';
  end if;
  insert into public.patients (full_name, relation, birth_date, sex, created_by)
    values (btrim(p_full_name), p_relation, p_birth_date, p_sex, uid)
    returning id into pid;
  insert into public.patient_access (patient_id, user_id, level, scopes, granted_by)
    values (pid, uid, 'owner', '{{*}}', uid);
  return pid;
end $$
"""

_SELF_INDEX = (
    "create unique index patients_one_self on patients (created_by)"
    " where relation = 'self' and deleted_at is null"
)


def _original(name: str, statements: list[str]) -> str:
    (sql,) = [s for s in statements if f"create function {name}(" in s]
    return str(sql).replace("create function", "create or replace function", 1)


# Rows the new rules would leave inconsistent (none exist: profiles had no API before 0013).
# Stop with a clear error rather than half-apply; such rows are fixed by support first.
_PRECHECK = """
do $$ begin
  if exists (select 1 from patients where deleted_at is null
             and (relation is null or relation not in ('self', 'child')
                  or (relation = 'child' and birth_date is null)))
     or exists (select created_by from patients
                where relation = 'self' and deleted_at is null
                group by created_by having count(*) > 1) then
    raise exception '0013: profiles break the new rules - fix them before upgrading';
  end if;
end $$
"""


def upgrade() -> None:
    op.execute(_PRECHECK)
    op.execute(_LOCAL_TODAY)
    op.execute("revoke execute on function local_today() from public")
    op.execute("grant execute on function local_today() to labtrack_app")
    op.execute(_IS_MINOR)
    op.execute(_BIRTH_DATE_ONCE)
    op.execute(_CREATE_PATIENT)
    op.execute(_SELF_INDEX)
    op.execute("revoke update (relation) on patients from labtrack_app")


def downgrade() -> None:
    op.execute("grant update (relation) on patients to labtrack_app")
    op.execute("drop index patients_one_self")
    op.execute(_original("create_patient", _M2._FUNCTIONS))
    op.execute(_original("patients_birth_date_once", _M2._FUNCTIONS))
    op.execute(_original("is_minor_patient", _M2._FUNCTIONS))
    op.execute("drop function local_today()")
