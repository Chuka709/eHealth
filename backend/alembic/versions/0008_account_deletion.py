"""Account deletion and per-user keys (docs/04 §1 "Хэрэглэгчийн тохиргоо", §6.9; Phase 1.8).

- request_account_deletion(): the user (password re-checked by the API) marks the account
  deleted; every session and token ends at once and nobody can sign in. The data stays 30
  days (accidental or coerced requests can be undone), then maint_purge_deleted_users() erases
  it: the profiles the user owns with all their health data, the account and its key.
- admin_cancel_deletion(): within the 30 days a super admin may restore the account, but only
  as `locked` + reset_required - the person is identified and sets a new password through the
  normal reset path, so a cancellation never hands an account to whoever asked for it.
- While a deletion is pending, nobody else (caregivers, doctors) reads or writes the profiles
  the user owns.
- user_keys: one key per user wraps the data keys of that user's encrypted fields. Erasing it
  makes every copy of those fields unreadable (crypto-shredding). In dev/test the key rows live
  in this database, so they are in its backups too; production keeps them in OpenBao (named
  keys, destroyed on purge), which is what makes backups unreadable.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-29
"""

import importlib.util
import os
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEFINER = "security definer set search_path = pg_catalog, public, pg_temp"

_UP = [
    # No FK to users: a key is created before the account row (the phone is encrypted for the
    # admin_create_user call) in the same transaction, and the purge deletes it explicitly.
    """
    create table user_keys (
      user_id uuid primary key,
      wrapped_key bytea not null,
      created_at timestamptz not null default now()
    )
    """,
    "alter table user_keys enable row level security",
    "alter table user_keys force row level security",
    """create policy user_keys_owner on user_keys for all to labtrack_owner
       using (true) with check (true)""",
    "create index on users (deleted_at) where deleted_at is not null",
    # --- per-user keys (admin API: phone numbers) -------------------------------------------
    f"""
    create function user_key_get(p_user_id uuid) returns bytea
    language plpgsql stable {_DEFINER} as $$
    declare
      actor uuid := public.admin_actor(array['super_admin','support']::public.user_role[]);
    begin
      perform public.admin_target(p_user_id);
      -- Only for a value this admin was just given in this transaction (audited, rationed):
      -- admin_reveal_phone / admin_sms_target write their audit row at now() = tx start.
      if not exists (select 1 from public.audit_logs l
                     where l.actor_id = actor and l.target_user_id = p_user_id
                       and l.action in ('admin.phone_reveal','admin.sms_target')
                       and l.at = now()) then
        raise exception 'admin not allowed' using errcode = '42501';
      end if;
      return (select wrapped_key from public.user_keys where user_id = p_user_id);
    end $$
    """,
    f"""
    create function user_key_put(p_user_id uuid, p_wrapped bytea) returns bytea
    language plpgsql volatile {_DEFINER} as $$
    begin
      perform public.admin_actor(array['super_admin']::public.user_role[]);
      -- Only for an account being created in this transaction: never a getter for existing
      -- keys, never a key for an existing (or purged) account.
      if exists (select 1 from public.users where id = p_user_id)
         or exists (select 1 from public.user_keys where user_id = p_user_id)
         or exists (select 1 from public.audit_logs where target_user_id = p_user_id
                    and action = 'account.purged') then
        raise exception 'target not allowed' using errcode = '42501';
      end if;
      insert into public.user_keys (user_id, wrapped_key) values (p_user_id, p_wrapped);
      return p_wrapped;
    end $$
    """,
    # --- deletion ---------------------------------------------------------------------------
    f"""
    create function request_account_deletion() returns timestamptz
    language plpgsql volatile {_DEFINER} as $$
    declare
      uid uuid := public.app_user_id();
    begin
      update public.users set deleted_at = now()
        where id = uid and deleted_at is null and role in ('user','doctor')
          and account_status = 'active';
      if not found then
        raise exception 'deletion not allowed' using errcode = '42501';
      end if;
      perform public.revoke_user_sessions(uid, 'disabled');
      update public.activation_tokens set revoked_at = now()
        where user_id = uid and used_at is null and revoked_at is null;
      insert into public.audit_logs (actor_id, actor_role, action, target_user_id, entity,
                                     entity_id)
        select uid, role::text, 'account.deletion_requested', uid, 'user', uid::text
        from public.users where id = uid;
      return now() + interval '30 days';
    end $$
    """,
    f"""
    create function admin_cancel_deletion(p_user_id uuid, p_reason text) returns void
    language plpgsql volatile {_DEFINER} as $$
    declare
      actor uuid := public.admin_actor(array['super_admin']::public.user_role[]);
    begin
      if p_reason is null or p_reason not in ('user_request','suspected_compromise','other') then
        raise exception 'reason required' using errcode = '22023';
      end if;
      update public.users
        set deleted_at = null, account_status = 'locked', reset_required = true
        where id = p_user_id and role in ('user','doctor') and deleted_at is not null
          and deleted_at > now() - interval '30 days';
      if not found then
        raise exception 'no pending deletion' using errcode = '42501';
      end if;
      perform public.admin_audit(actor, 'admin.deletion_cancel', p_user_id,
                                 jsonb_build_object('reason', p_reason));
    end $$
    """,
    # Run daily by the maintenance worker (labtrack_maint). Returns the purged ids so the
    # caller can destroy keys held outside the database (OpenBao in production).
    f"""
    create function maint_purge_deleted_users(p_limit int) returns setof uuid
    language plpgsql volatile {_DEFINER} as $$
    declare
      uid uuid;
    begin
      for uid in
        select id from public.users
        where deleted_at is not null and deleted_at <= now() - interval '30 days'
          and role in ('user','doctor')
        order by deleted_at limit least(greatest(p_limit, 1), 500)
        for update skip locked
      loop
        begin  -- a subtransaction per account: one failure is reported, the rest go on
        -- the profiles this user owns, with everything recorded on them (cascades)
        delete from public.patients p
          where exists (select 1 from public.patient_access a
                        where a.patient_id = p.id and a.user_id = uid and a.level = 'owner');
        update public.patients set created_by = null where created_by = uid;
        update public.patient_access set granted_by = null where granted_by = uid;
        delete from public.user_keys where user_id = uid;
        -- a freed username must not inherit this account's failed-login history
        delete from public.auth_attempts
          where username = (select username from public.users where id = uid);
        -- sessions, tokens, consents, notifications, access, devices cascade with the row
        delete from public.users where id = uid;
        insert into public.audit_logs (actor_role, action, target_user_id, entity, entity_id)
          values ('maint', 'account.purged', uid, 'user', uid::text);
        return next uid;
        exception when others then
          insert into public.audit_logs (actor_role, action, target_user_id, entity, entity_id)
            values ('maint', 'security.purge_failed', uid, 'user', uid::text);
        end;
      end loop;
    end $$
    """,
    "revoke execute on all functions in schema public from public",
    """grant execute on function user_key_get(uuid), user_key_put(uuid, bytea),
       admin_cancel_deletion(uuid, text) to labtrack_admin""",
    "grant execute on function request_account_deletion() to labtrack_app",
    "grant execute on function maint_purge_deleted_users(int) to labtrack_maint",
]


_OWNER_NOT_LEAVING = """
          and not exists (select 1 from public.patient_access o
                          join public.users u on u.id = o.user_id
                          where o.patient_id = p and o.level = 'owner'
                            and u.deleted_at is not null)
    $$"""
_CONSUME_WHERE = (
    "where id = tok.user_id and account_status in ('pending_activation','active','locked');"
)


def _revision(filename: str) -> ModuleType:
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _access_functions(*, pending_deletion_blocks: bool) -> list[str]:
    """can_read_patient / can_write_patient from 0002, optionally refusing access to the
    profiles of an owner whose deletion is pending."""
    statements: list[str] = _revision("0002_auth_and_profiles.py")._FUNCTIONS
    out = []
    for name in ("can_read_patient", "can_write_patient"):
        (sql,) = [x for x in statements if f"create function {name}(" in x]
        sql = sql.replace("create function", "create or replace function", 1)
        if pending_deletion_blocks:
            if sql.rstrip().count("$$") != 2:  # noqa: PLR2004
                raise RuntimeError("0002 definition changed")
            sql = sql.rstrip()[: sql.rstrip().rfind("$$")].rstrip() + _OWNER_NOT_LEAVING
        out.append(sql)
    return out


def _activation_consume(*, refuse_deleted: bool) -> str:
    m7 = _revision("0007_me.py")
    sql: str = m7._patched(m7._from_0006("activation_consume"), [(m7._CONSUME, m7._CONSUME_NEW)])
    if refuse_deleted:
        if sql.count(_CONSUME_WHERE) != 1:
            raise RuntimeError("0007 activation_consume changed")
        sql = sql.replace(_CONSUME_WHERE, _CONSUME_WHERE[:-1] + " and deleted_at is null;")
    return sql


def upgrade() -> None:
    grants = _UP.index("revoke execute on all functions in schema public from public")
    extra = [
        *_access_functions(pending_deletion_blocks=True),
        _activation_consume(refuse_deleted=True),
    ]
    for sql in _UP[:grants] + extra + _UP[grants:]:
        op.execute(sql)


def downgrade() -> None:
    # Values sealed under user keys would become unreadable: outside dev/test, refuse rather
    # than lose them (dev/test data is disposable; the test run migrates up, down and up).
    if os.environ.get("ENVIRONMENT") not in {"dev", "test"}:
        op.execute(
            """do $$ begin
                 if exists (select 1 from user_keys) then
                   raise exception 'user_keys is not empty: re-seal under the KEK first';
                 end if;
               end $$"""
        )
    for sql in [
        *_access_functions(pending_deletion_blocks=False),
        _activation_consume(refuse_deleted=False),
    ]:
        op.execute(sql)
    for fn in (
        "maint_purge_deleted_users(int)",
        "admin_cancel_deletion(uuid, text)",
        "request_account_deletion()",
        "user_key_put(uuid, bytea)",
        "user_key_get(uuid)",
    ):
        op.execute(f"drop function if exists {fn}")
    op.execute("drop index if exists users_deleted_at_idx")
    op.execute("drop table if exists user_keys")
