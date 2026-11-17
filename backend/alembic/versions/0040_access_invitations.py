"""Sharing a profile by username with a doctor or a viewer (Phase 7.1; docs/04 §2 "Хуваалцах
хоёр арга" 1, docs/06 §6; hazard H36).

- the owner invites a registered person by username as 'doctor' or 'viewer', for 1, 7 or 30
  days or until revoked. Nothing is shared until that person accepts (docs/04: "Тэр хэрэглэгч
  зөвшөөрснөөр идэвхжинэ"); the access then runs from the moment of acceptance. Every step is a
  definer function, audited by id only, as the caregiver invitations of 0020/0025;
- read-only, the whole profile (a scope by category is the link share's, Phase 7.2 - Q61);
- the app role no longer inserts, changes or deletes a doctor's or a viewer's access row
  directly (as for caregivers since 0020/0025): only the functions here, audited;
- who opened the profile, and when: one row per person and Ulaanbaatar day for a doctor's or
  a viewer's reads (first and last time), kept 400 days, shown to the owner only. Written by
  the API's profile gate through `note_profile_view()`, never by a client.

Revision ID: 0040
Revises: 0039
Create Date: 2026-11-17
"""

import importlib.util
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

from alembic import op

revision: str = "0040"
down_revision: str | None = "0039"
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


_M35 = _revision("0035_review_flags_and_notices.py")
_NOTIFY_OLD = _M35._NOTIFY.format(definer=_DEFINER, drafts="false")
# share_invite: a pending caregiver invitation (0020) or, now, a pending access invitation
_INVITE_CHECK_OLD = """      and exists (select 1 from public.caregiver_invitations i
                  where i.id::text = p_entity_id and i.invited_user_id = p_user_id
                    and i.patient_id = p_patient_id and i.status = 'pending')"""
_INVITE_CHECK_NEW = """      and (exists (select 1 from public.caregiver_invitations i
                   where i.id::text = p_entity_id and i.invited_user_id = p_user_id
                     and i.patient_id = p_patient_id and i.status = 'pending')
           or exists (select 1 from public.access_invitations i
                      where i.id::text = p_entity_id and i.invited_user_id = p_user_id
                        and i.patient_id = p_patient_id and i.status = 'pending'))"""
if _INVITE_CHECK_OLD not in _NOTIFY_OLD:
    raise RuntimeError("notify() text of 0035 changed")
_NOTIFY_NEW = _NOTIFY_OLD.replace(_INVITE_CHECK_OLD, _INVITE_CHECK_NEW)

_TABLES = [
    """
    create table access_invitations (
      id uuid primary key default gen_random_uuid(),
      patient_id uuid not null references patients on delete cascade,
      invited_user_id uuid not null references users on delete cascade,
      invited_by uuid not null references users on delete cascade,
      level access_level not null check (level in ('doctor', 'viewer')),
      -- how long the access lasts once accepted; null: until the owner revokes it
      access_days int check (access_days in (1, 7, 30)),
      status text not null default 'pending'
        check (status in ('pending','accepted','declined','revoked')),
      created_at timestamptz not null default now(),
      expires_at timestamptz not null default now() + interval '14 days',
      responded_at timestamptz,
      check (invited_user_id <> invited_by),
      check ((status = 'pending') = (responded_at is null))
    )
    """,
    """create unique index access_invitations_one_open on access_invitations
       (patient_id, invited_user_id) where status = 'pending'""",
    "create index on access_invitations (invited_user_id, created_at desc)",
    "create index on access_invitations (patient_id, created_at desc)",
    """
    create table profile_views (
      patient_id uuid not null references patients on delete cascade,
      user_id uuid not null references users on delete cascade,
      day date not null,
      first_at timestamptz not null default now(),
      last_at timestamptz not null default now(),
      primary key (patient_id, user_id, day)
    )
    """,
    "create index on profile_views (patient_id, day desc)",
]

# the caller's live access level on a profile (null: none)
_LEVEL = """(select a.level from public.patient_access a
            where a.patient_id = {p} and a.user_id = {u} and a.revoked_at is null
              and (a.expires_at is null or a.expires_at > now()))"""

_FUNCTIONS = [
    f"""
    create function invite_access(p_patient uuid, p_username text, p_level text, p_days int)
    returns uuid language plpgsql volatile {_DEFINER} as $$
    declare
      me uuid := public.app_user_id();
      found uuid;
      inv uuid;
    begin
      if me is null or not public.is_owner(p_patient) then
        raise exception 'not the owner' using errcode = '42501';
      end if;
      if p_level not in ('doctor', 'viewer')
         or (p_days is not null and p_days not in (1, 7, 30)) then
        raise exception 'invalid share' using errcode = '22023';
      end if;
      if (select count(*) from public.access_invitations i
          where i.patient_id = p_patient and i.status = 'pending'
            and i.expires_at > now()) >= 20 then
        raise exception 'too many invitations' using errcode = '54000';
      end if;
      found := public.lookup_user_for_share(p_username);  -- rate-limited, exact, active only
      -- nobody, oneself, already sharing, or declined in the last 30 days: nothing happens,
      -- and the API answers the same (no username oracle; as invite_caregiver)
      if found is null or found = me
         or {_LEVEL.format(p="p_patient", u="found")} is not null
         or exists (
           select 1 from public.access_invitations d
           where d.patient_id = p_patient and d.invited_user_id = found
             and d.status = 'declined' and d.responded_at > now() - interval '30 days') then
        return null;
      end if;
      -- at most 3 invitations from one person to another in 30 days (no notice spam)
      if (select count(*) from public.access_invitations i
          where i.invited_by = me and i.invited_user_id = found
            and i.created_at > now() - interval '30 days')
         + (select count(*) from public.caregiver_invitations i
            where i.invited_by = me and i.invited_user_id = found
              and i.created_at > now() - interval '30 days') >= 3 then
        return null;
      end if;
      update public.access_invitations set status = 'revoked', responded_at = now()
        where patient_id = p_patient and invited_user_id = found and status = 'pending'
          and expires_at <= now();
      select id into inv from public.access_invitations
        where patient_id = p_patient and invited_user_id = found and status = 'pending';
      if inv is not null then
        return inv;  -- asked again: the same invitation, as first made
      end if;
      insert into public.access_invitations
          (patient_id, invited_user_id, invited_by, level, access_days)
        values (p_patient, found, me, p_level::public.access_level, p_days)
        on conflict (patient_id, invited_user_id) where status = 'pending' do nothing
        returning id into inv;
      if inv is null then
        select id into inv from public.access_invitations
          where patient_id = p_patient and invited_user_id = found and status = 'pending';
        return inv;
      end if;
      perform public.notify(found, 'share_invite', p_patient, inv::text,
                            'notification.share_invite');
      perform public.caregiver_audit('share.invite', 'access_invitation', inv::text,
                                     p_patient,
                                     jsonb_build_object('fields',
                                                        jsonb_build_array('level',
                                                                          'access_days')));
      return inv;
    end $$
    """,
    f"""
    create function respond_access_invitation(p_invitation uuid, p_accept boolean)
    returns boolean language plpgsql volatile {_DEFINER} as $$
    declare
      me uuid := public.app_user_id();
      inv public.access_invitations;
      n int;
    begin
      select * into inv from public.access_invitations
        where id = p_invitation and invited_user_id = me and status = 'pending'
          and expires_at > now()
        for update;
      if inv.id is null then
        return false;
      end if;
      if not p_accept then
        update public.access_invitations set status = 'declined', responded_at = now()
          where id = inv.id;
        perform public.caregiver_audit('share.decline', 'access_invitation', inv.id::text,
                                       inv.patient_id, null);
        return true;
      end if;
      if not public.is_shareable_user(me) then
        return false;
      end if;
      -- the inviter must still own the profile, and the profile must still exist
      if not exists (select 1 from public.patient_access a
                     where a.patient_id = inv.patient_id and a.user_id = inv.invited_by
                       and a.level = 'owner' and a.revoked_at is null)
         or not public.is_shareable_user(inv.invited_by)
         or exists (select 1 from public.patients x
                    where x.id = inv.patient_id and x.deleted_at is not null) then
        return false;
      end if;
      -- someone with access already (a caregiver meanwhile): their access is not replaced
      if {_LEVEL.format(p="inv.patient_id", u="me")} is not null then
        return false;
      end if;
      -- only a row that gives nothing now is replaced: an access taken meanwhile by a
      -- concurrent acceptance (a caregiver's) stays as it is, and this one fails
      insert into public.patient_access (patient_id, user_id, level, granted_by, expires_at)
        values (inv.patient_id, me, inv.level, inv.invited_by,
                now() + make_interval(days => inv.access_days))
      on conflict (patient_id, user_id) do update
        set level = excluded.level, revoked_at = null, expires_at = excluded.expires_at,
            granted_by = excluded.granted_by, scopes = excluded.scopes
        where public.patient_access.level <> 'owner'
          and (public.patient_access.revoked_at is not null
               or public.patient_access.expires_at <= now());
      get diagnostics n = row_count;
      if n = 0 then
        return false;
      end if;
      update public.access_invitations set status = 'accepted', responded_at = now()
        where id = inv.id;
      perform public.caregiver_audit('share.accept', 'access_invitation', inv.id::text,
                                     inv.patient_id, null);
      return true;
    end $$
    """,
    f"""
    create function revoke_access_invitation(p_invitation uuid) returns boolean
    language plpgsql volatile {_DEFINER} as $$
    declare
      pid uuid;
    begin
      update public.access_invitations set status = 'revoked', responded_at = now()
        where id = p_invitation and status = 'pending' and public.is_owner(patient_id)
        returning patient_id into pid;
      if pid is null then
        return false;
      end if;
      perform public.caregiver_audit('share.uninvite', 'access_invitation',
                                     p_invitation::text, pid, null);
      return true;
    end $$
    """,
    f"""
    create function revoke_share(p_patient uuid, p_user uuid) returns boolean
    language plpgsql volatile {_DEFINER} as $$
    begin
      if public.app_user_id() is null or not public.is_owner(p_patient) then
        raise exception 'not the owner' using errcode = '42501';
      end if;
      update public.patient_access set revoked_at = now()
        where patient_id = p_patient and user_id = p_user and level in ('doctor', 'viewer')
          and revoked_at is null and (expires_at is null or expires_at > now());
      if not found then
        return false;
      end if;
      perform public.caregiver_audit('share.revoke', 'user', p_user::text, p_patient, null);
      return true;
    end $$
    """,
    # a doctor or a viewer steps back
    f"""
    create function leave_share(p_patient uuid) returns boolean
    language plpgsql volatile {_DEFINER} as $$
    declare
      me uuid := public.app_user_id();
    begin
      update public.patient_access set revoked_at = now()
        where patient_id = p_patient and user_id = me and level in ('doctor', 'viewer')
          and revoked_at is null;
      if not found then
        return false;
      end if;
      perform public.caregiver_audit('share.leave', 'patient', p_patient::text, p_patient,
                                     null);
      return true;
    end $$
    """,
    # the owner's list: who has the profile now, until when, and when they last opened it
    f"""
    create function owner_shares(p_patient uuid)
    returns table (user_id uuid, display_name text, level text, since timestamptz,
                   expires_at timestamptz, last_viewed_at timestamptz)
    language sql stable {_DEFINER} as $$
      select a.user_id, u.display_name, a.level::text,
             (select max(i.responded_at) from public.access_invitations i
              where i.patient_id = a.patient_id and i.invited_user_id = a.user_id
                and i.status = 'accepted'),
             a.expires_at,
             (select max(v.last_at) from public.profile_views v
              where v.patient_id = a.patient_id and v.user_id = a.user_id)
      from public.patient_access a
      join public.users u on u.id = a.user_id and u.deleted_at is null
      where public.is_owner(p_patient) and a.patient_id = p_patient
        and a.level in ('doctor', 'viewer') and a.revoked_at is null
        and (a.expires_at is null or a.expires_at > now())
      order by 4, a.user_id
    $$
    """,
    f"""
    create function owner_access_invitations(p_patient uuid)
    returns table (id uuid, username text, level text, access_days int,
                   created_at timestamptz, expires_at timestamptz)
    language sql stable {_DEFINER} as $$
      select i.id, u.username::text, i.level::text, i.access_days, i.created_at, i.expires_at
      from public.access_invitations i
      join public.users u on u.id = i.invited_user_id
      where public.is_owner(p_patient) and i.patient_id = p_patient
        and i.status = 'pending' and i.expires_at > now()
      order by i.created_at, i.id
    $$
    """,
    # what an invited person sees before accepting: who asks, as what, for how long (the
    # profile's name only after accepting, as Q45)
    f"""
    create function my_access_invitations()
    returns table (id uuid, inviter_name text, level text, access_days int,
                   created_at timestamptz, expires_at timestamptz)
    language sql stable {_DEFINER} as $$
      select i.id, u.display_name, i.level::text, i.access_days, i.created_at, i.expires_at
      from public.access_invitations i
      join public.users u on u.id = i.invited_by
      join public.patients p on p.id = i.patient_id and p.deleted_at is null
      where i.invited_user_id = public.app_user_id() and i.status = 'pending'
        and i.expires_at > now()
        and exists (select 1 from public.patient_access a
                    where a.patient_id = i.patient_id and a.user_id = i.invited_by
                      and a.level = 'owner' and a.revoked_at is null)
        and public.is_shareable_user(i.invited_by)
      order by i.created_at desc limit 50
    $$
    """,
    # a doctor's or a viewer's read of the profile (called by the API's profile gate)
    f"""
    create function note_profile_view(p uuid) returns void
    language plpgsql volatile {_DEFINER} as $$
    declare
      me uuid := public.app_user_id();
    begin
      -- a plain read first: noted in the last 5 minutes, nothing is written or locked
      -- (the app reads a profile with many requests at once)
      if exists (select 1 from public.profile_views v
                 where v.patient_id = p and v.user_id = me
                   and v.day = public.local_today()
                   and v.last_at > now() - interval '5 minutes') then
        return;
      end if;
      if {_LEVEL.format(p="p", u="me")} in ('doctor', 'viewer') then
        insert into public.profile_views (patient_id, user_id, day)
          values (p, me, public.local_today())
        on conflict (patient_id, user_id, day) do update set last_at = now();
      end if;
    end $$
    """,
    # the owner's view of who opened the profile, the last 90 days
    f"""
    create function owner_profile_views(p_patient uuid)
    returns table (user_id uuid, display_name text, day date, first_at timestamptz,
                   last_at timestamptz)
    language sql stable {_DEFINER} as $$
      select v.user_id, u.display_name, v.day, v.first_at, v.last_at
      from public.profile_views v
      join public.users u on u.id = v.user_id
      where public.is_owner(p_patient) and v.patient_id = p_patient
        and v.day > public.local_today() - 90
      order by v.day desc, v.last_at desc limit 500
    $$
    """,
    # retention: rows older than 400 days (the maintenance worker)
    f"""
    create function maint_prune_profile_views() returns int
    language sql volatile {_DEFINER} as $$
      with gone as (delete from public.profile_views
                    where day < public.local_today() - 400 returning 1)
      select count(*)::int from gone
    $$
    """,
]

_GRANTS = [
    """create policy access_invitations_select on access_invitations for select
       to labtrack_app using (invited_user_id = app_user_id() or is_owner(patient_id))""",
    "grant select on access_invitations to labtrack_app",
    # profile_views: through the functions only (no policy for the app = no rows)
    """grant execute on function invite_access(uuid, text, text, int),
       respond_access_invitation(uuid, boolean), revoke_access_invitation(uuid),
       revoke_share(uuid, uuid), leave_share(uuid), owner_shares(uuid),
       owner_access_invitations(uuid), my_access_invitations(), note_profile_view(uuid),
       owner_profile_views(uuid) to labtrack_app""",
    "grant execute on function maint_prune_profile_views() to labtrack_maint",
]

_DROPS = [
    "maint_prune_profile_views()",
    "owner_profile_views(uuid)",
    "note_profile_view(uuid)",
    "my_access_invitations()",
    "owner_access_invitations(uuid)",
    "owner_shares(uuid)",
    "leave_share(uuid)",
    "revoke_share(uuid, uuid)",
    "revoke_access_invitation(uuid)",
    "respond_access_invitation(uuid, boolean)",
    "invite_access(uuid, text, text, int)",
]


# 0025's trigger, now over every shared level (the owner's own row is the owner's)
_SHARED_ROWS = """
create or replace function patient_access_caregiver_rows() returns trigger
language plpgsql as $$
begin
  if current_user = 'labtrack_app' and old.level in ({levels}) then
    raise exception 'a shared access changes through its functions'
      using errcode = '42501';
  end if;
  return case when tg_op = 'DELETE' then old else new end;
end $$
"""
_ACCESS_INSERT_0020 = """create policy access_insert on patient_access for insert to labtrack_app
       with check (is_owner(patient_id) and user_id <> app_user_id()
                   and level not in ('owner', 'caregiver') and is_shareable_user(user_id))"""


def upgrade() -> None:
    for sql in _TABLES:
        op.execute(sql)
    for table in ("access_invitations", "profile_views"):
        op.execute(f"alter table {table} enable row level security")
        op.execute(f"alter table {table} force row level security")
        op.execute(
            f"create policy {table}_owner on {table} for all to labtrack_owner"
            " using (true) with check (true)"
        )
        op.execute(f"revoke truncate on {table} from public")
    op.execute(_NOTIFY_NEW)
    for sql in _FUNCTIONS:
        op.execute(sql)
    for name in _DROPS:
        op.execute(f"revoke execute on function {name} from public")
    for sql in _GRANTS:
        op.execute(sql)
    op.execute(_SHARED_ROWS.format(levels="'caregiver', 'doctor', 'viewer'"))
    op.execute("drop policy access_insert on patient_access")
    # every access row is written by a definer function now (no direct grant)
    op.execute(
        "create policy access_insert on patient_access for insert to labtrack_app"
        " with check (false)"
    )


def downgrade() -> None:
    op.execute("drop policy access_insert on patient_access")
    op.execute(_ACCESS_INSERT_0020)
    op.execute(_SHARED_ROWS.format(levels="'caregiver'"))
    # shares made by invitation do not outlive their invitations and their management
    op.execute(
        "update patient_access set revoked_at = now() where level in ('doctor', 'viewer')"
        " and revoked_at is null and granted_by is not null"
    )
    for name in _DROPS:
        op.execute(f"drop function {name}")
    op.execute(_NOTIFY_OLD)
    op.execute("drop table profile_views")
    op.execute("drop table access_invitations")
