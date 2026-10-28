"""Account deletion and per-user keys (docs/04 §1 "Хэрэглэгчийн тохиргоо", §6.9; Phase 1.8).

- request_account_deletion(): the user (password re-checked by the API) marks the account
  deleted; every session and token ends at once and nobody can sign in. The data stays 30
  days (accidental or coerced requests can be undone), then maint_purge_deleted_users() erases
  it: the profiles the user owns with all their health data, the account and its key.
- admin_cancel_deletion(): within the 30 days a super admin may restore the account, but only
  as `locked` + reset_required - the person is identified and sets a new password through the
  normal reset path, so a cancellation never hands an account to whoever asked for it.
- user_keys: one key per user wraps the data keys of that user's encrypted fields. Erasing it
  makes every copy of those fields unreadable (crypto-shredding). In dev/test the key rows live
  in this database, so they are in its backups too; production keeps them in OpenBao (named
  keys, destroyed on purge), which is what makes backups unreadable.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-29
"""

from collections.abc import Sequence

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
    begin
      perform public.admin_actor(array['super_admin','support']::public.user_role[]);
      return (select wrapped_key from public.user_keys where user_id = p_user_id);
    end $$
    """,
    f"""
    create function user_key_put(p_user_id uuid, p_wrapped bytea) returns bytea
    language plpgsql volatile {_DEFINER} as $$
    begin
      perform public.admin_actor(array['super_admin']::public.user_role[]);
      if exists (select 1 from public.users where id = p_user_id
                 and role not in ('user','doctor')) then
        raise exception 'target not allowed' using errcode = '42501';
      end if;
      insert into public.user_keys (user_id, wrapped_key) values (p_user_id, p_wrapped)
        on conflict (user_id) do nothing;
      return (select wrapped_key from public.user_keys where user_id = p_user_id);
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
    create function admin_cancel_deletion(p_user_id uuid) returns void
    language plpgsql volatile {_DEFINER} as $$
    declare
      actor uuid := public.admin_actor(array['super_admin']::public.user_role[]);
    begin
      update public.users
        set deleted_at = null, account_status = 'locked', reset_required = true
        where id = p_user_id and role in ('user','doctor') and deleted_at is not null
          and deleted_at > now() - interval '30 days';
      if not found then
        raise exception 'no pending deletion' using errcode = '42501';
      end if;
      perform public.admin_audit(actor, 'admin.deletion_cancel', p_user_id, null);
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
        -- the profiles this user owns, with everything recorded on them (cascades)
        delete from public.patients p
          where exists (select 1 from public.patient_access a
                        where a.patient_id = p.id and a.user_id = uid and a.level = 'owner');
        update public.patients set created_by = null where created_by = uid;
        update public.patient_access set granted_by = null where granted_by = uid;
        delete from public.user_keys where user_id = uid;
        -- sessions, tokens, consents, notifications, access, devices cascade with the row
        delete from public.users where id = uid;
        insert into public.audit_logs (actor_role, action, target_user_id, entity, entity_id)
          values ('maint', 'account.purged', uid, 'user', uid::text);
        return next uid;
      end loop;
    end $$
    """,
    "revoke execute on all functions in schema public from public",
    """grant execute on function user_key_get(uuid), user_key_put(uuid, bytea),
       admin_cancel_deletion(uuid) to labtrack_admin""",
    "grant execute on function request_account_deletion() to labtrack_app",
    "grant execute on function maint_purge_deleted_users(int) to labtrack_maint",
]


def upgrade() -> None:
    for sql in _UP:
        op.execute(sql)


def downgrade() -> None:
    for fn in (
        "maint_purge_deleted_users(int)",
        "admin_cancel_deletion(uuid)",
        "request_account_deletion()",
        "user_key_put(uuid, bytea)",
        "user_key_get(uuid)",
    ):
        op.execute(f"drop function if exists {fn}")
    op.execute("drop index if exists users_deleted_at_idx")
    op.execute("drop table if exists user_keys")
