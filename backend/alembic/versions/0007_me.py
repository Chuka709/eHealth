"""The user's side of account administration (docs/04 §1 step 5c, Phase 1.7).

- report_unwanted_admin_action(): the "Би хүсээгүй" button. A user who sees an admin action
  they did not ask for (within 30 days of it) locks their own account: every session and live
  token ends, and a security event reaches the admins.
- A lock for suspected compromise (an admin's lock/disable with that reason, or the user's
  own report) sets users.reset_required. While it is set no status change makes the account
  active again, from any state: someone else may know the password. Only setting a new
  password with a reset token (activation_consume) clears it.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-29
"""

import importlib.util
from collections.abc import Sequence
from pathlib import Path

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEFINER = "security definer set search_path = pg_catalog, public, pg_temp"

_REPORT = f"""
    create function report_unwanted_admin_action() returns void
    language plpgsql volatile {_DEFINER} as $$
    declare
      uid uuid := public.app_user_id();
    begin
      if uid is null or not exists (
           select 1 from public.audit_logs
           where target_user_id = uid and action like 'admin.%'
             and at > now() - interval '30 days') then
        raise exception 'no recent admin action' using errcode = '42501';
      end if;
      update public.users set account_status = 'locked', reset_required = true
        where id = uid and account_status = 'active' and role in ('user','doctor')
          and deleted_at is null;
      if not found then
        raise exception 'account not active' using errcode = '42501';
      end if;
      perform public.revoke_user_sessions(uid, 'disabled');
      update public.activation_tokens set revoked_at = now()
        where user_id = uid and used_at is null and revoked_at is null;
      insert into public.audit_logs (actor_id, actor_role, action, target_user_id, entity,
                                     entity_id)
        select uid, role::text, 'security.user_report', uid, 'user', uid::text
        from public.users where id = uid;
    end $$
    """

_SUPPORT_CHECK_OLD = """\
        -- A lock for suspected compromise is lifted by a super admin, not support.
        if exists (select 1 from public.users where id = actor and role = 'support')
           and (select l.diff ->> 'reason' from public.audit_logs l
                where l.action = 'admin.status_locked' and l.target_user_id = p_user_id
                order by l.at desc limit 1) = 'suspected_compromise' then
          raise exception 'admin not allowed' using errcode = '42501';
        end if;"""
_STATUS_READ = """\
      select account_status into current_status from public.users where id = p_user_id;"""
_STATUS_READ_NEW = """\
      select account_status into current_status from public.users where id = p_user_id;
      -- Suspected compromise: never active again by a status change, from any state.
      if p_status = 'active' and (select reset_required from public.users where id = p_user_id)
      then
        raise exception 'password reset required' using errcode = '42501';
      end if;"""
_STATUS_WRITE = """\
      update public.users set account_status = p_status where id = p_user_id;"""
_STATUS_WRITE_NEW = """\
      update public.users set account_status = p_status,
             reset_required = reset_required
               or (p_status in ('locked','disabled') and p_reason = 'suspected_compromise')
        where id = p_user_id;"""
_CONSUME = """\
        set password_hash = p_password_hash, password_changed_at = now(),
            account_status = 'active'"""
_CONSUME_NEW = """\
        set password_hash = p_password_hash, password_changed_at = now(),
            account_status = 'active', reset_required = false"""


def _from_0006(name: str) -> str:
    """A function's definition from 0006, as `create or replace`."""
    path = Path(__file__).with_name("0006_admin_auth.py")
    spec = importlib.util.spec_from_file_location("rev0006", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path.name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    statements: list[str] = module._UP
    (sql,) = [s for s in statements if f"create function {name}(" in s]
    return sql.replace("create function", "create or replace function", 1)


def _patched(sql: str, changes: list[tuple[str, str]]) -> str:
    for old, new in changes:
        if sql.count(old) != 1:
            raise RuntimeError("0006 definition changed")
        sql = sql.replace(old, new)
    return sql


def upgrade() -> None:
    op.execute("alter table users add column reset_required boolean not null default false")
    op.execute("grant select (reset_required) on users to labtrack_admin")
    # Accounts already locked/disabled for suspected compromise before this revision: any such
    # event since the account was last made active or got a new password counts (not only the
    # latest lock event, which a later lock for another reason would hide).
    op.execute(
        """update users u set reset_required = true
           where u.account_status in ('locked','disabled')
             and exists (
               select 1 from audit_logs l
               where l.target_user_id = u.id
                 and (l.action = 'security.user_report'
                      or (l.action in ('admin.status_locked','admin.status_disabled')
                          and l.diff ->> 'reason' = 'suspected_compromise'))
                 and l.at > coalesce(u.password_changed_at, '-infinity')
                 and l.at > coalesce((select max(a.at) from audit_logs a
                                      where a.target_user_id = u.id
                                        and a.action = 'admin.status_active'),
                                     '-infinity'))"""
    )
    op.execute(_REPORT)
    op.execute(
        _patched(
            _from_0006("admin_set_status"),
            [
                (_SUPPORT_CHECK_OLD, ""),
                (_STATUS_READ, _STATUS_READ_NEW),
                (_STATUS_WRITE, _STATUS_WRITE_NEW),
            ],
        )
    )
    op.execute(_patched(_from_0006("activation_consume"), [(_CONSUME, _CONSUME_NEW)]))
    op.execute("revoke execute on all functions in schema public from public")
    op.execute("grant execute on function report_unwanted_admin_action() to labtrack_app")


def downgrade() -> None:
    # Dev only: security.user_report rows stay in the (append-only) audit log.
    op.execute("drop function if exists report_unwanted_admin_action()")
    op.execute(_from_0006("admin_set_status"))
    op.execute(_from_0006("activation_consume"))
    op.execute("alter table users drop column if exists reset_required")
