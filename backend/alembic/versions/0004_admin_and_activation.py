"""Admin and activation functions - the only write paths for account administration.

docs/04 §1, §6 (v7.2): the admin never knows a password and never touches patient data.
Every rule is enforced here, not in the API, so a compromised admin service or an injected
statement cannot take over an account:
- the acting admin is always app.user_id (set per transaction by the admin API), never a
  parameter; it must be an active super_admin (support may only unlock);
- targets are only 'user'/'doctor' accounts - admins cannot change other admins;
- identity checks are computed by the database (bcrypt via pgcrypto + pepper), rate-limited,
  and a reset token needs a successful check of the same user by the same admin <= 10 min old;
- token lifetimes are fixed here (QR 15 min, SMS 24 h); one live token per user;
- a reset clears the old password, revokes every session and bumps token_version.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-28
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEFINER = "security definer set search_path = pg_catalog, public, pg_temp"

_FUNCTIONS = [
    # The acting admin from the transaction context; raises unless active with an allowed role.
    f"""
    create function admin_actor(p_roles user_role[]) returns uuid
    language plpgsql stable {_DEFINER} as $$
    declare
      actor uuid := public.app_user_id();
    begin
      if actor is null or not exists (
           select 1 from public.users
           where id = actor and role = any (p_roles) and account_status = 'active'
             and deleted_at is null) then
        raise exception 'admin not allowed' using errcode = '42501';
      end if;
      return actor;
    end $$
    """,
    f"""
    create function admin_target(p_user_id uuid) returns void
    language plpgsql stable {_DEFINER} as $$
    begin
      if not exists (select 1 from public.users
                     where id = p_user_id and role in ('user','doctor') and deleted_at is null) then
        raise exception 'target not allowed' using errcode = '42501';
      end if;
    end $$
    """,
    f"""
    create function admin_audit(p_actor uuid, p_action text, p_target uuid, p_diff jsonb)
    returns void language sql volatile {_DEFINER} as $$
      insert into public.audit_logs (actor_id, actor_role, action, target_user_id, entity,
                                     entity_id, diff)
      select u.id, u.role::text, p_action, p_target, 'user', p_target::text, p_diff
      from public.users u where u.id = p_actor
    $$
    """,
    f"""
    create function revoke_user_sessions(p_user_id uuid, p_reason text) returns void
    language sql volatile {_DEFINER} as $$
      update public.sessions set revoked_at = now(), revoked_reason = p_reason
      where user_id = p_user_id and revoked_at is null;
      update public.users set token_version = token_version + 1 where id = p_user_id;
    $$
    """,
    f"""
    create function admin_create_user(p_username text, p_display_name text, p_role user_role,
                                      p_phone_enc bytea, p_phone_last4 text,
                                      p_national_id text, p_pepper text)
    returns uuid language plpgsql volatile {_DEFINER} as $$
    declare
      actor uuid := public.admin_actor(array['super_admin']::public.user_role[]);
      uid uuid;
    begin
      if p_role not in ('user','doctor') then
        raise exception 'admins are created with the CLI only' using errcode = '42501';
      end if;
      if p_national_id is not null
         and (p_pepper is null or length(p_pepper) not between 16 and 60) then
        raise exception 'pepper required' using errcode = '22023';
      end if;
      insert into public.users (username, display_name, role, contact_phone_enc,
                                contact_phone_last4, identity_check_hash, created_by)
        values (p_username, p_display_name, p_role, p_phone_enc, p_phone_last4,
                case when p_national_id is null then null
                     else public.crypt(upper(p_national_id) || p_pepper, public.gen_salt('bf', 12))
                end,
                actor)
        returning id into uid;
      -- The "Би" profile belongs to the new user; the admin gets no access to it.
      with p as (
        insert into public.patients (full_name, relation, created_by)
          values (p_display_name, 'self', uid) returning id)
      insert into public.patient_access (patient_id, user_id, level, scopes, granted_by)
        select p.id, uid, 'owner', '{{*}}', uid from p;
      perform public.admin_audit(actor, 'admin.user_create', uid, null);
      return uid;
    end $$
    """,
    # Result computed here from the stored hash; the admin only learns yes/no.
    f"""
    create function admin_identity_check(p_user_id uuid, p_candidate text, p_pepper text)
    returns table (check_id bigint, success boolean)
    language plpgsql volatile {_DEFINER} as $$
    declare
      actor uuid := public.admin_actor(array['super_admin']::public.user_role[]);
      stored text;
      ok boolean;
      cid bigint;
    begin
      perform public.admin_target(p_user_id);
      if (select count(*) from public.identity_checks
          where user_id = p_user_id and at > now() - interval '1 day') >= 5
         or (select count(*) from public.identity_checks
             where admin_id = actor and at > now() - interval '1 day') >= 50 then
        raise exception 'identity check limit reached' using errcode = '54000';
      end if;
      select identity_check_hash into stored from public.users where id = p_user_id;
      if stored is null then
        raise exception 'no identity data: verify in person' using errcode = '22023';
      end if;
      ok := public.crypt(upper(p_candidate) || p_pepper, stored) = stored;
      insert into public.identity_checks (user_id, admin_id, success)
        values (p_user_id, actor, ok) returning id into cid;
      perform public.admin_audit(actor, 'admin.identity_check', p_user_id,
                                 jsonb_build_object('success', ok));
      return query select cid, ok;
    end $$
    """,
    f"""
    create function admin_issue_token(p_user_id uuid, p_purpose text, p_channel text,
                                      p_token_hash text, p_identity_check_id bigint)
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
      else
        raise exception 'unknown purpose' using errcode = '22023';
      end if;
      expires := now() + case p_channel when 'in_person_qr' then interval '15 minutes'
                                        when 'sms' then interval '24 hours' end;
      if expires is null then
        raise exception 'unknown channel' using errcode = '22023';
      end if;
      update public.activation_tokens set revoked_at = now()
        where user_id = p_user_id and used_at is null and revoked_at is null;
      insert into public.activation_tokens (user_id, token_hash, purpose, channel, issued_by,
                                            identity_check_id, expires_at)
        values (p_user_id, p_token_hash, p_purpose, p_channel, actor,
                case when p_purpose = 'admin_reset' then p_identity_check_id end, expires);
      if p_purpose = 'admin_reset' then
        -- The old password stops working now; nobody (including the admin) can log in until
        -- the user sets a new one with the token.
        update public.users set password_hash = null where id = p_user_id;
        perform public.revoke_user_sessions(p_user_id, 'admin_reset');
        insert into public.notifications (user_id, kind, title_key)
          values (p_user_id, 'admin_reset', 'account.admin_reset');
      end if;
      perform public.admin_audit(actor, 'admin.token_issue', p_user_id,
                                 jsonb_build_object('purpose', p_purpose, 'channel', p_channel));
      return expires;
    end $$
    """,
    f"""
    create function admin_set_status(p_user_id uuid, p_status text) returns void
    language plpgsql volatile {_DEFINER} as $$
    declare
      actor uuid;
      current_status text;
    begin
      perform public.admin_target(p_user_id);
      select account_status into current_status from public.users where id = p_user_id;
      if p_status = 'active' and current_status = 'locked' then
        actor := public.admin_actor(array['super_admin','support']::public.user_role[]);
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
      perform public.admin_audit(actor, 'admin.status_' || p_status, p_user_id, null);
    end $$
    """,
    f"""
    create function admin_reveal_phone(p_user_id uuid) returns bytea
    language plpgsql volatile {_DEFINER} as $$
    declare
      actor uuid := public.admin_actor(array['super_admin','support']::public.user_role[]);
      phone bytea;
    begin
      perform public.admin_target(p_user_id);
      select contact_phone_enc into phone from public.users where id = p_user_id;
      perform public.admin_audit(actor, 'admin.phone_reveal', p_user_id, null);
      return phone;
    end $$
    """,
    # User side (no user context yet): a valid token sets the user's own password.
    f"""
    create function activation_consume(p_token_hash text, p_password_hash text) returns uuid
    language plpgsql volatile {_DEFINER} as $$
    declare
      tok record;
    begin
      if p_password_hash !~ '^[$]argon2id[$]' then
        raise exception 'password hash must be argon2id' using errcode = '22023';
      end if;
      select * into tok from public.activation_tokens
        where token_hash = p_token_hash and used_at is null and revoked_at is null
          and expires_at > now()
        for update;
      if not found then
        raise exception 'invalid or expired token' using errcode = '28000';
      end if;
      update public.activation_tokens set used_at = now() where id = tok.id;
      update public.users
        set password_hash = p_password_hash, password_changed_at = now(),
            account_status = 'active'
        where id = tok.user_id and account_status in ('pending_activation','active','locked');
      if not found then
        raise exception 'account cannot be activated' using errcode = '28000';
      end if;
      if tok.purpose = 'admin_reset' then
        perform public.revoke_user_sessions(tok.user_id, 'admin_reset');
      end if;
      insert into public.audit_logs (actor_id, actor_role, action, target_user_id)
        select tok.user_id, role::text, 'account.password_set', tok.user_id
        from public.users where id = tok.user_id;
      return tok.user_id;
    end $$
    """,
]

_GRANTS = [
    "revoke execute on all functions in schema public from public",
    """grant execute on function
       admin_create_user(text, text, user_role, bytea, text, text, text),
       admin_identity_check(uuid, text, text),
       admin_issue_token(uuid, text, text, text, bigint),
       admin_set_status(uuid, text),
       admin_reveal_phone(uuid)
       to labtrack_admin""",
    "grant execute on function activation_consume(text, text) to labtrack_app",
]


def upgrade() -> None:
    for sql in _FUNCTIONS + _GRANTS:
        op.execute(sql)


def downgrade() -> None:
    for fn in (
        "activation_consume(text, text)",
        "admin_reveal_phone(uuid)",
        "admin_set_status(uuid, text)",
        "admin_issue_token(uuid, text, text, text, bigint)",
        "admin_identity_check(uuid, text, text)",
        "admin_create_user(text, text, user_role, bytea, text, text, text)",
        "revoke_user_sessions(uuid, text)",
        "admin_audit(uuid, text, uuid, jsonb)",
        "admin_target(uuid)",
        "admin_actor(user_role[])",
    ):
        op.execute(f"drop function if exists {fn}")
