"""Authentication functions for the API (role labtrack_app, no user context yet).

docs/04 §1, §6. Password verification (argon2id) and the lockout policy live in Python
(labtrack.core.security); the database stores state and enforces what it can on its own:
- refresh tokens are stored as sha256 only; rotation is atomic (row lock) with a 20 s grace
  window for concurrent refreshes, and reuse of an old token revokes the whole family;
- a session is valid only while not revoked/expired, the account is active and the access
  token's token_version matches (so disable/reset take effect immediately);
- trusted devices (OWASP device cookie) are stored as hashes, expire after 180 days of
  disuse and are forgotten on reset, disable and password change (sign out others);
- success is never recorded from outside: the API can only record failures, and a success
  row is written by session_create / auth_change_password themselves (so an injected call cannot
  reset another account's lockout counters by "recording" a success);
- a login lives at most 180 days regardless of rotation.

Trust boundary: the API is the authentication authority - session_create can only be reached
after the API has verified a password. These functions narrow what an injected statement could
do (no direct table access, no hash reads beyond one username) but do not replace safe SQL.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-28
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEFINER = "security definer set search_path = pg_catalog, public, pg_temp"

_UP = [
    """
    create table trusted_devices (
      user_id uuid not null references users on delete cascade,
      device_hash text not null check (device_hash ~ '^[0-9a-f]{64}$'),
      created_at timestamptz not null default now(),
      last_seen_at timestamptz not null default now(),
      primary key (user_id, device_hash)
    )
    """,
    "alter table trusted_devices enable row level security",
    "alter table trusted_devices force row level security",
    """create policy trusted_devices_owner on trusted_devices for all to labtrack_owner
       using (true) with check (true)""",
    # Lockout keys: untrusted devices by (username, IP), trusted devices by (username, device),
    # so a neighbour behind the same CGNAT address cannot lock the owner's phone.
    "alter table auth_attempts add column device_trusted boolean not null default false",
    "alter table auth_attempts add column device_hash text",
    # A rotated token may be used once more within the grace window (concurrent refresh), and
    # only while nothing has happened to the account since it was issued.
    "alter table sessions add column grace_used boolean not null default false",
    "alter table sessions add column issued_token_version int not null default 0",
    # Absolute lifetime: rotation never extends a login beyond 180 days (ASVS 3.3).
    "alter table sessions add column family_expires_at timestamptz",
    # --- login -------------------------------------------------------------------------------
    f"""
    create function auth_login_lookup(p_username text)
    returns table (user_id uuid, password_hash text, account_status text, token_version int,
                   role user_role)
    language sql stable {_DEFINER} as $$
      select id, password_hash, account_status, token_version, role from public.users
      where username = p_username::citext and deleted_at is null
    $$
    """,
    f"""
    create function auth_record_failure(p_kind text, p_username text, p_ip inet,
                                        p_device_hash text, p_device_trusted boolean)
    returns void language sql volatile {_DEFINER} as $$
      insert into public.auth_attempts (kind, username, ip, device_hash, device_trusted, success)
      values (p_kind, p_username, p_ip, p_device_hash, p_device_trusted, false)
    $$
    """,
    # Failure counts since the last success, for the Python lockout policy (core/security).
    f"""
    create function auth_failure_counts(p_kind text, p_username text, p_ip inet,
                                        p_device_hash text, p_window interval)
    returns table (by_username_ip int, by_username_device int, by_username_untrusted int,
                   last_failure timestamptz)
    language sql stable {_DEFINER} as $$
      with recent as (
        select * from public.auth_attempts
        where kind = p_kind and username = p_username::citext and at > now() - p_window
          and at > coalesce((select max(at) from public.auth_attempts
                             where kind = p_kind and username = p_username::citext
                               and success), '-infinity')
      )
      select
        (count(*) filter (where not success and not device_trusted and ip = p_ip))::int,
        (count(*) filter (where not success and device_trusted
                          and device_hash = p_device_hash))::int,
        (count(*) filter (where not success and not device_trusted))::int,
        max(at) filter (where not success)
      from recent
    $$
    """,
    f"""
    create function device_is_trusted(p_username text, p_device_hash text) returns boolean
    language sql stable {_DEFINER} as $$
      select exists (select 1 from public.trusted_devices d join public.users u on u.id = d.user_id
                     where u.username = p_username::citext and d.device_hash = p_device_hash
                       and d.last_seen_at > now() - interval '180 days')
    $$
    """,
    # Usernames for the password policy during activation (only for a live token).
    f"""
    create function activation_token_user(p_token_hash text)
    returns table (username text, display_name text)
    language sql stable {_DEFINER} as $$
      select u.username::text, u.display_name from public.activation_tokens t
      join public.users u on u.id = t.user_id
      where t.token_hash = p_token_hash and t.used_at is null and t.revoked_at is null
        and t.expires_at > now()
    $$
    """,
    # --- sessions ----------------------------------------------------------------------------
    f"""
    create function session_create(p_user_id uuid, p_token_hash text, p_device_name text,
                                   p_platform text, p_device_hash text,
                                   p_device_was_trusted boolean, p_ip inet, p_ttl interval)
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
      if u.account_status is distinct from 'active' or u.deleted_at is not null then
        raise exception 'account not active' using errcode = '28000';
      end if;
      -- The API calls this only after verifying the password (argon2 runs in Python, so the
      -- database cannot check it itself - see the module docstring). The success that resets
      -- the lockout counters is recorded here, never by a separately callable function.
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
    # status: ok | invalid | expired | revoked:<reason> | reuse | inactive
    f"""
    create function session_rotate(p_old_hash text, p_new_hash text, p_ttl interval)
    returns table (status text, session_id uuid, user_id uuid, token_version int,
                   role user_role)
    language plpgsql volatile {_DEFINER} as $$
    declare
      s public.sessions%rowtype;
      u public.users%rowtype;
      new_id uuid;
    begin
      if p_new_hash !~ '^[0-9a-f]{{64}}$' or p_ttl > interval '90 days' then
        raise exception 'invalid session parameters' using errcode = '22023';
      end if;
      select * into s from public.sessions where token_hash = p_old_hash for update;
      if not found then
        return query select 'invalid', null::uuid, null::uuid, null::int, null::public.user_role;
        return;
      end if;
      select * into u from public.users where id = s.user_id;
      if s.revoked_at is not null then
        if s.revoked_reason = 'rotated' and s.revoked_at > now() - interval '20 seconds'
           and not s.grace_used
           and s.issued_token_version = u.token_version
           and exists (select 1 from public.sessions r
                       where r.id = s.replaced_by and r.revoked_at is null)
           and not exists (select 1 from public.sessions f
                           where f.family_id = s.family_id
                             and f.revoked_reason not in ('rotated')) then
          -- A concurrent refresh of the same token: one sibling, only while the session it
          -- was rotated into is alive and nothing (logout, reset, password change, reuse)
          -- has happened to the family or the account since.
          update public.sessions set grace_used = true where id = s.id;
        elsif s.revoked_reason = 'rotated' then
          -- an old token came back: assume theft, end the whole family
          update public.sessions set revoked_at = now(), revoked_reason = 'reuse_detected'
            where family_id = s.family_id and revoked_at is null;
          return query select 'reuse', s.id, s.user_id, u.token_version, u.role;
          return;
        else
          return query select 'revoked:' || s.revoked_reason, s.id, s.user_id, u.token_version,
                              u.role;
          return;
        end if;
      elsif s.expires_at <= now() or s.family_expires_at <= now() then
        update public.sessions set revoked_at = now(), revoked_reason = 'expired'
          where family_id = s.family_id and revoked_at is null;
        return query select 'expired', s.id, s.user_id, u.token_version, u.role;
        return;
      end if;
      if u.account_status <> 'active' or u.deleted_at is not null then
        return query select 'inactive', s.id, s.user_id, u.token_version, u.role;
        return;
      end if;
      insert into public.sessions (user_id, family_id, token_hash, device_name, platform,
                                   push_token, expires_at, device_trusted, last_used_at,
                                   issued_token_version, family_expires_at)
        values (s.user_id, s.family_id, p_new_hash, s.device_name, s.platform, s.push_token,
                least(now() + p_ttl, s.family_expires_at), s.device_trusted, now(),
                u.token_version, s.family_expires_at)
        returning id into new_id;
      if s.revoked_at is null then
        update public.sessions set revoked_at = now(), revoked_reason = 'rotated',
               replaced_by = new_id where id = s.id;
      end if;
      return query select 'ok', new_id, s.user_id, u.token_version, u.role;
    end $$
    """,
    # Per request: is this access token still backed by a live session?
    f"""
    create function session_check(p_session_id uuid, p_user_id uuid, p_token_version int)
    returns boolean language sql stable {_DEFINER} as $$
      select exists (
        select 1 from public.sessions s join public.users u on u.id = s.user_id
        where s.id = p_session_id and s.user_id = p_user_id and s.revoked_at is null
          and s.expires_at > now() and u.account_status = 'active' and u.deleted_at is null
          and u.token_version = p_token_version)
    $$
    """,
    # Logout ends the device's whole family (including any grace sibling).
    f"""
    create function session_revoke_by_token(p_token_hash text) returns void
    language sql volatile {_DEFINER} as $$
      update public.sessions set revoked_at = now(), revoked_reason = 'logout'
      where revoked_at is null
        and family_id = (select family_id from public.sessions where token_hash = p_token_hash)
    $$
    """,
    # Account-wide revocation (admin reset/disable, from 0004) now also forgets trusted devices.
    f"""
    create or replace function revoke_user_sessions(p_user_id uuid, p_reason text) returns void
    language sql volatile {_DEFINER} as $$
      update public.sessions set revoked_at = now(), revoked_reason = p_reason
      where user_id = p_user_id and revoked_at is null;
      update public.users set token_version = token_version + 1 where id = p_user_id;
      delete from public.trusted_devices where user_id = p_user_id;
    $$
    """,
    # --- password change (user context required) --------------------------------------------
    f"""
    create function auth_own_password_hash() returns text
    language sql stable {_DEFINER} as $$
      select password_hash from public.users where id = public.app_user_id()
    $$
    """,
    f"""
    create function auth_change_password(p_new_hash text, p_keep_session uuid,
                                         p_revoke_others boolean) returns void
    language plpgsql volatile {_DEFINER} as $$
    declare
      uid uuid := public.app_user_id();
    begin
      if uid is null or p_new_hash !~ '^[$]argon2id[$]' then
        raise exception 'password change not allowed' using errcode = '42501';
      end if;
      update public.users set password_hash = p_new_hash, password_changed_at = now(),
             token_version = token_version + 1
        where id = uid and account_status = 'active';
      if not found then
        raise exception 'password change not allowed' using errcode = '42501';
      end if;
      if p_revoke_others then
        update public.sessions set revoked_at = now(), revoked_reason = 'user_revoke'
          where user_id = uid and revoked_at is null and id is distinct from p_keep_session;
        delete from public.trusted_devices where user_id = uid;
      end if;
      -- The kept session continues under the new token_version (no grace for older tokens).
      update public.sessions set issued_token_version = (select token_version from public.users
                                                         where id = uid)
        where id = p_keep_session and user_id = uid;
      insert into public.auth_attempts (kind, username, success)
        select 'change_password', username, true from public.users where id = uid;
      insert into public.audit_logs (actor_id, actor_role, action, target_user_id)
        select uid, role::text, 'account.password_change', uid from public.users where id = uid;
    end $$
    """,
    "revoke execute on all functions in schema public from public",
    """grant execute on function
       auth_login_lookup(text),
       auth_record_failure(text, text, inet, text, boolean),
       auth_failure_counts(text, text, inet, text, interval),
       device_is_trusted(text, text),
       activation_token_user(text),
       session_create(uuid, text, text, text, text, boolean, inet, interval),
       session_rotate(text, text, interval),
       session_check(uuid, uuid, int),
       session_revoke_by_token(text),
       auth_own_password_hash(),
       auth_change_password(text, uuid, boolean)
       to labtrack_app""",
]


def upgrade() -> None:
    for sql in _UP:
        op.execute(sql)


def downgrade() -> None:
    for fn in (
        "auth_change_password(text, uuid, boolean)",
        "auth_own_password_hash()",
        "session_revoke_by_token(text)",
        "session_check(uuid, uuid, int)",
        "session_rotate(text, text, interval)",
        "session_create(uuid, text, text, text, text, boolean, inet, interval)",
        "activation_token_user(text)",
        "device_is_trusted(text, text)",
        "auth_failure_counts(text, text, inet, text, interval)",
        "auth_record_failure(text, text, inet, text, boolean)",
        "auth_login_lookup(text)",
    ):
        op.execute(f"drop function if exists {fn}")
    # restore 0004's revoke_user_sessions (without trusted devices)
    op.execute(
        f"""
        create or replace function revoke_user_sessions(p_user_id uuid, p_reason text)
        returns void language sql volatile {_DEFINER} as $$
          update public.sessions set revoked_at = now(), revoked_reason = p_reason
          where user_id = p_user_id and revoked_at is null;
          update public.users set token_version = token_version + 1 where id = p_user_id;
        $$
        """
    )
    op.execute("revoke execute on function revoke_user_sessions(uuid, text) from public")
    for col in ("family_expires_at", "issued_token_version", "grace_used"):
        op.execute(f"alter table sessions drop column if exists {col}")
    for col in ("device_hash", "device_trusted"):
        op.execute(f"alter table auth_attempts drop column if exists {col}")
    op.execute("drop table if exists trusted_devices")
