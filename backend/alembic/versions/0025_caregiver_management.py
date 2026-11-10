"""The owner manages caregivers; no caregivers on a child's profile (Phase 2.8d).

- owner_caregivers(p): the profile's caregivers for its owner - their display name (they
  accepted an invitation from this owner), since when, the alert delay they chose and whether
  the owner paused it. Users' rows are not readable across accounts, hence a definer.
- owner_caregiver_invitations(p): the owner's open invitations with the username the owner
  typed (user decision (a), 2026-11-11: no display name before acceptance). That a row appears
  says the username exists; the lookup behind it is limited to 30 an hour (0002).
- revoke_caregiver(p, u): the owner ends a caregiver's access, with their alert settings,
  audited by id (caregiver.revoke).
- user decision (b): a minor's profile gets no caregiver invitation in the MVP (its owner is
  the parent; a caregiver's consent flow for a child does not exist yet). Enforced on insert,
  and open ones are ended. invite_caregiver() checks it before the username lookup, so the
  answer is the same whoever the username is (security review H1: an error after the lookup
  rolled back the lookup's rate-limit row and told the caller the username exists).
  Caregivers already on a child's profile are let out (M2).
- an invited person sees who invites, not the profile's full name, until they accept
  (security review M1, Q45): a mistyped username must not send someone's name to a stranger.
- pause_caregiver_alerts() answers false for a caregiver whose access ended (L1), and the
  app role cannot change or delete a caregiver's access row directly - only through the
  definer functions, which audit it (L2).

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-11
"""

import importlib.util
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEFINER = "security definer set search_path = pg_catalog, public, pg_temp"


def _revision(filename: str) -> ModuleType:
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_M20 = _revision("0020_caregivers_and_push.py")


def _original(name: str) -> str:
    (sql,) = [x for x in _M20._FUNCTIONS if f"create function {name}(" in x]
    return str(sql)


def _patched(sql: str, old: str, new: str) -> str:
    if sql.count(old) != 1:
        raise RuntimeError(f"0020 text changed: {old[:40]}")
    return sql.replace(old, new)


_INVITE_OLD = _original("invite_caregiver").replace(
    "create function", "create or replace function", 1
)
_INVITE = _patched(
    _INVITE_OLD,
    """hint = 'caregiver_sharing';
      end if;
""",
    """hint = 'caregiver_sharing';
      end if;
      -- before the lookup: the same answer whoever the username is (0025, H1)
      if exists (select 1 from public.patients p
                 where p.id = p_patient
                   and p.birth_date > public.local_today() - interval '18 years') then
        raise exception 'no caregivers on a minor''s profile' using errcode = '42501',
          hint = 'minor_profile';
      end if;
""",
)
_PAUSE_OLD = _original("pause_caregiver_alerts").replace(
    "create function", "create or replace function", 1
)
_PAUSE = _patched(
    _PAUSE_OLD,
    "and a.level = 'caregiver') then",
    """and a.level = 'caregiver' and a.revoked_at is null
                       and (a.expires_at is null or a.expires_at > now())) then""",
)
_MY_INVITATIONS_OLD = _original("my_caregiver_invitations")
_MY_INVITATIONS = _patched(
    _patched(
        _MY_INVITATIONS_OLD,
        "returns table (id uuid, inviter_name text, patient_name text, created_at timestamptz,",
        "returns table (id uuid, inviter_name text, created_at timestamptz,",
    ),
    "select i.id, u.display_name, p.full_name, i.created_at, i.expires_at",
    "select i.id, u.display_name, i.created_at, i.expires_at",
)

# the app changes or removes a caregiver's access only through the definer functions
_CAREGIVER_ROWS = """
create function patient_access_caregiver_rows() returns trigger language plpgsql as $$
begin
  if current_user = 'labtrack_app' and old.level = 'caregiver' then
    raise exception 'a caregiver''s access changes through its functions'
      using errcode = '42501';
  end if;
  return case when tg_op = 'DELETE' then old else new end;
end $$
"""

_FUNCTIONS = [
    f"""
    create function owner_caregivers(p_patient uuid)
    returns table (user_id uuid, display_name text, since timestamptz,
                   missed_dose_after_min int, critical_result boolean, owner_paused boolean)
    language sql stable {_DEFINER} as $$
      -- since: the latest accepted invitation (access rows carry no time of their own)
      select a.user_id, u.display_name,
             (select max(i.responded_at) from public.caregiver_invitations i
              where i.patient_id = a.patient_id and i.invited_user_id = a.user_id
                and i.status = 'accepted'),
             s.missed_dose_after_min,
             coalesce(s.critical_result, false), coalesce(s.owner_paused, false)
      from public.patient_access a
      join public.users u on u.id = a.user_id and u.deleted_at is null
      left join public.caregiver_alert_settings s
        on s.patient_id = a.patient_id and s.caregiver_user_id = a.user_id
      where public.is_owner(p_patient) and a.patient_id = p_patient
        and a.level = 'caregiver' and a.revoked_at is null
        and (a.expires_at is null or a.expires_at > now())
      order by 3, a.user_id
    $$
    """,
    f"""
    create function owner_caregiver_invitations(p_patient uuid)
    returns table (id uuid, username text, created_at timestamptz, expires_at timestamptz)
    language sql stable {_DEFINER} as $$
      select i.id, u.username::text, i.created_at, i.expires_at
      from public.caregiver_invitations i
      join public.users u on u.id = i.invited_user_id
      where public.is_owner(p_patient) and i.patient_id = p_patient
        and i.status = 'pending' and i.expires_at > now()
      order by i.created_at, i.id
    $$
    """,
    f"""
    create function revoke_caregiver(p_patient uuid, p_user uuid) returns boolean
    language plpgsql volatile {_DEFINER} as $$
    begin
      if public.app_user_id() is null or not public.is_owner(p_patient) then
        raise exception 'not the owner' using errcode = '42501';
      end if;
      update public.patient_access set revoked_at = now()
        where patient_id = p_patient and user_id = p_user and level = 'caregiver'
          and revoked_at is null;
      if not found then
        return false;
      end if;
      delete from public.caregiver_alert_settings
        where patient_id = p_patient and caregiver_user_id = p_user;
      perform public.caregiver_audit('caregiver.revoke', 'user', p_user::text, p_patient, null);
      return true;
    end $$
    """,
]

# the profile's age is read directly: the inviting owner can read it anyway
_NO_MINOR = f"""
create function caregiver_invitations_no_minor() returns trigger
language plpgsql {_DEFINER} as $$
begin
  if exists (select 1 from public.patients p
             where p.id = new.patient_id
               and p.birth_date > public.local_today() - interval '18 years') then
    raise exception 'no caregivers on a minor''s profile' using errcode = '42501',
      hint = 'minor_profile';
  end if;
  return new;
end $$
"""


def upgrade() -> None:
    for sql in _FUNCTIONS:
        op.execute(sql)
    op.execute(_NO_MINOR)
    op.execute(
        """create trigger caregiver_invitations_no_minor before insert on caregiver_invitations
           for each row execute function caregiver_invitations_no_minor()"""
    )
    op.execute(
        "update caregiver_invitations i set status = 'revoked', responded_at = now()"
        " from patients p where p.id = i.patient_id and i.status = 'pending'"
        " and p.birth_date > local_today() - interval '18 years'"
    )
    # caregivers who got onto a child's profile before this: out, with their alerts (M2)
    op.execute(
        "delete from caregiver_alert_settings s using patients p where p.id = s.patient_id"
        " and p.birth_date > local_today() - interval '18 years'"
    )
    op.execute(
        "update patient_access a set revoked_at = now() from patients p"
        " where p.id = a.patient_id and a.level = 'caregiver' and a.revoked_at is null"
        " and p.birth_date > local_today() - interval '18 years'"
    )
    op.execute(_INVITE)
    op.execute(_PAUSE)
    op.execute("drop function my_caregiver_invitations()")
    op.execute(_MY_INVITATIONS)
    op.execute(_CAREGIVER_ROWS)
    op.execute(
        """create trigger patient_access_caregiver_rows before update or delete on patient_access
           for each row execute function patient_access_caregiver_rows()"""
    )
    for name in (
        "owner_caregivers(uuid)",
        "owner_caregiver_invitations(uuid)",
        "revoke_caregiver(uuid, uuid)",
        "caregiver_invitations_no_minor()",
        "my_caregiver_invitations()",
        "patient_access_caregiver_rows()",
    ):
        op.execute(f"revoke execute on function {name} from public")
    op.execute(
        """grant execute on function owner_caregivers(uuid), owner_caregiver_invitations(uuid),
           revoke_caregiver(uuid, uuid), my_caregiver_invitations() to labtrack_app"""
    )


def downgrade() -> None:
    op.execute("drop trigger patient_access_caregiver_rows on patient_access")
    op.execute("drop function patient_access_caregiver_rows()")
    op.execute("drop function my_caregiver_invitations()")
    op.execute(_MY_INVITATIONS_OLD)
    op.execute("revoke execute on function my_caregiver_invitations() from public")
    op.execute("grant execute on function my_caregiver_invitations() to labtrack_app")
    op.execute(_PAUSE_OLD)
    op.execute(_INVITE_OLD)
    op.execute("drop trigger caregiver_invitations_no_minor on caregiver_invitations")
    op.execute("drop function caregiver_invitations_no_minor()")
    op.execute("drop function revoke_caregiver(uuid, uuid)")
    op.execute("drop function owner_caregiver_invitations(uuid)")
    op.execute("drop function owner_caregivers(uuid)")
