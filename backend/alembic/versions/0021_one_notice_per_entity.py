"""One notice per invitation and per dose alert (commit security review of 0020).

0020 let the owner call notify(..., 'share_invite', ...) again and again for one pending
invitation, and each call became a push to the invited person, past every invitation limit.
An invitation (and a dose alert) now gets its notice once: the entity must exist and must not
have been announced yet. A dose alert's notice also names that caregiver's own alert row.

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-10
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEFINER = "security definer set search_path = pg_catalog, public, pg_temp"

_HEAD = f"""
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
"""
_TAIL = """    when p_kind = 'reminder' then p_user_id = public.app_user_id()
    else false
  end;
  if not coalesce(allowed, false) then
    raise exception 'notification not allowed' using errcode = '42501';
  end if;
  insert into public.notifications (user_id, kind, patient_id, entity_id, title_key)
    values (p_user_id, p_kind, p_patient_id, p_entity_id, p_title_key);
end $$
"""

_NEW = (
    _HEAD
    + """    -- an invitation's notice: for that pending invitation, and only once
    when p_kind = 'share_invite' then
      p_patient_id is not null and public.is_owner(p_patient_id)
      and exists (select 1 from public.caregiver_invitations i
                  where i.id::text = p_entity_id and i.invited_user_id = p_user_id
                    and i.patient_id = p_patient_id and i.status = 'pending')
      and not exists (select 1 from public.notifications n
                      where n.kind = 'share_invite' and n.entity_id = p_entity_id)
    -- a missed dose: the caregiver's own alert row, announced once, while alerts are on
    when p_kind = 'dose_overdue' then
      p_user_id = public.app_user_id() and p_patient_id is not null
      and public.caregiver_alerts_on(p_patient_id)
      and exists (select 1 from public.dose_alerts d
                  where d.id::text = p_entity_id and d.alerted_user_id = p_user_id
                    and d.patient_id = p_patient_id)
      and not exists (select 1 from public.notifications n
                      where n.kind = 'dose_overdue' and n.entity_id = p_entity_id)
"""
    + _TAIL
)

# as 0020 left it
_OLD = (
    _HEAD
    + """    -- an invitation's notice only for that pending invitation
    when p_kind = 'share_invite' then
      p_patient_id is not null and public.is_owner(p_patient_id)
      and exists (select 1 from public.caregiver_invitations i
                  where i.id::text = p_entity_id and i.invited_user_id = p_user_id
                    and i.patient_id = p_patient_id and i.status = 'pending')
    when p_kind = 'dose_overdue' then
      p_user_id = public.app_user_id() and p_patient_id is not null
      and public.caregiver_alerts_on(p_patient_id)
"""
    + _TAIL
)

_INDEX = (
    "create index notifications_entity on notifications (kind, entity_id)"
    " where kind in ('share_invite', 'dose_overdue')"
)


def upgrade() -> None:
    op.execute(_INDEX)
    op.execute(_NEW)


def downgrade() -> None:
    op.execute(_OLD)
    op.execute("drop index notifications_entity")
