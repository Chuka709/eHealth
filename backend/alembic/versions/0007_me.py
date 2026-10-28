"""The user's side of account administration (docs/04 §1 step 5c, Phase 1.7).

- report_unwanted_admin_action(): the "Би хүсээгүй" button. A user who sees an admin action
  they did not ask for (within 30 days of it) locks their own account: every session and live
  token ends, and a security event reaches the admins.
- Such a self-lock is treated like a lock for suspected compromise: support cannot lift it,
  only a super admin (after verifying the person).

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
      update public.users set account_status = 'locked'
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

_SUPPORT_CHECK_OLD = """           and (select l.diff ->> 'reason' from public.audit_logs l
                where l.action = 'admin.status_locked' and l.target_user_id = p_user_id
                order by l.at desc limit 1) = 'suspected_compromise' then"""
_SUPPORT_CHECK_NEW = """           and (select case when l.action = 'security.user_report'
                            then 'suspected_compromise' else l.diff ->> 'reason' end
                from public.audit_logs l
                where l.action in ('admin.status_locked','security.user_report')
                  and l.target_user_id = p_user_id
                order by l.at desc limit 1) = 'suspected_compromise' then"""


def _set_status_0006() -> str:
    path = Path(__file__).with_name("0006_admin_auth.py")
    spec = importlib.util.spec_from_file_location("rev0006", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path.name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    statements: list[str] = module._UP
    (sql,) = [s for s in statements if "create function admin_set_status(" in s]
    if sql.count(_SUPPORT_CHECK_OLD) != 1:
        raise RuntimeError("0006 admin_set_status changed")
    return sql.replace("create function", "create or replace function", 1)


def upgrade() -> None:
    op.execute(_REPORT)
    op.execute(_set_status_0006().replace(_SUPPORT_CHECK_OLD, _SUPPORT_CHECK_NEW))
    op.execute("revoke execute on all functions in schema public from public")
    op.execute("grant execute on function report_unwanted_admin_action() to labtrack_app")


def downgrade() -> None:
    op.execute("drop function if exists report_unwanted_admin_action()")
    op.execute(_set_status_0006())
