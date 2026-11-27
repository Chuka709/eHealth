"""Push only while access lasts, and a moved token keeps the reset notice (commit review of 0023).

- maint_push_queue(): a notice about a profile is pushed only while the recipient still has
  access to it (any level; a dose alert needs caregiver access). An invitation's notice is
  for someone who has no access yet, and admin_reset is about the account: both exempt.
- set_session_push_token(): a token taken over by another account no longer leaves a session
  an admin reset signed out in the last day, so someone who learnt a victim's token before a
  fraudulent reset cannot silence the reset notice to the victim's phone (H12). Every move
  between accounts is audited (session.push_token_moved, ids and a count only).
  Proof that the caller holds the device (a per-install key) is 2.8f.

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-11
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEFINER = "security definer set search_path = pg_catalog, public, pg_temp"
_PUSHED = "'share_invite','dose_overdue','admin_reset','review_ready','critical_pending'"
_ACCESS = """exists (select 1 from public.patient_access a
               where a.patient_id = n.patient_id and a.user_id = n.user_id
                 and a.revoked_at is null
                 and (a.expires_at is null or a.expires_at > now()){level})"""
_GATE_0023 = (
    "\n        and (n.kind <> 'dose_overdue' or "
    + _ACCESS.format(level="\n                 and a.level = 'caregiver'")
    + ")"
)
_GATE_0024 = (
    "\n        and (n.patient_id is null or n.kind in ('share_invite', 'admin_reset')"
    "\n             or (n.kind <> 'dose_overdue' and "
    + _ACCESS.format(level="")
    + ")\n             or (n.kind = 'dose_overdue' and "
    + _ACCESS.format(level="\n                 and a.level = 'caregiver'")
    + "))"
)


def _queue(gate: str) -> str:
    return f"""
    create or replace function maint_push_queue(p_limit int)
    returns table (notification_id bigint, kind text, title_key text, entity_id text,
                   patient_id uuid, session_id uuid, push_token text, locale text)
    language sql stable {_DEFINER} as $$
      select n.id, n.kind, n.title_key, n.entity_id, n.patient_id, s.id, s.push_token, u.locale
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
        and not exists (select 1 from public.push_receipts r
                        where r.notification_id = n.id and r.session_id = s.id){gate}
      order by n.id, s.id limit least(greatest(p_limit, 1), 500)
    $$
    """


def _token_setter(keep_reset_sessions: bool) -> str:
    keep = (
        """
            and not coalesce(revoked_reason = 'admin_reset'
                             and revoked_at > now() - interval '1 day', false)"""
        if keep_reset_sessions
        else ""
    )
    audit = (
        """
        get diagnostics moved = row_count;
        if moved > 0 then
          insert into public.audit_logs (actor_id, actor_role, action, entity, entity_id, diff)
            select u.id, u.role::text, 'session.push_token_moved', 'session', p_session::text,
                   jsonb_build_object('sessions', moved)
            from public.users u where u.id = public.app_user_id();
        end if;"""
        if keep_reset_sessions
        else ""
    )
    other = (
        "id <> p_session and user_id <> public.app_user_id()"
        if keep_reset_sessions
        else "id <> p_session"
    )
    same_user = (
        """
        -- the same account's other sessions just lose it (a re-login on the same phone)
        update public.sessions set push_token = null
          where push_token = p_token and id <> p_session and user_id = public.app_user_id();"""
        if keep_reset_sessions
        else ""
    )
    declare = "\n    declare\n      moved int;" if keep_reset_sessions else ""
    return f"""
    create or replace function set_session_push_token(p_session uuid, p_token text)
    returns boolean
    language plpgsql volatile {_DEFINER} as $${declare}
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
      if p_token is not null then{same_user}
        update public.sessions set push_token = null
          where push_token = p_token and {other}{keep};{audit}
      end if;
      update public.sessions set push_token = p_token where id = p_session;
      return true;
    end $$
    """


def upgrade() -> None:
    op.execute(_queue(_GATE_0024))
    op.execute(_token_setter(keep_reset_sessions=True))


def downgrade() -> None:
    op.execute(_token_setter(keep_reset_sessions=False))
    op.execute(_queue(_GATE_0023))
