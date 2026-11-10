"""Caregivers (invitations, alert settings, dose alerts) and push delivery (Phase 2.8a).

docs/03 (АСРАН ХАМГААЛАГЧИЙН МЭДЭГДЭЛ), docs/08 "Асран хамгаалагч", hazards H12, H16, H20;
user decisions 2026-11-10 (PROGRESS 2.8):

- a caregiver is invited by username and accepts. Until then they have no access. The owner
  can no longer grant 'caregiver' directly (access_insert), and an access that was revoked
  cannot be revived by an update: a new invitation is needed. Every step goes through a
  definer function, never a direct write, and is audited by id only;
- the owner invites only after giving the caregiver_sharing consent;
- caregiver_alert_settings: the caregiver chooses the delay (30 min by default, 15-240, or
  off). The owner can pause any caregiver's alerts, and only the owner can lift the pause;
- dose_alerts: one alert per scheduled dose and caregiver (H16). Missed doses are found by the
  server, not the phone (decision (a)). The worker gets the targets as ids from
  `maint_caregiver_alert_targets()` and then reads each profile as that caregiver, under the
  normal RLS. It never reads health data as a maintenance role;
- push: a session's Expo token is set only by its own user. A token moved to another account
  on the same phone leaves the old session, so one account's alerts never reach the next. The
  push queue is read by the maintenance worker through definer functions (ids, keys, tokens
  only - never a name or a value; CLAUDE.md rule 3). An admin reset also reaches the devices
  it just signed out (H12).

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-10
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEFINER = "security definer set search_path = pg_catalog, public, pg_temp"
_NOTIFY_OLD = (
    "'review_ready','critical_pending','share_invite','admin_reset','reminder','admin_action'"
)
_NOTIFY_NEW = _NOTIFY_OLD + ",'dose_overdue'"
_PUSHED = "'share_invite','dose_overdue','admin_reset','review_ready','critical_pending'"
# an active caregiver of the profile, for the calling user
_ACTIVE_CAREGIVER = """exists (select 1 from public.patient_access a
      where a.patient_id = {p} and a.user_id = {u} and a.level = 'caregiver'
        and a.revoked_at is null and (a.expires_at is null or a.expires_at > now()))
      and not exists (select 1 from public.patients x
                      where x.id = {p} and x.deleted_at is not null)"""

_TABLES = [
    """
    create table caregiver_invitations (
      id uuid primary key default gen_random_uuid(),
      patient_id uuid not null references patients on delete cascade,
      invited_user_id uuid not null references users on delete cascade,
      invited_by uuid not null references users on delete cascade,
      status text not null default 'pending'
        check (status in ('pending','accepted','declined','revoked')),
      created_at timestamptz not null default now(),
      expires_at timestamptz not null default now() + interval '14 days',
      responded_at timestamptz,
      check (invited_user_id <> invited_by),
      check ((status = 'pending') = (responded_at is null))
    )
    """,
    # one open invitation per profile and person
    """create unique index caregiver_invitations_one_open on caregiver_invitations
       (patient_id, invited_user_id) where status = 'pending'""",
    "create index on caregiver_invitations (invited_user_id, created_at desc)",
    "create index on caregiver_invitations (patient_id, created_at desc)",
    """
    create table caregiver_alert_settings (
      patient_id uuid not null references patients on delete cascade,
      caregiver_user_id uuid not null references users on delete cascade,
      missed_dose_after_min int default 30
        check (missed_dose_after_min is null or missed_dose_after_min between 15 and 240),
      critical_result boolean not null default true,
      owner_paused boolean not null default false,
      updated_at timestamptz not null default now(),
      primary key (patient_id, caregiver_user_id)
    )
    """,
    """
    create table dose_alerts (
      id bigserial primary key,
      patient_id uuid not null references patients on delete cascade,
      medication_id uuid not null,
      slot_at timestamptz not null,
      alerted_user_id uuid not null references users on delete cascade,
      created_at timestamptz not null default now(),
      foreign key (medication_id, patient_id) references medications (id, patient_id)
        on delete cascade,
      unique (patient_id, medication_id, slot_at, alerted_user_id)
    )
    """,
    "create index on dose_alerts (patient_id, slot_at desc)",
    """
    create table push_receipts (
      id bigserial primary key,
      notification_id bigint not null references notifications on delete cascade,
      session_id uuid not null references sessions on delete cascade,
      ticket_id text check (length(ticket_id) <= 100),
      status text not null default 'sent' check (status in ('sent','ok','error')),
      error text check (error ~ '^[A-Za-z]{1,40}$'),
      created_at timestamptz not null default now(),
      checked_at timestamptz
    )
    """,
    "create index on push_receipts (status, created_at) where status = 'sent'",
]

_FUNCTIONS = [
    # audit rows of these functions (ids and field names only). audit_write() needs read access to
    # the profile, which a declined or departing person does not have; called only from here.
    f"""
    create function caregiver_audit(p_action text, p_entity text, p_entity_id text,
                                    p_patient_id uuid, p_diff jsonb)
    returns void language sql volatile {_DEFINER} as $$
      insert into public.audit_logs (actor_id, actor_role, action, entity, entity_id,
                                     patient_id, diff)
      select u.id, u.role::text, p_action, p_entity, p_entity_id, p_patient_id, p_diff
      from public.users u where u.id = public.app_user_id()
    $$
    """,
    # --- the owner's caregiver_sharing consent, as last given (internal) ---
    f"""
    create function caregiver_sharing_given(p_user uuid) returns boolean
    language sql stable {_DEFINER} as $$
      select coalesce((select c.granted from public.consents c
                       where c.user_id = p_user and c.patient_id is null
                         and c.kind = 'caregiver_sharing'
                       order by c.created_at desc, c.id desc limit 1), false)
    $$
    """,
    # --- whether the calling caregiver has alerts on for the profile ---
    f"""
    create function caregiver_alerts_on(p uuid) returns boolean
    language sql stable {_DEFINER} as $$
      select {_ACTIVE_CAREGIVER.format(p="p", u="public.app_user_id()")}
        and exists (select 1 from public.caregiver_alert_settings s
                    where s.patient_id = p and s.caregiver_user_id = public.app_user_id()
                      and s.missed_dose_after_min is not null and not s.owner_paused)
    $$
    """,
    # --- invitations ---
    f"""
    create function invite_caregiver(p_patient uuid, p_username text) returns uuid
    language plpgsql volatile {_DEFINER} as $$
    declare
      me uuid := public.app_user_id();
      found uuid;
      inv uuid;
    begin
      if me is null or not public.is_owner(p_patient) then
        raise exception 'not the owner' using errcode = '42501';
      end if;
      -- the owner's own consent to share with a caregiver, as last given
      if not public.caregiver_sharing_given(me) then
        raise exception 'consent required' using errcode = '42501', hint = 'caregiver_sharing';
      end if;
      if (select count(*) from public.caregiver_invitations i
          where i.patient_id = p_patient and i.status = 'pending'
            and i.expires_at > now()) >= 20 then
        raise exception 'too many invitations' using errcode = '54000';
      end if;
      found := public.lookup_user_for_share(p_username);  -- rate-limited, exact, active only
      -- nobody, oneself, already sharing, or declined in the last 30 days: nothing happens.
      -- The API answers the same in every case (the id stays inside); the lookup is
      -- rate-limited and exact, so this is no username oracle.
      if found is null or found = me or exists (
           select 1 from public.patient_access a
           where a.patient_id = p_patient and a.user_id = found and a.revoked_at is null
             and (a.expires_at is null or a.expires_at > now()))
         or exists (
           select 1 from public.caregiver_invitations d
           where d.patient_id = p_patient and d.invited_user_id = found
             and d.status = 'declined' and d.responded_at > now() - interval '30 days') then
        return null;
      end if;
      -- at most 3 invitations from one person to another in 30 days, over all profiles and
      -- whatever became of them (no notice spam by revoking and inviting again)
      if (select count(*) from public.caregiver_invitations i
          where i.invited_by = me and i.invited_user_id = found
            and i.created_at > now() - interval '30 days') >= 3 then
        return null;
      end if;
      -- an expired open invitation makes room for a new one
      update public.caregiver_invitations set status = 'revoked', responded_at = now()
        where patient_id = p_patient and invited_user_id = found and status = 'pending'
          and expires_at <= now();
      select id into inv from public.caregiver_invitations
        where patient_id = p_patient and invited_user_id = found and status = 'pending';
      if inv is not null then
        return inv;  -- asked again: the same invitation
      end if;
      insert into public.caregiver_invitations (patient_id, invited_user_id, invited_by)
        values (p_patient, found, me)
        on conflict (patient_id, invited_user_id) where status = 'pending' do nothing
        returning id into inv;
      if inv is null then  -- a concurrent call made it: that one
        select id into inv from public.caregiver_invitations
          where patient_id = p_patient and invited_user_id = found and status = 'pending';
        return inv;
      end if;
      perform public.notify(found, 'share_invite', p_patient, inv::text,
                            'notification.caregiver_invite');
      perform public.caregiver_audit('caregiver.invite', 'caregiver_invitation', inv::text,
                                 p_patient, null);
      return inv;
    end $$
    """,
    f"""
    create function respond_caregiver_invitation(p_invitation uuid, p_accept boolean)
    returns boolean language plpgsql volatile {_DEFINER} as $$
    declare
      me uuid := public.app_user_id();
      inv public.caregiver_invitations;
    begin
      select * into inv from public.caregiver_invitations
        where id = p_invitation and invited_user_id = me and status = 'pending'
          and expires_at > now()
        for update;
      if inv.id is null then
        return false;
      end if;
      -- a "no" is always possible, whatever became of the inviter or the profile
      if not p_accept then
        update public.caregiver_invitations set status = 'declined', responded_at = now()
          where id = inv.id;
        perform public.caregiver_audit('caregiver.decline', 'caregiver_invitation',
                                       inv.id::text, inv.patient_id, null);
        return true;
      end if;
      if not public.is_shareable_user(me) then
        return false;
      end if;
      -- the inviter must still own the profile (and the profile must still exist)
      if not exists (select 1 from public.patient_access a
                     where a.patient_id = inv.patient_id and a.user_id = inv.invited_by
                       and a.level = 'owner' and a.revoked_at is null)
         or exists (select 1 from public.patients x
                    where x.id = inv.patient_id and x.deleted_at is not null)
         or not public.caregiver_sharing_given(inv.invited_by) then
        return false;
      end if;
      update public.caregiver_invitations
        set status = case when p_accept then 'accepted' else 'declined' end, responded_at = now()
        where id = inv.id;
      if p_accept then
        insert into public.patient_access (patient_id, user_id, level, granted_by)
          values (inv.patient_id, me, 'caregiver', inv.invited_by)
        on conflict (patient_id, user_id) do update
          set level = 'caregiver', revoked_at = null, expires_at = null,
              granted_by = excluded.granted_by, scopes = excluded.scopes
          where public.patient_access.level <> 'owner';
        -- settings from an earlier time as caregiver do not come back: chosen anew
        delete from public.caregiver_alert_settings
          where patient_id = inv.patient_id and caregiver_user_id = me;
      end if;
      perform public.caregiver_audit(
        case when p_accept then 'caregiver.accept' else 'caregiver.decline' end,
        'caregiver_invitation', inv.id::text, inv.patient_id, null);
      return true;
    end $$
    """,
    f"""
    create function revoke_caregiver_invitation(p_invitation uuid) returns boolean
    language plpgsql volatile {_DEFINER} as $$
    declare
      pid uuid;
    begin
      update public.caregiver_invitations set status = 'revoked', responded_at = now()
        where id = p_invitation and status = 'pending' and public.is_owner(patient_id)
        returning patient_id into pid;
      if pid is null then
        return false;
      end if;
      perform public.caregiver_audit('caregiver.uninvite', 'caregiver_invitation',
                                 p_invitation::text, pid, null);
      return true;
    end $$
    """,
    # the caregiver steps back; their alerts go with them
    f"""
    create function leave_patient(p_patient uuid) returns boolean
    language plpgsql volatile {_DEFINER} as $$
    declare
      me uuid := public.app_user_id();
    begin
      update public.patient_access set revoked_at = now()
        where patient_id = p_patient and user_id = me and level = 'caregiver'
          and revoked_at is null;
      if not found then
        return false;
      end if;
      delete from public.caregiver_alert_settings
        where patient_id = p_patient and caregiver_user_id = me;
      perform public.caregiver_audit('caregiver.leave', 'patient', p_patient::text, p_patient,
                                     null);
      return true;
    end $$
    """,
    # --- alert settings ---
    f"""
    create function set_caregiver_alerts(p_patient uuid, p_after_min int, p_critical boolean)
    returns boolean language plpgsql volatile {_DEFINER} as $$
    declare
      me uuid := public.app_user_id();
    begin
      if me is null or not ({_ACTIVE_CAREGIVER.format(p="p_patient", u="me")}) then
        raise exception 'not a caregiver of this profile' using errcode = '42501';
      end if;
      insert into public.caregiver_alert_settings
          (patient_id, caregiver_user_id, missed_dose_after_min, critical_result)
        values (p_patient, me, p_after_min, p_critical)
      on conflict (patient_id, caregiver_user_id) do update
        set missed_dose_after_min = excluded.missed_dose_after_min,
            critical_result = excluded.critical_result, updated_at = now();
      perform public.caregiver_audit('caregiver.alerts', 'patient', p_patient::text, p_patient,
        jsonb_build_object('fields', jsonb_build_array('missed_dose_after_min',
                                                       'critical_result')));
      return true;
    end $$
    """,
    f"""
    create function pause_caregiver_alerts(p_patient uuid, p_caregiver uuid, p_paused boolean)
    returns boolean language plpgsql volatile {_DEFINER} as $$
    begin
      if not public.is_owner(p_patient) then
        raise exception 'not the owner' using errcode = '42501';
      end if;
      if not exists (select 1 from public.patient_access a
                     where a.patient_id = p_patient and a.user_id = p_caregiver
                       and a.level = 'caregiver') then
        return false;
      end if;
      -- a pause before the caregiver chose anything leaves alerts off (no default delay)
      insert into public.caregiver_alert_settings
          (patient_id, caregiver_user_id, missed_dose_after_min, owner_paused)
        values (p_patient, p_caregiver, null, p_paused)
      on conflict (patient_id, caregiver_user_id) do update
        set owner_paused = excluded.owner_paused, updated_at = now();
      perform public.caregiver_audit('caregiver.pause', 'patient', p_patient::text, p_patient,
        jsonb_build_object('fields', jsonb_build_array('owner_paused')));
      return true;
    end $$
    """,
    # what an invited person sees before accepting: who asks, for which profile
    f"""
    create function my_caregiver_invitations()
    returns table (id uuid, inviter_name text, patient_name text, created_at timestamptz,
                   expires_at timestamptz)
    language sql stable {_DEFINER} as $$
      select i.id, u.display_name, p.full_name, i.created_at, i.expires_at
      from public.caregiver_invitations i
      join public.users u on u.id = i.invited_by
      join public.patients p on p.id = i.patient_id and p.deleted_at is null
      where i.invited_user_id = public.app_user_id() and i.status = 'pending'
        and i.expires_at > now()
        -- only invitations that could still be accepted: the inviter owns the profile and
        -- still consents to sharing it
        and exists (select 1 from public.patient_access a
                    where a.patient_id = i.patient_id and a.user_id = i.invited_by
                      and a.level = 'owner' and a.revoked_at is null)
        and public.caregiver_sharing_given(i.invited_by)
      order by i.created_at desc limit 50
    $$
    """,
    # --- push tokens ---
    f"""
    create function set_session_push_token(p_session uuid, p_token text) returns boolean
    language plpgsql volatile {_DEFINER} as $$
    begin
      if p_token is not null
         and p_token !~ '^Expo(nent)?PushToken\\[[A-Za-z0-9_-]{{10,100}}\\]$' then
        raise exception 'not an Expo push token' using errcode = '22023';
      end if;
      if not exists (select 1 from public.sessions
                     where id = p_session and user_id = public.app_user_id()
                       and revoked_at is null and expires_at > now()) then
        return false;
      end if;
      -- the phone now belongs to this session: no other session (account) keeps its token
      if p_token is not null then
        update public.sessions set push_token = null
          where push_token = p_token and id <> p_session;
      end if;
      update public.sessions set push_token = p_token where id = p_session;
      return true;
    end $$
    """,
    # --- maintenance worker (labtrack_maint): ids, keys and tokens only ---
    f"""
    create function maint_caregiver_alert_targets()
    returns table (patient_id uuid, caregiver_user_id uuid, after_min int)
    language sql stable {_DEFINER} as $$
      select s.patient_id, s.caregiver_user_id, s.missed_dose_after_min
      from public.caregiver_alert_settings s
      join public.patient_access a on a.patient_id = s.patient_id
        and a.user_id = s.caregiver_user_id and a.level = 'caregiver'
        and a.revoked_at is null and (a.expires_at is null or a.expires_at > now())
      join public.patients p on p.id = s.patient_id and p.deleted_at is null
      join public.users u on u.id = s.caregiver_user_id and u.account_status = 'active'
        and u.deleted_at is null
      where s.missed_dose_after_min is not null and not s.owner_paused
    $$
    """,
    f"""
    create function maint_push_queue(p_limit int)
    returns table (notification_id bigint, kind text, title_key text, entity_id text,
                   patient_id uuid, session_id uuid, push_token text)
    language sql stable {_DEFINER} as $$
      select n.id, n.kind, n.title_key, n.entity_id, n.patient_id, s.id, s.push_token
      from public.notifications n
      join public.sessions s on s.user_id = n.user_id and s.push_token is not null
        and ((s.revoked_at is null and s.expires_at > now())
             -- the devices an admin reset just signed out still hear about it (H12)
             or (n.kind = 'admin_reset' and s.revoked_reason = 'admin_reset'
                 and s.revoked_at > now() - interval '1 day'))
      join public.users u on u.id = n.user_id
        and (u.account_status = 'active' or n.kind = 'admin_reset')
      where n.sent_push_at is null and n.created_at > now() - interval '1 day'
        and n.kind in ({_PUSHED})
      order by n.id limit least(greatest(p_limit, 1), 500)
    $$
    """,
    f"""
    create function maint_mark_pushed(p_ids bigint[]) returns int
    language sql volatile {_DEFINER} as $$
      with done as (update public.notifications set sent_push_at = now()
                    where id = any(p_ids) and sent_push_at is null returning 1)
      select count(*)::int from done
    $$
    """,
    f"""
    create function maint_forget_push_token(p_token text) returns int
    language sql volatile {_DEFINER} as $$
      with gone as (update public.sessions set push_token = null
                    where push_token = p_token returning 1)
      select count(*)::int from gone
    $$
    """,
]

# notify(): adds 'dose_overdue' - a caregiver (the worker acting as them) to themselves only,
# while their alerts are on
_NOTIFY = f"""
create or replace function notify(p_user_id uuid, p_kind text, p_patient_id uuid,
                                  p_entity_id text, p_title_key text)
returns void language plpgsql volatile {_DEFINER} as $$
declare
  allowed boolean;
begin
  allowed := case
    when p_kind in ('review_ready', 'critical_pending') then
      p_patient_id is not null and public.can_write_patient(p_patient_id)
      and exists (select 1 from public.patient_access a
                  where a.patient_id = p_patient_id and a.user_id = p_user_id
                    and a.revoked_at is null
                    and (a.expires_at is null or a.expires_at > now()))
    -- an invitation's notice only for that pending invitation (no notices to anyone at will)
    when p_kind = 'share_invite' then
      p_patient_id is not null and public.is_owner(p_patient_id)
      and exists (select 1 from public.caregiver_invitations i
                  where i.id::text = p_entity_id and i.invited_user_id = p_user_id
                    and i.patient_id = p_patient_id and i.status = 'pending')
    when p_kind = 'reminder' then p_user_id = public.app_user_id()
    when p_kind = 'dose_overdue' then
      p_user_id = public.app_user_id() and p_patient_id is not null
      and public.caregiver_alerts_on(p_patient_id)
    else false
  end;
  if not coalesce(allowed, false) then
    raise exception 'notification not allowed' using errcode = '42501';
  end if;
  insert into public.notifications (user_id, kind, patient_id, entity_id, title_key)
    values (p_user_id, p_kind, p_patient_id, p_entity_id, p_title_key);
end $$
"""

_NOTIFY_PREVIOUS = _NOTIFY.replace(
    """    when p_kind = 'dose_overdue' then
      p_user_id = public.app_user_id() and p_patient_id is not null
      and public.caregiver_alerts_on(p_patient_id)
""",
    "",
).replace(
    """    -- an invitation's notice only for that pending invitation (no notices to anyone at will)
    when p_kind = 'share_invite' then
      p_patient_id is not null and public.is_owner(p_patient_id)
      and exists (select 1 from public.caregiver_invitations i
                  where i.id::text = p_entity_id and i.invited_user_id = p_user_id
                    and i.patient_id = p_patient_id and i.status = 'pending')
""",
    "    when p_kind = 'share_invite' then p_patient_id is not null"
    " and public.is_owner(p_patient_id)\n",
)
# the downgrade must restore the old notify(), never keep calls to dropped functions
if "caregiver" in _NOTIFY_PREVIOUS:
    raise RuntimeError("notify() downgrade text did not apply")

# patient_access, as the app writes it: no direct caregiver grant, no revived access
_ACCESS_RULES = """
create function patient_access_app_rules() returns trigger language plpgsql as $$
begin
  if current_user = 'labtrack_app' and tg_op = 'UPDATE' then
    if new.patient_id <> old.patient_id or new.user_id <> old.user_id then
      raise exception 'access rows are not moved' using errcode = '42501';
    end if;
    if old.expires_at is not null and old.expires_at <= now()
       and (new.expires_at is null or new.expires_at > now()) then
      raise exception 'an expired access is not revived' using errcode = '42501';
    end if;
    if old.revoked_at is not null and new.revoked_at is null then
      raise exception 'a revoked access is not revived' using errcode = '42501';
    end if;
    if new.level = 'caregiver' and old.level <> 'caregiver' then
      raise exception 'a caregiver accepts an invitation' using errcode = '42501';
    end if;
  end if;
  return new;
end $$
"""

# a withdrawn caregiver_sharing consent ends the owner's open invitations at once; access
# already given stays until the owner revokes it (OPEN_QUESTIONS Q42)
_CONSENT_WITHDRAWN = f"""
create function consents_caregiver_withdrawn() returns trigger
language plpgsql {_DEFINER} as $$
begin
  update public.caregiver_invitations set status = 'revoked', responded_at = now()
    where invited_by = new.user_id and status = 'pending';
  return null;
end $$
"""

_POLICIES = [
    # invitations: the owner and the invited person; written by the functions only
    """create policy caregiver_invitations_select on caregiver_invitations for select
       to labtrack_app using (invited_user_id = app_user_id() or is_owner(patient_id))""",
    "grant select on caregiver_invitations to labtrack_app",
    # alert settings: the caregiver and the owner; written by the functions only
    """create policy caregiver_alert_settings_select on caregiver_alert_settings for select
       to labtrack_app using (caregiver_user_id = app_user_id() or is_owner(patient_id))""",
    "grant select on caregiver_alert_settings to labtrack_app",
    # dose alerts: written as the caregiver (the worker acting for them) while alerts are on
    """create policy dose_alerts_select on dose_alerts for select to labtrack_app
       using ((alerted_user_id = app_user_id() and can_read_patient(patient_id))
              or is_owner(patient_id))""",
    """create policy dose_alerts_insert on dose_alerts for insert to labtrack_app
       with check (alerted_user_id = app_user_id() and caregiver_alerts_on(patient_id))""",
    "grant select on dose_alerts to labtrack_app",
    """grant insert (patient_id, medication_id, slot_at, alerted_user_id) on dose_alerts
       to labtrack_app""",
    "grant usage on sequence dose_alerts_id_seq to labtrack_app",
    # push receipts: the maintenance worker only
    """create policy push_receipts_maint on push_receipts for all to labtrack_maint
       using (true) with check (true)""",
    "grant select, insert, update, delete on push_receipts to labtrack_maint",
    "grant usage on sequence push_receipts_id_seq to labtrack_maint",
    # patient_access: the owner no longer grants 'caregiver' directly
    "drop policy access_insert on patient_access",
    """create policy access_insert on patient_access for insert to labtrack_app
       with check (is_owner(patient_id) and user_id <> app_user_id()
                   and level not in ('owner', 'caregiver') and is_shareable_user(user_id))""",
    """create trigger patient_access_app_rules before update on patient_access
       for each row execute function patient_access_app_rules()""",
    "revoke update on patient_access from labtrack_app",
    "grant update (level, scopes, expires_at, revoked_at) on patient_access to labtrack_app",
    # functions
    "revoke execute on all functions in schema public from public",
    """grant execute on function caregiver_alerts_on(uuid), invite_caregiver(uuid, text),
       respond_caregiver_invitation(uuid, boolean), revoke_caregiver_invitation(uuid),
       leave_patient(uuid), set_caregiver_alerts(uuid, int, boolean),
       pause_caregiver_alerts(uuid, uuid, boolean), my_caregiver_invitations(),
       set_session_push_token(uuid, text) to labtrack_app""",
    """grant execute on function maint_caregiver_alert_targets(), maint_push_queue(int),
       maint_mark_pushed(bigint[]), maint_forget_push_token(text) to labtrack_maint""",
]

_RLS = ["caregiver_invitations", "caregiver_alert_settings", "dose_alerts", "push_receipts"]


def upgrade() -> None:
    for sql in _TABLES:
        op.execute(sql)
    for table in _RLS:
        op.execute(f"alter table {table} enable row level security")
        op.execute(f"alter table {table} force row level security")
        op.execute(
            f"create policy {table}_owner on {table} for all to labtrack_owner"
            " using (true) with check (true)"
        )
        op.execute(f"revoke truncate on {table} from public")
    op.execute("alter table notifications drop constraint notifications_kind_check")
    op.execute(
        f"alter table notifications add constraint notifications_kind_check"
        f" check (kind in ({_NOTIFY_NEW}))"
    )
    for sql in _FUNCTIONS:
        op.execute(sql)
    op.execute(_NOTIFY)
    op.execute(_ACCESS_RULES)
    op.execute(_CONSENT_WITHDRAWN)
    op.execute(
        """create trigger consents_caregiver_withdrawn after insert on consents
           for each row when (new.kind = 'caregiver_sharing' and not new.granted)
           execute function consents_caregiver_withdrawn()"""
    )
    for sql in _POLICIES:
        op.execute(sql)
    # the grants above revoked execute from public for every function: restore the app's own
    op.execute(
        """grant execute on function app_user_id() to labtrack_app, labtrack_admin,
           labtrack_maint"""
    )


def downgrade() -> None:
    op.execute(
        "revoke update (level, scopes, expires_at, revoked_at) on patient_access from labtrack_app"
    )
    op.execute("grant update on patient_access to labtrack_app")
    op.execute("drop trigger consents_caregiver_withdrawn on consents")
    op.execute("drop function consents_caregiver_withdrawn()")
    op.execute("drop trigger patient_access_app_rules on patient_access")
    op.execute("drop function patient_access_app_rules()")
    op.execute("drop policy access_insert on patient_access")
    op.execute(
        """create policy access_insert on patient_access for insert to labtrack_app
           with check (is_owner(patient_id) and user_id <> app_user_id() and level <> 'owner'
                       and is_shareable_user(user_id))"""
    )
    op.execute(_NOTIFY_PREVIOUS)
    for name in (
        "maint_forget_push_token(text)",
        "maint_mark_pushed(bigint[])",
        "maint_push_queue(int)",
        "maint_caregiver_alert_targets()",
        "set_session_push_token(uuid, text)",
        "my_caregiver_invitations()",
        "pause_caregiver_alerts(uuid, uuid, boolean)",
        "set_caregiver_alerts(uuid, int, boolean)",
        "leave_patient(uuid)",
        "revoke_caregiver_invitation(uuid)",
        "respond_caregiver_invitation(uuid, boolean)",
        "invite_caregiver(uuid, text)",
    ):
        op.execute(f"drop function {name}")
    op.execute("delete from notifications where kind = 'dose_overdue'")
    op.execute("alter table notifications drop constraint notifications_kind_check")
    op.execute(
        f"alter table notifications add constraint notifications_kind_check"
        f" check (kind in ({_NOTIFY_OLD}))"
    )
    for table in reversed(_RLS):
        op.execute(f"drop table {table}")
    op.execute("drop function caregiver_alerts_on(uuid)")
    op.execute("drop function caregiver_sharing_given(uuid)")
    op.execute("drop function caregiver_audit(text, text, text, uuid, jsonb)")
