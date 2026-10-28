"""Admin sign-in, admin sessions and the remaining admin operations (docs/04 §1, §6).

- Admins sign in with password + TOTP to their own short sessions (8 h, 15 min idle). Sign-in
  runs as its own role, labtrack_admin_login (the only role that can read admin password
  hashes or create admin sessions); the admin API role cannot mint sessions. Every admin_*
  function needs the acting admin's live session, begun in the same transaction
  (admin_session_begin records the transaction id), so a session id seen once cannot be
  replayed with set_config in a later transaction.
- A TOTP code is accepted once and only for the current time step +-1 (users.totp_last_step),
  and the database refuses user sessions for admin accounts (admins never hold a user JWT, so
  never reach PHI routes); user sessions admins already had are revoked.
- admin_create_user takes the new id from the caller, so the phone number can be encrypted
  with its row id as associated data before the insert.
- Status changes and reset tokens carry a reason code (an enum, so no free text - which could
  hold health details - reaches the audit log).
- A reset/activation token remembers the issuing admin's address; using it from that network
  (or with admin credentials) is refused for SMS and flagged for in-person QR (docs/04 §6.1).
- The admin who enrolled a user's national id cannot also issue that user a reset for 7 days
  (one admin alone cannot take an account over), and the user is notified.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-28
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEFINER = "security definer set search_path = pg_catalog, public, pg_temp"

_KINDS_OLD = "'login','activation','change_password','identity_check','share_pin','share_lookup'"
_KINDS_NEW = _KINDS_OLD + ",'admin_login','admin_unlock'"
_NOTIFY_OLD = "'review_ready','critical_pending','share_invite','admin_reset','reminder'"
_NOTIFY_NEW = _NOTIFY_OLD + ",'admin_action'"

_UP = [
    "alter table users add column totp_last_step bigint",
    "alter table auth_attempts drop constraint auth_attempts_kind_check",
    "alter table auth_attempts add constraint auth_attempts_kind_check"
    f" check (kind in ({_KINDS_NEW}))",
    "alter table activation_tokens add column issued_ip inet",
    "alter table users add constraint users_totp_step_positive"
    " check (totp_last_step is null or totp_last_step > 0)",
    "alter table notifications drop constraint notifications_kind_check",
    "alter table notifications add constraint notifications_kind_check"
    f" check (kind in ({_NOTIFY_NEW}))",
    """
    create table admin_sessions (
      id uuid primary key default gen_random_uuid(),
      admin_id uuid not null references users on delete cascade,
      token_hash text not null unique check (token_hash ~ '^[0-9a-f]{64}$'),
      ip inet,
      created_at timestamptz not null default now(),
      last_seen_at timestamptz not null default now(),
      expires_at timestamptz not null,
      revoked_at timestamptz,
      revoked_reason text
        check (revoked_reason in ('logout','idle','expired','account_inactive','superseded')),
      -- the transaction that last began this session; admin_actor() requires the current one
      begun_xid xid8
    )
    """,
    "create index on admin_sessions (admin_id) where revoked_at is null",
    "alter table admin_sessions enable row level security",
    "alter table admin_sessions force row level security",
    # Nobody but the owner (definer functions, test fixtures) touches admin sessions directly.
    """create policy admin_sessions_owner on admin_sessions for all to labtrack_owner
       using (true) with check (true)""",
    # IPv4 by address, IPv6 by /64 (one subscriber), as client_network() in the API.
    """
    create function ip_net(p inet) returns cidr language sql immutable
    set search_path = pg_catalog as $$
      select case when p is null then null
                  when family(p) = 6 then network(set_masklen(p, 64))
                  else network(set_masklen(p, 32)) end
    $$
    """,
    # --- admin sessions ------------------------------------------------------------------------
    f"""
    create function admin_login_lookup(p_username text)
    returns table (user_id uuid, password_hash text, totp_secret_enc bytea,
                   account_status text, role user_role)
    language sql stable {_DEFINER} as $$
      select id, password_hash, totp_secret_enc, account_status, role from public.users
      where username = p_username::citext and role in ('super_admin','support')
        and deleted_at is null
    $$
    """,
    f"""
    create function admin_login_failure(p_username text, p_ip inet) returns void
    language sql volatile {_DEFINER} as $$
      insert into public.auth_attempts (kind, username, ip, success)
      values ('admin_login', p_username, p_ip, false)
    $$
    """,
    # Called by the API only after it verified the password and the TOTP code (argon2 and TOTP
    # run in Python). The step check makes each code single-use even across admin API replicas.
    f"""
    create function admin_session_create(p_user_id uuid, p_token_hash text, p_ip inet,
                                         p_totp_step bigint)
    returns timestamptz language plpgsql volatile {_DEFINER} as $$
    declare
      u public.users%rowtype;
      expires timestamptz := now() + interval '8 hours';
    begin
      if p_token_hash !~ '^[0-9a-f]{{64}}$' then
        raise exception 'invalid session parameters' using errcode = '22023';
      end if;
      -- Only near the current step (+-2 for clock skew): a null step would disable replay
      -- protection and a far future one would lock the admin out.
      if p_totp_step is null or abs(p_totp_step
           - floor(extract(epoch from clock_timestamp()) / 30)::bigint) > 2 then
        raise exception 'invalid totp step' using errcode = '22023';
      end if;
      select * into u from public.users where id = p_user_id for update;
      if not found or u.role not in ('super_admin','support') or u.account_status <> 'active'
         or u.deleted_at is not null or u.totp_secret_enc is null then
        raise exception 'admin not allowed' using errcode = '28000';
      end if;
      if u.totp_last_step is not null and p_totp_step <= u.totp_last_step then
        raise exception 'totp code already used' using errcode = '28000';
      end if;
      -- The API serialises sign-in per username and applies the lockout policy; this is the
      -- floor if it does not: no session after 10 failures since the last success (24 h).
      if (select count(*) from public.auth_attempts a
          where a.kind = 'admin_login' and a.username = u.username and not a.success
            and a.at > now() - interval '24 hours'
            and a.at > coalesce((select max(b.at) from public.auth_attempts b
                                 where b.kind in ('admin_login','admin_unlock')
                                   and b.username = u.username and b.success),
                                '-infinity')) >= 10 then
        raise exception 'admin not allowed' using errcode = '28000';
      end if;
      update public.users set totp_last_step = p_totp_step where id = p_user_id;
      insert into public.auth_attempts (kind, username, ip, success)
        values ('admin_login', u.username, public.ip_net(p_ip), true);
      insert into public.admin_sessions (admin_id, token_hash, ip, expires_at)
        values (p_user_id, p_token_hash, p_ip, expires);
      -- At most 3 live sessions per admin: the oldest beyond that end.
      update public.admin_sessions set revoked_at = now(), revoked_reason = 'superseded'
        where admin_id = p_user_id and revoked_at is null
          and id not in (select x.id from public.admin_sessions x
                         where x.admin_id = p_user_id and x.revoked_at is null
                         order by x.created_at desc limit 3);
      perform public.admin_audit(p_user_id, 'admin.login', null, null);
      return expires;
    end $$
    """,
    # Per request: validates the session, slides the idle window and sets the transaction's
    # admin context (app.user_id + app.admin_sid) that admin_actor() requires.
    f"""
    create function admin_session_begin(p_token_hash text)
    returns table (admin_id uuid, role user_role, expires_at timestamptz)
    language plpgsql volatile {_DEFINER} as $$
    declare
      s public.admin_sessions%rowtype;
      r public.user_role;
    begin
      select * into s from public.admin_sessions
        where token_hash = p_token_hash and revoked_at is null for update;
      if not found then
        return;
      end if;
      if s.expires_at <= now() or s.last_seen_at <= now() - interval '15 minutes' then
        update public.admin_sessions
          set revoked_at = now(),
              revoked_reason = case when s.expires_at <= now() then 'expired' else 'idle' end
          where id = s.id;
        return;
      end if;
      select u.role into r from public.users u
        where u.id = s.admin_id and u.role in ('super_admin','support')
          and u.account_status = 'active' and u.deleted_at is null;
      if not found then
        update public.admin_sessions set revoked_at = now(), revoked_reason = 'account_inactive'
          where id = s.id;
        return;
      end if;
      -- The row lock taken above is held until this transaction ends, so a concurrent request
      -- of the same session waits instead of overwriting begun_xid.
      update public.admin_sessions set last_seen_at = now(), begun_xid = pg_current_xact_id()
        where id = s.id;
      perform set_config('app.user_id', s.admin_id::text, true);
      perform set_config('app.admin_sid', s.id::text, true);
      return query select s.admin_id, r, s.expires_at;
    end $$
    """,
    f"""
    create function admin_session_end(p_token_hash text) returns void
    language sql volatile {_DEFINER} as $$
      update public.admin_sessions set revoked_at = now(), revoked_reason = 'logout'
      where token_hash = p_token_hash and revoked_at is null
    $$
    """,
    # Now also requires the live admin session begun in this very transaction.
    f"""
    create or replace function admin_actor(p_roles user_role[]) returns uuid
    language plpgsql stable {_DEFINER} as $$
    declare
      actor uuid := public.app_user_id();
      sid uuid := nullif(current_setting('app.admin_sid', true), '')::uuid;
    begin
      if actor is null or sid is null or not exists (
           select 1 from public.users u join public.admin_sessions s on s.admin_id = u.id
           where u.id = actor and u.role = any (p_roles) and u.account_status = 'active'
             and u.deleted_at is null and s.id = sid and s.revoked_at is null
             and s.expires_at > now() and s.last_seen_at > now() - interval '15 minutes'
             and s.begun_xid = pg_current_xact_id()) then
        raise exception 'admin not allowed' using errcode = '42501';
      end if;
      return actor;
    end $$
    """,
    # --- account administration ------------------------------------------------------------------
    "drop function admin_create_user(text, text, user_role, bytea, text, text, text)",
    f"""
    create function admin_create_user(p_user_id uuid, p_username text, p_display_name text,
                                      p_role user_role, p_phone_enc bytea, p_phone_last4 text,
                                      p_national_id text, p_pepper text)
    returns uuid language plpgsql volatile {_DEFINER} as $$
    declare
      actor uuid := public.admin_actor(array['super_admin']::public.user_role[]);
    begin
      if p_role not in ('user','doctor') then
        raise exception 'admins are created with the CLI only' using errcode = '42501';
      end if;
      if p_user_id is null then
        raise exception 'user id required' using errcode = '22023';
      end if;
      if p_national_id is not null
         and (p_pepper is null or length(p_pepper) not between 16 and 60) then
        raise exception 'pepper required' using errcode = '22023';
      end if;
      insert into public.users (id, username, display_name, role, contact_phone_enc,
                                contact_phone_last4, identity_check_hash, created_by)
        values (p_user_id, p_username, p_display_name, p_role, p_phone_enc, p_phone_last4,
                case when p_national_id is null then null
                     else public.crypt(upper(p_national_id) || p_pepper, public.gen_salt('bf', 12))
                end,
                actor);
      -- The "Би" profile belongs to the new user; the admin gets no access to it.
      with p as (
        insert into public.patients (full_name, relation, created_by)
          values (p_display_name, 'self', p_user_id) returning id)
      insert into public.patient_access (patient_id, user_id, level, scopes, granted_by)
        select p.id, p_user_id, 'owner', '{{*}}', p_user_id from p;
      perform public.admin_audit(actor, 'admin.user_create', p_user_id,
                                 jsonb_build_object('identity', p_national_id is not null));
      return p_user_id;
    end $$
    """,
    # In person, from the ID card, for accounts created without a national id (CSV, doctors).
    # Never overwrites: changing a stored identity would let a caller redirect resets.
    f"""
    create function admin_set_identity(p_user_id uuid, p_national_id text, p_pepper text)
    returns void language plpgsql volatile {_DEFINER} as $$
    declare
      actor uuid := public.admin_actor(array['super_admin']::public.user_role[]);
    begin
      perform public.admin_target(p_user_id);
      if p_national_id is null or p_pepper is null or length(p_pepper) not between 16 and 60 then
        raise exception 'pepper required' using errcode = '22023';
      end if;
      update public.users
        set identity_check_hash = public.crypt(upper(p_national_id) || p_pepper,
                                               public.gen_salt('bf', 12))
        where id = p_user_id and identity_check_hash is null;
      if not found then
        raise exception 'identity already set' using errcode = '42501';
      end if;
      insert into public.notifications (user_id, kind, title_key)
        values (p_user_id, 'admin_action', 'account.identity_set');
      perform public.admin_audit(actor, 'admin.identity_set', p_user_id, null);
    end $$
    """,
    "drop function admin_issue_token(uuid, text, text, text, bigint)",
    f"""
    create function admin_issue_token(p_user_id uuid, p_purpose text, p_channel text,
                                      p_token_hash text, p_identity_check_id bigint,
                                      p_reason text, p_admin_ip inet)
    returns timestamptz language plpgsql volatile {_DEFINER} as $$
    declare
      actor uuid := public.admin_actor(array['super_admin']::public.user_role[]);
      status text;
      expires timestamptz;
    begin
      perform public.admin_target(p_user_id);
      if p_token_hash !~ '^[0-9a-f]{{64}}$' then
        raise exception 'token hash must be sha256 hex' using errcode = '22023';
      end if;
      select account_status into status from public.users where id = p_user_id;
      if p_purpose = 'activation' then
        if status <> 'pending_activation' then
          raise exception 'account is already activated' using errcode = '42501';
        end if;
      elsif p_purpose = 'admin_reset' then
        if p_reason is null or p_reason not in
             ('forgot_password','lost_device','suspected_compromise','other') then
          raise exception 'reason required' using errcode = '22023';
        end if;
        if status = 'disabled' then
          raise exception 'account is disabled' using errcode = '42501';
        end if;
        if not exists (
             select 1 from public.identity_checks c
             where c.id = p_identity_check_id and c.user_id = p_user_id and c.admin_id = actor
               and c.success and c.at > now() - interval '10 minutes'
               and not exists (select 1 from public.activation_tokens t
                               where t.identity_check_id = c.id)) then
          raise exception 'a fresh successful identity check is required' using errcode = '42501';
        end if;
        -- One admin must not both enrol the identity and use it for a reset.
        if exists (select 1 from public.audit_logs l
                   where (l.action = 'admin.identity_set'
                          or (l.action = 'admin.user_create' and l.diff ->> 'identity' = 'true'))
                     and l.actor_id = actor
                     and l.target_user_id = p_user_id and l.at > now() - interval '7 days') then
          raise exception 'identity was enrolled by this admin: another admin must reset'
            using errcode = '42501';
        end if;
      else
        raise exception 'unknown purpose' using errcode = '22023';
      end if;
      expires := now() + case p_channel when 'in_person_qr' then interval '15 minutes'
                                        when 'sms' then interval '24 hours' end;
      if expires is null then
        raise exception 'unknown channel' using errcode = '22023';
      end if;
      if p_channel = 'sms' and p_admin_ip is null then
        raise exception 'admin address required' using errcode = '22023';
      end if;
      update public.activation_tokens set revoked_at = now()
        where user_id = p_user_id and used_at is null and revoked_at is null;
      insert into public.activation_tokens (user_id, token_hash, purpose, channel, issued_by,
                                            identity_check_id, expires_at, issued_ip)
        values (p_user_id, p_token_hash, p_purpose, p_channel, actor,
                case when p_purpose = 'admin_reset' then p_identity_check_id end, expires,
                p_admin_ip);
      if p_purpose = 'admin_reset' then
        -- The old password stops working now; nobody (including the admin) can log in until
        -- the user sets a new one with the token.
        update public.users set password_hash = null where id = p_user_id;
        perform public.revoke_user_sessions(p_user_id, 'admin_reset');
        insert into public.notifications (user_id, kind, title_key)
          values (p_user_id, 'admin_reset', 'account.admin_reset');
      end if;
      perform public.admin_audit(actor, 'admin.token_issue', p_user_id,
                                 jsonb_build_object('purpose', p_purpose, 'channel', p_channel,
                                                    'reason', p_reason));
      return expires;
    end $$
    """,
    "drop function admin_set_status(uuid, text)",
    f"""
    create function admin_set_status(p_user_id uuid, p_status text, p_reason text)
    returns void language plpgsql volatile {_DEFINER} as $$
    declare
      actor uuid := public.admin_actor(array['super_admin','support']::public.user_role[]);
      current_status text;
    begin
      perform public.admin_target(p_user_id);
      if p_reason is null or p_reason not in
           ('user_request','identity_verified','suspected_compromise','left_program','other') then
        raise exception 'reason required' using errcode = '22023';
      end if;
      select account_status into current_status from public.users where id = p_user_id;
      if p_status = 'active' and current_status = 'locked' then
        -- A lock for suspected compromise is lifted by a super admin, not support.
        if exists (select 1 from public.users where id = actor and role = 'support')
           and (select l.diff ->> 'reason' from public.audit_logs l
                where l.action = 'admin.status_locked' and l.target_user_id = p_user_id
                order by l.at desc limit 1) = 'suspected_compromise' then
          raise exception 'admin not allowed' using errcode = '42501';
        end if;
      elsif p_status in ('active','locked','disabled') and current_status <> 'pending_activation'
      then
        actor := public.admin_actor(array['super_admin']::public.user_role[]);
      else
        raise exception 'status change not allowed' using errcode = '42501';
      end if;
      update public.users set account_status = p_status where id = p_user_id;
      if p_status in ('locked','disabled') then
        perform public.revoke_user_sessions(p_user_id, 'disabled');
      end if;
      perform public.admin_audit(actor, 'admin.status_' || p_status, p_user_id,
                                 jsonb_build_object('reason', p_reason));
    end $$
    """,
    # Clears the login lockout counters (they count failures since the last success).
    f"""
    create function admin_clear_lockout(p_user_id uuid) returns void
    language plpgsql volatile {_DEFINER} as $$
    declare
      actor uuid := public.admin_actor(array['super_admin','support']::public.user_role[]);
    begin
      perform public.admin_target(p_user_id);
      insert into public.auth_attempts (kind, username, success)
        select 'login', username, true from public.users where id = p_user_id;
      insert into public.auth_attempts (kind, username, success)
        select 'admin_unlock', username, true from public.users where id = p_user_id;
      perform public.admin_audit(actor, 'admin.lockout_clear', p_user_id, null);
    end $$
    """,
    # CSV import: only the file hash and the row count are recorded (the file itself is PHI).
    f"""
    create function admin_log_import(p_file_sha256 text, p_rows int) returns void
    language plpgsql volatile {_DEFINER} as $$
    declare
      actor uuid := public.admin_actor(array['super_admin']::public.user_role[]);
    begin
      if p_file_sha256 !~ '^[0-9a-f]{{64}}$' or p_rows < 0 then
        raise exception 'invalid import record' using errcode = '22023';
      end if;
      perform public.admin_audit(actor, 'admin.csv_import', null,
                                 jsonb_build_object('sha256', p_file_sha256, 'rows', p_rows));
    end $$
    """,
    f"""
    create function admin_security_events(p_limit int)
    returns table (id bigint, at timestamptz, action text, actor_id uuid, target_user_id uuid,
                   diff jsonb)
    language plpgsql stable {_DEFINER} as $$
    begin
      perform public.admin_actor(array['super_admin']::public.user_role[]);
      return query
        select l.id, l.at, l.action, l.actor_id, l.target_user_id, l.diff
        from public.audit_logs l where l.action like 'security.%'
        order by l.at desc limit least(greatest(p_limit, 1), 200);
    end $$
    """,
    # --- user side -------------------------------------------------------------------------
    "drop function activation_consume(text, text)",
    # status: ok | invalid | refused. A refusal is returned (not raised) so that the revocation
    # and the security event commit.
    f"""
    create function activation_consume(p_token_hash text, p_password_hash text, p_ip inet,
                                       p_admin_present boolean)
    returns table (status text, user_id uuid)
    language plpgsql volatile {_DEFINER} as $$
    declare
      tok record;
      same_net boolean;
    begin
      if p_password_hash !~ '^[$]argon2id[$]' then
        raise exception 'password hash must be argon2id' using errcode = '22023';
      end if;
      select * into tok from public.activation_tokens
        where token_hash = p_token_hash and used_at is null and revoked_at is null
          and expires_at > now()
        for update;
      if not found then
        insert into public.auth_attempts (kind, ip, success)
          values ('activation', public.ip_net(p_ip), false);
        return query select 'invalid', null::uuid;
        return;
      end if;
      same_net := coalesce(public.ip_net(p_ip) = public.ip_net(tok.issued_ip), false);
      -- docs/04 §6.1: the issuing admin must not use the token. An SMS link opened from the
      -- admin's own network, or any token used with admin credentials, is refused and
      -- reported. An in-person QR may share the office network, so it is only reported.
      if p_admin_present or (same_net and tok.channel = 'sms') then
        update public.activation_tokens set revoked_at = now() where id = tok.id;
        insert into public.audit_logs (actor_id, actor_role, action, target_user_id, diff)
          select tok.issued_by, u.role::text, 'security.admin_token_self_use', tok.user_id,
                 jsonb_build_object('purpose', tok.purpose, 'channel', tok.channel,
                                    'admin_credentials', p_admin_present, 'refused', true)
          from public.users u where u.id = tok.issued_by;
        insert into public.auth_attempts (kind, ip, success)
          values ('activation', public.ip_net(p_ip), false);
        return query select 'refused', null::uuid;
        return;
      end if;
      if same_net then
        insert into public.audit_logs (actor_id, actor_role, action, target_user_id, diff)
          select tok.issued_by, u.role::text, 'security.admin_network_activation', tok.user_id,
                 jsonb_build_object('purpose', tok.purpose, 'channel', tok.channel,
                                    'refused', false)
          from public.users u where u.id = tok.issued_by;
      end if;
      update public.activation_tokens set used_at = now() where id = tok.id;
      update public.users
        set password_hash = p_password_hash, password_changed_at = now(),
            account_status = 'active'
        where id = tok.user_id and account_status in ('pending_activation','active','locked');
      if not found then
        return query select 'invalid', null::uuid;
        return;
      end if;
      if tok.purpose = 'admin_reset' then
        perform public.revoke_user_sessions(tok.user_id, 'admin_reset');
      end if;
      insert into public.audit_logs (actor_id, actor_role, action, target_user_id)
        select tok.user_id, role::text, 'account.password_set', tok.user_id
        from public.users where id = tok.user_id;
      return query select 'ok', tok.user_id;
    end $$
    """,
    # Admin accounts never get a user session (their tokens must never reach PHI routes).
    f"""
    create or replace function auth_login_lookup(p_username text)
    returns table (user_id uuid, password_hash text, account_status text, token_version int,
                   role user_role)
    language sql stable {_DEFINER} as $$
      select id, password_hash, account_status, token_version, role from public.users
      where username = p_username::citext and deleted_at is null and role in ('user','doctor')
    $$
    """,
    f"""
    create or replace function session_create(p_user_id uuid, p_token_hash text,
                                              p_device_name text, p_platform text,
                                              p_device_hash text, p_device_was_trusted boolean,
                                              p_ip inet, p_ttl interval)
    returns table (session_id uuid, token_version int)
    language plpgsql volatile {_DEFINER} as $$
    declare
      u public.users%rowtype;
    begin
      if p_token_hash !~ '^[0-9a-f]{{64}}$' or p_ttl > interval '90 days'
         or (p_device_hash is not null and p_device_hash !~ '^[0-9a-f]{{64}}$') then
        raise exception 'invalid session parameters' using errcode = '22023';
      end if;
      select * into u from public.users where id = p_user_id;
      if u.account_status is distinct from 'active' or u.deleted_at is not null
         or u.role not in ('user','doctor') then
        raise exception 'account not active' using errcode = '28000';
      end if;
      -- The API calls this only after verifying the password (argon2 runs in Python, so the
      -- database cannot check it itself - see 0005). The success that resets the lockout
      -- counters is recorded here, never by a separately callable function.
      insert into public.auth_attempts (kind, username, ip, device_hash, device_trusted, success)
        values ('login', u.username, p_ip,
                case when p_device_was_trusted then p_device_hash end, p_device_was_trusted, true);
      if p_device_hash is not null then
        insert into public.trusted_devices (user_id, device_hash)
          values (p_user_id, p_device_hash)
          on conflict (user_id, device_hash) do update set last_seen_at = now();
      end if;
      return query
        insert into public.sessions (user_id, family_id, token_hash, device_name, platform,
                                     expires_at, device_trusted, last_used_at,
                                     issued_token_version, family_expires_at)
        values (p_user_id, gen_random_uuid(), p_token_hash, p_device_name, p_platform,
                now() + p_ttl, p_device_hash is not null, now(), u.token_version,
                now() + interval '180 days')
        returning id, u.token_version;
    end $$
    """,
    # The registered phone for the SMS that goes with a token this admin has just issued (link
    # or reset notice). The admin API sends it and never returns the number.
    f"""
    create function admin_sms_target(p_user_id uuid) returns bytea
    language plpgsql volatile {_DEFINER} as $$
    declare
      actor uuid := public.admin_actor(array['super_admin']::public.user_role[]);
    begin
      perform public.admin_target(p_user_id);
      if not exists (select 1 from public.activation_tokens t
                     where t.user_id = p_user_id and t.issued_by = actor
                       and t.created_at > now() - interval '1 minute'
                       and t.used_at is null and t.revoked_at is null
                       and (t.channel = 'sms' or t.purpose = 'admin_reset')) then
        raise exception 'admin not allowed' using errcode = '42501';
      end if;
      perform public.admin_audit(actor, 'admin.sms_target', p_user_id, null);
      return (select contact_phone_enc from public.users where id = p_user_id);
    end $$
    """,
    f"""
    create function admin_token_is_live(p_token_hash text) returns boolean
    language sql stable {_DEFINER} as $$
      select exists (select 1 from public.admin_sessions
                     where token_hash = p_token_hash and revoked_at is null
                       and expires_at > now())
    $$
    """,
    # Admins may still hold user sessions from before this revision: end them.
    """select public.revoke_user_sessions(id, 'disabled') from public.users
       where role in ('super_admin','support')""",
    "grant usage on schema public to labtrack_admin_login",
    "revoke execute on all functions in schema public from public",
    # Sign-in has its own role: the admin API role cannot read admin password hashes or mint
    # sessions, so an injected statement there cannot sign itself in.
    """grant execute on function
       admin_login_lookup(text),
       admin_login_failure(text, inet),
       admin_session_create(uuid, text, inet, bigint),
       auth_failure_counts(text, text, inet, text, interval)
       to labtrack_admin_login""",
    """grant execute on function
       admin_session_begin(text),
       admin_session_end(text),
       admin_create_user(uuid, text, text, user_role, bytea, text, text, text),
       admin_set_identity(uuid, text, text),
       admin_issue_token(uuid, text, text, text, bigint, text, inet),
       admin_set_status(uuid, text, text),
       admin_clear_lockout(uuid),
       admin_log_import(text, int),
       admin_sms_target(uuid),
       admin_security_events(int)
       to labtrack_admin""",
    """grant execute on function activation_consume(text, text, inet, boolean),
       admin_token_is_live(text) to labtrack_app""",
]


def _definitions(filename: str, attr: str, names: tuple[str, ...]) -> list[str]:
    """The original `create function` statements of an earlier revision, for downgrade."""
    import importlib.util  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    spec = importlib.util.spec_from_file_location(filename, Path(__file__).with_name(filename))
    if spec is None or spec.loader is None:
        raise RuntimeError(filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    statements: list[str] = getattr(module, attr)
    return [
        sql
        for sql in statements
        if any(
            f"create function {n}(" in sql or f"create or replace function {n}(" in sql
            for n in names
        )
    ]


def _user_roles_only() -> list[str]:
    rotate, check = _definitions(
        "0005_auth_functions.py", "_UP", ("session_rotate", "session_check")
    )
    rotate_old = "if u.account_status <> 'active' or u.deleted_at is not null then"
    check_old = "u.account_status = 'active' and u.deleted_at is null"
    if rotate.count(rotate_old) != 1 or check.count(check_old) != 1:
        raise RuntimeError("0005 session functions changed")
    return [
        rotate.replace("create function", "create or replace function", 1).replace(
            rotate_old,
            "if u.account_status <> 'active' or u.deleted_at is not null\n"
            "         or u.role not in ('user','doctor') then",
        ),
        check.replace("create function", "create or replace function", 1).replace(
            check_old, check_old + " and u.role in ('user','doctor')"
        ),
    ]


def upgrade() -> None:
    grants = _UP.index("revoke execute on all functions in schema public from public")
    for sql in _UP[:grants] + _user_roles_only() + _UP[grants:]:
        op.execute(sql)


def downgrade() -> None:
    for fn in (
        "activation_consume(text, text, inet, boolean)",
        "admin_security_events(int)",
        "admin_log_import(text, int)",
        "admin_clear_lockout(uuid)",
        "admin_set_status(uuid, text, text)",
        "admin_issue_token(uuid, text, text, text, bigint, text, inet)",
        "admin_set_identity(uuid, text, text)",
        "admin_create_user(uuid, text, text, user_role, bytea, text, text, text)",
        "admin_session_end(text)",
        "admin_session_begin(text)",
        "admin_session_create(uuid, text, inet, bigint)",
        "admin_login_failure(text, inet)",
        "admin_login_lookup(text)",
        "admin_token_is_live(text)",
        "admin_sms_target(uuid)",
        "admin_actor(user_role[])",
        "auth_login_lookup(text)",
        "session_create(uuid, text, text, text, text, boolean, inet, interval)",
        "session_rotate(text, text, interval)",
        "session_check(uuid, uuid, int)",
    ):
        op.execute(f"drop function if exists {fn}")
    for sql in _definitions(
        "0004_admin_and_activation.py",
        "_FUNCTIONS",
        (
            "admin_actor",
            "admin_create_user",
            "admin_issue_token",
            "admin_set_status",
            "activation_consume",
        ),
    ) + _definitions(
        "0005_auth_functions.py",
        "_UP",
        ("auth_login_lookup", "session_create", "session_rotate", "session_check"),
    ):
        op.execute(sql)
    op.execute("revoke execute on all functions in schema public from public")
    op.execute(
        """grant execute on function
           admin_create_user(text, text, user_role, bytea, text, text, text),
           admin_issue_token(uuid, text, text, text, bigint),
           admin_set_status(uuid, text)
           to labtrack_admin"""
    )
    op.execute(
        "revoke execute on function auth_failure_counts(text, text, inet, text, interval)"
        " from labtrack_admin_login"
    )
    op.execute("grant execute on function activation_consume(text, text) to labtrack_app")
    op.execute(
        "grant execute on function auth_login_lookup(text),"
        " session_create(uuid, text, text, text, text, boolean, inet, interval),"
        " session_rotate(text, text, interval), session_check(uuid, uuid, int) to labtrack_app"
    )
    op.execute("revoke usage on schema public from labtrack_admin_login")
    op.execute("drop function if exists ip_net(inet)")
    op.execute("drop table if exists admin_sessions")
    op.execute("alter table activation_tokens drop column if exists issued_ip")
    op.execute("delete from auth_attempts where kind in ('admin_login','admin_unlock')")
    op.execute("alter table auth_attempts drop constraint auth_attempts_kind_check")
    op.execute(
        "alter table auth_attempts add constraint auth_attempts_kind_check"
        f" check (kind in ({_KINDS_OLD}))"
    )
    op.execute("delete from notifications where kind = 'admin_action'")
    op.execute("alter table notifications drop constraint notifications_kind_check")
    op.execute(
        "alter table notifications add constraint notifications_kind_check"
        f" check (kind in ({_NOTIFY_OLD}))"
    )
    op.execute("alter table users drop column if exists totp_last_step")
