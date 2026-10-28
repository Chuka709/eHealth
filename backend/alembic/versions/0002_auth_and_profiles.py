"""Auth, accounts, patient profiles, consents, notifications, audit (docs/03, docs/04 §6).

Access model:
- labtrack_app   - user requests; every table below is RLS-filtered by app.user_id; secret
                   columns (password hash, TOTP, phone, identity hash) are not readable at all.
- labtrack_admin - /admin API; account rows only, never patient tables.
- labtrack_maint - retention jobs.
- labtrack_owner - migrations and the owner of security definer functions (needs explicit
                   policies because RLS is FORCEd for the owner too).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-28
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Every security definer function: fixed search_path (pg_temp last), schema-qualified tables,
# EXECUTE revoked from PUBLIC (0001 default) and granted per role below.
_DEFINER = "security definer set search_path = pg_catalog, public, pg_temp"

_TYPES = [
    "create type access_level as enum ('owner','caregiver','doctor','viewer')",
    "create type sex as enum ('male','female','unknown')",
    "create type user_role as enum ('user','doctor','support','super_admin')",
]

_TABLES = [
    """
    create table users (
      id uuid primary key default gen_random_uuid(),
      username citext unique not null check (username ~ '^[a-z0-9._]{3,32}$'),
      password_hash text,
      account_status text not null default 'pending_activation'
        check (account_status in ('pending_activation','active','locked','disabled')),
      token_version int not null default 0,
      contact_phone_enc bytea,
      contact_phone_last4 text check (contact_phone_last4 ~ '^[0-9]{4}$'),
      identity_check_hash text,
      created_by uuid references users,
      display_name text not null check (length(display_name) between 1 and 100),
      locale text not null default 'mn' check (locale in ('mn','en')),
      role user_role not null default 'user',
      totp_secret_enc bytea,
      emergency_card_unlocked boolean not null default false,
      password_changed_at timestamptz,
      created_at timestamptz not null default now(),
      deleted_at timestamptz,
      constraint users_pending_has_no_password
        check (account_status <> 'pending_activation' or password_hash is null)
    )
    """,
    """
    create table identity_checks (
      id bigserial primary key,
      user_id uuid not null references users on delete cascade,
      admin_id uuid not null references users,
      success boolean not null,
      at timestamptz not null default now()
    )
    """,
    "create index on identity_checks (user_id, at desc)",
    "create index on identity_checks (admin_id, at desc)",
    """
    create table activation_tokens (
      id uuid primary key default gen_random_uuid(),
      user_id uuid not null references users on delete cascade,
      token_hash text not null unique,
      purpose text not null check (purpose in ('activation','admin_reset')),
      channel text not null check (channel in ('in_person_qr','sms')),
      issued_by uuid not null references users,
      identity_check_id bigint references identity_checks,
      expires_at timestamptz not null,
      used_at timestamptz,
      revoked_at timestamptz,
      created_at timestamptz not null default now(),
      constraint reset_needs_identity_check
        check (purpose <> 'admin_reset' or identity_check_id is not null)
    )
    """,
    """create unique index activation_tokens_one_live on activation_tokens (user_id)
       where used_at is null and revoked_at is null""",
    """
    create table sessions (
      id uuid primary key default gen_random_uuid(),
      user_id uuid not null references users on delete cascade,
      family_id uuid not null,
      token_hash text not null unique,
      device_name text check (length(device_name) <= 100),
      platform text check (platform in ('ios','android','web')),
      push_token text,
      created_at timestamptz not null default now(),
      last_used_at timestamptz,
      expires_at timestamptz not null,
      revoked_at timestamptz,
      replaced_by uuid references sessions,
      revoked_reason text check (revoked_reason in
        ('logout','user_revoke','admin_reset','disabled','reuse_detected','expired','rotated')),
      device_trusted boolean not null default false
    )
    """,
    "create index on sessions (user_id) where revoked_at is null",
    "create index on sessions (family_id)",
    """
    create table auth_attempts (
      id bigserial primary key,
      at timestamptz not null default now(),
      username citext,
      ip inet,
      share_link_id uuid,
      kind text not null check (kind in
        ('login','activation','change_password','identity_check','share_pin',
         'share_lookup')),
      success boolean not null
    )
    """,
    "create index on auth_attempts (username, at desc)",
    "create index on auth_attempts (ip, at desc)",
    """
    create table patients (
      id uuid primary key default gen_random_uuid(),
      org_id uuid,
      full_name text not null check (length(full_name) between 1 and 200),
      relation text check (relation in ('self','child','parent','spouse','other')),
      archived_at timestamptz,
      birth_date date check (birth_date > date '1900-01-01'),
      sex sex not null default 'unknown',
      national_id_enc bytea,
      national_id_hmac text,
      created_by uuid references users,
      created_at timestamptz not null default now(),
      deleted_at timestamptz
    )
    """,
    """
    create table patient_access (
      patient_id uuid not null references patients on delete cascade,
      user_id uuid not null references users on delete cascade,
      level access_level not null,
      scopes text[] not null default '{results:read}',
      granted_by uuid references users,
      expires_at timestamptz,
      revoked_at timestamptz,
      primary key (patient_id, user_id)
    )
    """,
    "create index on patient_access (user_id) where revoked_at is null",
    """
    create table consents (
      id bigserial primary key,
      user_id uuid not null references users on delete cascade,
      patient_id uuid references patients on delete cascade,
      kind text not null check (kind in ('terms','privacy','sensitive_data','ai_processing',
                                         'cross_border','caregiver_sharing','research')),
      version text not null check (length(version) between 1 and 20),
      granted boolean not null,
      created_at timestamptz not null default now()
    )
    """,
    "create index on consents (user_id, kind, created_at desc)",
    """
    create table notifications (
      id bigserial primary key,
      user_id uuid not null references users on delete cascade,
      kind text not null check (kind in ('review_ready','critical_pending','share_invite',
                                         'admin_reset','reminder')),
      patient_id uuid references patients on delete cascade,
      entity_id text check (length(entity_id) <= 64),
      title_key text not null check (title_key ~ '^[a-z0-9_.]{1,80}$'),
      read_at timestamptz,
      sent_push_at timestamptz,
      created_at timestamptz not null default now()
    )
    """,
    "create index on notifications (user_id, created_at desc)",
    """
    create table audit_logs (
      id bigserial primary key,
      at timestamptz not null default now(),
      actor_id uuid,
      actor_role text,
      org_id uuid,
      action text not null check (action ~ '^[a-z0-9_.]{1,64}$'),
      target_user_id uuid,
      patient_id uuid,
      entity text check (entity ~ '^[a-z0-9_]{1,40}$'),
      entity_id text check (length(entity_id) <= 64),
      ip inet,
      user_agent text check (length(user_agent) <= 300),
      request_id text check (length(request_id) <= 64),
      diff jsonb
    )
    """,
    "create index on audit_logs (target_user_id, at desc)",
    "create index on audit_logs (patient_id, at desc)",
]

_FUNCTIONS = [
    # Not a definer: reads the caller's own transaction setting.
    """
    create function app_user_id() returns uuid language sql stable as
    $$ select nullif(current_setting('app.user_id', true), '')::uuid $$
    """,
    f"""
    create function is_owner(p uuid) returns boolean language sql stable {_DEFINER} as $$
      select exists (select 1 from public.patient_access a
        where a.patient_id = p and a.user_id = public.app_user_id() and a.level = 'owner'
          and a.revoked_at is null and (a.expires_at is null or a.expires_at > now()))
          and not exists (select 1 from public.patients x
                          where x.id = p and x.deleted_at is not null)
    $$
    """,
    f"""
    create function can_read_patient(p uuid) returns boolean language sql stable {_DEFINER} as $$
      select exists (select 1 from public.patient_access a
        where a.patient_id = p and a.user_id = public.app_user_id()
          and a.revoked_at is null and (a.expires_at is null or a.expires_at > now()))
          and not exists (select 1 from public.patients x
                          where x.id = p and x.deleted_at is not null)
    $$
    """,
    f"""
    create function can_write_patient(p uuid) returns boolean language sql stable {_DEFINER} as $$
      select exists (select 1 from public.patient_access a
        where a.patient_id = p and a.user_id = public.app_user_id()
          and a.level in ('owner','caregiver')
          and a.revoked_at is null and (a.expires_at is null or a.expires_at > now()))
          and not exists (select 1 from public.patients x
                          where x.id = p and x.deleted_at is not null)
    $$
    """,
    f"""
    create function is_minor_patient(p uuid) returns boolean language sql stable {_DEFINER} as $$
      -- Evaluated at check time: a child's profile stops being a minor's on the 18th birthday.
      select coalesce((select birth_date > current_date - interval '18 years'
                       from public.patients where id = p), false)
    $$
    """,
    # The caller becomes the owner of the new profile (the only way to insert a patient).
    f"""
    create function create_patient(p_full_name text, p_relation text, p_birth_date date,
                                   p_sex sex)
    returns uuid language plpgsql volatile {_DEFINER} as $$
    declare
      uid uuid := public.app_user_id();
      pid uuid;
    begin
      if uid is null then
        raise exception 'no user context' using errcode = '42501';
      end if;
      insert into public.patients (full_name, relation, birth_date, sex, created_by)
        values (p_full_name, p_relation, p_birth_date, p_sex, uid)
        returning id into pid;
      insert into public.patient_access (patient_id, user_id, level, scopes, granted_by)
        values (pid, uid, 'owner', '{{*}}', uid);
      return pid;
    end $$
    """,
    # Audit rows can only be written through these; the actor is never caller-supplied.
    rf"""
    create function audit_write(p_action text, p_entity text, p_entity_id text,
                                p_patient_id uuid, p_diff jsonb)
    returns void language plpgsql volatile {_DEFINER} as $$
    begin
      if public.app_user_id() is null
         or p_action !~ '^[a-z]+[.][a-z_]{{1,40}}$' or p_action like 'admin.%'
         or (p_patient_id is not null and not public.can_read_patient(p_patient_id)) then
        raise exception 'audit entry not allowed' using errcode = '42501';
      end if;
      insert into public.audit_logs (actor_id, actor_role, action, entity, entity_id,
                                     patient_id, diff)
      select u.id, u.role::text, p_action, p_entity, p_entity_id, p_patient_id, p_diff
      from public.users u where u.id = public.app_user_id();
    end $$
    """,
    f"""
    create function my_admin_actions()
    returns table (at timestamptz, action text, actor_role text)
    language sql stable {_DEFINER} as $$
      select l.at, l.action, l.actor_role from public.audit_logs l
      where l.target_user_id = public.app_user_id() and l.action like 'admin.%'
      order by l.at desc limit 200
    $$
    """,
    f"""
    create function notify(p_user_id uuid, p_kind text, p_patient_id uuid, p_entity_id text,
                           p_title_key text)
    returns void language plpgsql volatile {_DEFINER} as $$
    declare
      allowed boolean;
    begin
      allowed := case
        -- results: the caller writes for the patient, the recipient already has access
        when p_kind in ('review_ready', 'critical_pending') then
          p_patient_id is not null and public.can_write_patient(p_patient_id)
          and exists (select 1 from public.patient_access a
                      where a.patient_id = p_patient_id and a.user_id = p_user_id
                        and a.revoked_at is null
                        and (a.expires_at is null or a.expires_at > now()))
        -- invitations come only from the owner of the shared profile
        when p_kind = 'share_invite' then p_patient_id is not null and public.is_owner(p_patient_id)
        -- reminders only to oneself
        when p_kind = 'reminder' then p_user_id = public.app_user_id()
        else false  -- 'admin_reset' etc. are written by the admin service, never by users
      end;
      if not coalesce(allowed, false) then
        raise exception 'notification not allowed' using errcode = '42501';
      end if;
      insert into public.notifications (user_id, kind, patient_id, entity_id, title_key)
        values (p_user_id, p_kind, p_patient_id, p_entity_id, p_title_key);
    end $$
    """,
    # Users end their own sessions; a revoked session can never be revived.
    f"""
    create function revoke_my_session(p_session_id uuid, p_reason text) returns boolean
    language sql volatile {_DEFINER} as $$
      update public.sessions set revoked_at = now(), revoked_reason = p_reason
      where id = p_session_id and user_id = public.app_user_id() and revoked_at is null
        and p_reason in ('logout', 'user_revoke')
      returning true
    $$
    """,
    # Exact-match lookup for sharing by username: returns only the id of an active account.
    f"""
    create function lookup_user_for_share(p_username text) returns uuid
    language plpgsql volatile {_DEFINER} as $$
    declare
      me citext;
      found uuid;
    begin
      select username into me from public.users where id = public.app_user_id();
      if me is null then
        raise exception 'no user context' using errcode = '42501';
      end if;
      -- Not an account-existence oracle: at most 30 lookups per caller per hour.
      if (select count(*) from public.auth_attempts
          where kind = 'share_lookup' and username = me and at > now() - interval '1 hour') >= 30
      then
        raise exception 'too many lookups' using errcode = '54000';
      end if;
      select id into found from public.users
      where username = p_username::citext and account_status = 'active'
        and role in ('user','doctor') and deleted_at is null;
      insert into public.auth_attempts (kind, username, success)
        values ('share_lookup', me, found is not null);
      return found;
    end $$
    """,
    f"""
    create function is_shareable_user(p uuid) returns boolean language sql stable {_DEFINER} as $$
      select exists (select 1 from public.users where id = p and account_status = 'active'
                     and role in ('user','doctor') and deleted_at is null)
    $$
    """,
    # Minor status (proxy consent) derives from birth_date. A minor's birth date can only be
    # given when the profile is created; afterwards users may only fill an empty date with an
    # adult one, and never change a set date (corrections go through support). Otherwise an
    # adult's profile could be turned into a "child" to consent on their behalf.
    """
    create function patients_birth_date_once() returns trigger language plpgsql as $$
    begin
      if current_user = 'labtrack_app' and new.birth_date is distinct from old.birth_date
         and (old.birth_date is not null
              or new.birth_date is null
              or new.birth_date > current_date - interval '18 years') then
        raise exception 'birth date cannot be changed' using errcode = '42501';
      end if;
      return new;
    end $$
    """,
    """
    create trigger patients_birth_date_once before update on patients
      for each row execute function patients_birth_date_once()
    """,
    # L2: who granted access is recorded by the database, not by the caller.
    """
    create function patient_access_set_grantor() returns trigger language plpgsql as $$
    begin
      if current_user = 'labtrack_app' then
        new.granted_by := public.app_user_id();
      end if;
      return new;
    end $$
    """,
    """
    create trigger patient_access_grantor before insert or update on patient_access
      for each row execute function patient_access_set_grantor()
    """,
    # Audit rows are immutable.
    """
    create function audit_logs_immutable() returns trigger language plpgsql as $$
    begin
      raise exception 'audit_logs is append-only' using errcode = '42501';
    end $$
    """,
    """
    create trigger audit_logs_no_update_delete before update or delete on audit_logs
      for each row execute function audit_logs_immutable()
    """,
    """
    create trigger audit_logs_no_truncate before truncate on audit_logs
      for each statement execute function audit_logs_immutable()
    """,
]

_RLS_TABLES = [
    "users",
    "identity_checks",
    "activation_tokens",
    "sessions",
    "auth_attempts",
    "patients",
    "patient_access",
    "consents",
    "notifications",
    "audit_logs",
]

_POLICIES = [
    # --- users: a user sees and edits only their own row (and only harmless columns) ---
    "create policy users_app_select on users for select to labtrack_app using (id = app_user_id())",
    """create policy users_app_update on users for update to labtrack_app
       using (id = app_user_id()) with check (id = app_user_id())""",
    """create policy users_admin_select on users for select to labtrack_admin using (true)""",
    # --- sessions ---
    """create policy sessions_app_select on sessions for select to labtrack_app
       using (user_id = app_user_id())""",
    """create policy sessions_admin_select on sessions for select to labtrack_admin
       using (true)""",
    # --- admin-only account tables ---
    """create policy identity_checks_admin_select on identity_checks for select
       to labtrack_admin using (true)""",
    """create policy activation_tokens_admin_select on activation_tokens for select
       to labtrack_admin using (true)""",
    """create policy auth_attempts_admin on auth_attempts for select to labtrack_admin
       using (true)""",
    """create policy auth_attempts_maint on auth_attempts for all to labtrack_maint
       using (true) with check (true)""",
    # --- patients: insert only via create_patient(); owner edits; readers read ---
    """create policy patients_select on patients for select to labtrack_app
       using (can_read_patient(id))""",
    """create policy patients_update on patients for update to labtrack_app
       using (is_owner(id)) with check (is_owner(id))""",
    "create policy patients_delete on patients for delete to labtrack_app using (is_owner(id))",
    # --- patient_access: only the owner grants; nobody grants to themselves; no new owners ---
    """create policy access_select on patient_access for select to labtrack_app
       using (user_id = app_user_id() or is_owner(patient_id))""",
    """create policy access_insert on patient_access for insert to labtrack_app
       with check (is_owner(patient_id) and user_id <> app_user_id() and level <> 'owner'
                   and is_shareable_user(user_id))""",
    """create policy access_update on patient_access for update to labtrack_app
       using (is_owner(patient_id) and user_id <> app_user_id())
       with check (is_owner(patient_id) and user_id <> app_user_id() and level <> 'owner'
                   and is_shareable_user(user_id))""",
    """create policy access_delete on patient_access for delete to labtrack_app
       using (is_owner(patient_id) and user_id <> app_user_id())""",
    # --- consents: append-only; profile consents only by the owner of a minor's profile ---
    """create policy consents_select on consents for select to labtrack_app
       using (user_id = app_user_id())""",
    """create policy consents_insert on consents for insert to labtrack_app
       with check (user_id = app_user_id() and
                   (patient_id is null
                    or (is_owner(patient_id) and is_minor_patient(patient_id))))""",
    # --- notifications: read and mark read; created only via notify() ---
    """create policy notifications_select on notifications for select to labtrack_app
       using (user_id = app_user_id())""",
    """create policy notifications_update on notifications for update to labtrack_app
       using (user_id = app_user_id()) with check (user_id = app_user_id())""",
]

_GRANTS = [
    # labtrack_app: harmless columns only (no password_hash, totp_secret_enc,
    # contact_phone_*, identity_check_hash, created_by)
    """grant select (id, username, display_name, locale, role, account_status,
                     emergency_card_unlocked, password_changed_at, created_at)
       on users to labtrack_app""",
    "grant update (display_name, locale, emergency_card_unlocked) on users to labtrack_app",
    """grant select (id, user_id, family_id, device_name, platform, created_at, last_used_at,
                     expires_at, revoked_at, revoked_reason, device_trusted)
       on sessions to labtrack_app""",
    "grant select, delete on patients to labtrack_app",
    """grant update (full_name, relation, birth_date, sex, archived_at, deleted_at,
                     national_id_enc, national_id_hmac) on patients to labtrack_app""",
    "grant select, insert, update, delete on patient_access to labtrack_app",
    """grant select, insert (user_id, patient_id, kind, version, granted)
       on consents to labtrack_app""",
    "grant usage on sequence consents_id_seq to labtrack_app",
    "grant select on notifications to labtrack_app",
    "grant update (read_at) on notifications to labtrack_app",
    # labtrack_admin: read-only on account tables; every change goes through the admin_*
    # functions in 0004 (actor = app.user_id, rules enforced in SQL). Never patient tables.
    """grant select (id, username, display_name, locale, role, account_status, token_version,
                     contact_phone_last4, created_by, password_changed_at, created_at,
                     deleted_at)
       on users to labtrack_admin""",
    """grant select (id, user_id, purpose, channel, issued_by, identity_check_id, expires_at,
                     used_at, revoked_at, created_at)
       on activation_tokens to labtrack_admin""",
    "grant select on identity_checks to labtrack_admin",
    "grant select (id, user_id, revoked_at, revoked_reason) on sessions to labtrack_admin",
    "grant select on auth_attempts to labtrack_admin",
    # labtrack_maint: retention only
    "grant select, delete on auth_attempts to labtrack_maint",
    # functions
    "grant execute on function app_user_id() to labtrack_app, labtrack_admin, labtrack_maint",
    """grant execute on function is_owner(uuid), can_read_patient(uuid), can_write_patient(uuid),
       is_minor_patient(uuid), is_shareable_user(uuid), create_patient(text, text, date, sex),
       audit_write(text, text, text, uuid, jsonb), my_admin_actions(),
       notify(uuid, text, uuid, text, text), lookup_user_for_share(text),
       revoke_my_session(uuid, text)
       to labtrack_app""",
]


def upgrade() -> None:
    for sql in _TYPES + _TABLES + _FUNCTIONS:
        op.execute(sql)
    for table in _RLS_TABLES:
        op.execute(f"alter table {table} enable row level security")
        op.execute(f"alter table {table} force row level security")
        # FORCE applies to the owner too; security definer functions run as the owner.
        op.execute(
            f"create policy {table}_owner on {table} for all to labtrack_owner "
            "using (true) with check (true)"
        )
    op.execute("revoke execute on all functions in schema public from public")
    for sql in _POLICIES + _GRANTS:
        op.execute(sql)
    op.execute("revoke truncate on all tables in schema public from public")


def downgrade() -> None:
    # Tables first: dropping them removes the policies that reference the helper functions.
    for table in reversed(_RLS_TABLES):
        op.execute(f"drop table if exists {table} cascade")
    for fn in (
        "revoke_my_session(uuid, text)",
        "patient_access_set_grantor()",
        "is_shareable_user(uuid)",
        "lookup_user_for_share(text)",
        "notify(uuid, text, uuid, text, text)",
        "my_admin_actions()",
        "audit_write(text, text, text, uuid, jsonb)",
        "create_patient(text, text, date, sex)",
        "is_minor_patient(uuid)",
        "patients_birth_date_once()",
        "can_write_patient(uuid)",
        "can_read_patient(uuid)",
        "is_owner(uuid)",
        "audit_logs_immutable()",
        "app_user_id()",
    ):
        op.execute(f"drop function if exists {fn}")
    for t in ("user_role", "sex", "access_level"):
        op.execute(f"drop type if exists {t}")
