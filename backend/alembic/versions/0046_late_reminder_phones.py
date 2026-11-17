"""A caregiver's dose alert waits at least 90 minutes when the owner's phone may be late (Q48).

Physician decision (2026-11-18, ★ Б): on Android without the exact-alarm permission a medicine
reminder can come up to about an hour late, so a caregiver alert after 30 minutes could reach
the caregiver before the reminder reached the patient. Adherence studies count a dose taken
within ±2 hours of its time as on time. So:

- each device tells the server whether it can schedule exact alarms (device_alarm_states, one
  row per session family - it outlives refresh rotations; iOS always can);
- when every live device of the owner that told says it cannot, the owner's reminders may be
  late: maint_caregiver_alert_targets() gives at least 90 minutes (a later choice is kept), and
  the caregiver's alert settings say so (owner_reminders_may_be_late()).

A device that never told counts as unknown, never as late: an owner with no report keeps the
caregiver's own choice (nothing changes for iOS, the web or an older app).

Revision ID: 0046
Revises: 0045
Create Date: 2026-11-18
"""

import importlib.util
from collections.abc import Sequence
from pathlib import Path

from alembic import op

revision: str = "0046"
down_revision: str | None = "0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEFINER = "security definer set search_path = pg_catalog, public, pg_temp"
LATE_PHONE_MIN = 90

# the owner's live devices that told the server: none can schedule exact alarms
_LATE = """(exists (
        select 1 from public.device_alarm_states d
        where d.user_id = {owner} and not d.exact_alarms
          and exists (select 1 from public.sessions s where s.family_id = d.family_id
                      and s.revoked_at is null and s.expires_at > now()))
      and not exists (
        select 1 from public.device_alarm_states d
        where d.user_id = {owner} and d.exact_alarms
          and exists (select 1 from public.sessions s where s.family_id = d.family_id
                      and s.revoked_at is null and s.expires_at > now())))"""

_OWNER_OF = """(select o.user_id from public.patient_access o
        where o.patient_id = {p} and o.level = 'owner' and o.revoked_at is null limit 1)"""


def _targets_0026() -> str:
    path = Path(__file__).with_name("0026_alert_targets_consent.py")
    spec = importlib.util.spec_from_file_location("m0026", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sql: str = module._targets(consent_filter=True)
    return sql


def _targets_late() -> str:
    sql = _targets_0026()
    old = "      select s.patient_id, s.caregiver_user_id, s.missed_dose_after_min\n"
    if old not in sql:
        raise RuntimeError("0026 select changed")
    late = _LATE.format(owner=_OWNER_OF.format(p="s.patient_id"))
    new = (
        "      select s.patient_id, s.caregiver_user_id,\n"
        f"        case when {late}\n"
        f"          then greatest(s.missed_dose_after_min, {LATE_PHONE_MIN})\n"
        "          else s.missed_dose_after_min end\n"
    )
    return sql.replace(old, new)


_UP = [
    """
    create table device_alarm_states (
      family_id uuid primary key,
      user_id uuid not null references users on delete cascade,
      exact_alarms boolean not null,
      updated_at timestamptz not null default now()
    )
    """,
    "alter table device_alarm_states enable row level security",
    "alter table device_alarm_states force row level security",
    """create policy device_alarm_states_own on device_alarm_states for select to labtrack_app
       using (user_id = app_user_id())""",
    "grant select on device_alarm_states to labtrack_app",
    # the definer functions (owned by labtrack_owner) write and read through forced RLS
    """create policy device_alarm_states_owner on device_alarm_states for all to labtrack_owner
       using (true) with check (true)""",
    "revoke truncate on device_alarm_states from public",
    f"""
    create function set_device_exact_alarms(p_session uuid, p_exact boolean) returns boolean
    language plpgsql volatile {_DEFINER} as $$
    declare
      fam uuid;
    begin
      select s.family_id into fam from public.sessions s
        where s.id = p_session and s.user_id = public.app_user_id()
          and s.revoked_at is null and s.expires_at > now();
      if fam is null or p_exact is null then
        return false;
      end if;
      insert into public.device_alarm_states (family_id, user_id, exact_alarms)
        values (fam, public.app_user_id(), p_exact)
        on conflict (family_id) do update
          set exact_alarms = excluded.exact_alarms, updated_at = now()
          where device_alarm_states.user_id = excluded.user_id;
      return true;
    end
    $$
    """,
    f"""
    create function owner_reminders_may_be_late(p uuid) returns boolean
    language sql stable {_DEFINER} as $$
      -- the owner and the profile's caregivers only (security review L1): a doctor or a viewer
      -- learns nothing about the owner's phones
      select public.can_read_patient(p) and exists (
          select 1 from public.patient_access me
          where me.patient_id = p and me.user_id = public.app_user_id()
            and me.level in ('owner', 'caregiver') and me.revoked_at is null
            and (me.expires_at is null or me.expires_at > now()))
        and coalesce({_LATE.format(owner=_OWNER_OF.format(p="p"))}, false)
    $$
    """,
    "revoke execute on function set_device_exact_alarms(uuid, boolean) from public",
    "grant execute on function set_device_exact_alarms(uuid, boolean) to labtrack_app",
    "revoke execute on function owner_reminders_may_be_late(uuid) from public",
    "grant execute on function owner_reminders_may_be_late(uuid) to labtrack_app",
]


def upgrade() -> None:
    for sql in _UP:
        op.execute(sql)
    op.execute(_targets_late())


def downgrade() -> None:
    op.execute(_targets_0026())
    op.execute("drop function owner_reminders_may_be_late(uuid)")
    op.execute("drop function set_device_exact_alarms(uuid, boolean)")
    op.execute("drop table device_alarm_states")
