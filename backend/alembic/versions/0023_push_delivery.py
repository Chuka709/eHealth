"""Push delivery and the Q42 decision (Phase 2.8b).

- maint_push_queue() also returns the recipient's locale: the worker writes the visible text in
  the user's language without reading users itself (the text names nobody: security L3).
- push_receipts.token_sha256: the token a ticket went to, as a hash. A late DeviceNotRegistered
  receipt clears a session's token only if it still is that token, so a phone that registered
  a new one in the meantime keeps it (maint_forget_receipt_token).
- Q42 (user, 2026-11-10): withdrawing the caregiver_sharing consent ends, at once, every
  caregiver's access to the profiles the user owns (and their alert settings), not only the
  open invitations. Audited by id only (caregiver.consent_revoke). Only the user-level
  consent counts (patient_id is null), as caregiver_sharing_given() reads it.
- security review: the queue skips devices that already have a receipt for a notice (no
  repeat to them while a notice is retried for the others) and dose alerts to someone who is
  no longer the profile's caregiver.

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-10
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEFINER = "security definer set search_path = pg_catalog, public, pg_temp"
_PUSHED = "'share_invite','dose_overdue','admin_reset','review_ready','critical_pending'"


def _queue(with_locale: bool) -> str:
    columns = ", locale text" if with_locale else ""
    select = ", u.locale" if with_locale else ""
    # 0023 (security review): a device that already has a receipt for the notice is not sent
    # it again (a notice is retried only for the devices still due), and a dose alert goes
    # only to someone who still is that profile's caregiver
    extra = (
        """
        and not exists (select 1 from public.push_receipts r
                        where r.notification_id = n.id and r.session_id = s.id)
        and (n.kind <> 'dose_overdue' or exists (
               select 1 from public.patient_access a
               where a.patient_id = n.patient_id and a.user_id = n.user_id
                 and a.level = 'caregiver' and a.revoked_at is null
                 and (a.expires_at is null or a.expires_at > now())))"""
        if with_locale
        else ""
    )
    return f"""
    create function maint_push_queue(p_limit int)
    returns table (notification_id bigint, kind text, title_key text, entity_id text,
                   patient_id uuid, session_id uuid, push_token text{columns})
    language sql stable {_DEFINER} as $$
      select n.id, n.kind, n.title_key, n.entity_id, n.patient_id, s.id, s.push_token{select}
      from public.notifications n
      join public.sessions s on s.user_id = n.user_id and s.push_token is not null
        and ((s.revoked_at is null and s.expires_at > now())
             -- the devices an admin reset just signed out still hear about it (H12)
             or (n.kind = 'admin_reset' and s.revoked_reason = 'admin_reset'
                 and s.revoked_at > now() - interval '1 day'))
      join public.users u on u.id = n.user_id
        and (u.account_status = 'active' or n.kind = 'admin_reset')
      where n.sent_push_at is null and n.created_at > now() - interval '1 day'
        and n.kind in ({_PUSHED}){extra}
      order by n.id, s.id limit least(greatest(p_limit, 1), 500)
    $$
    """


_FORGET_RECEIPT_TOKEN = f"""
create function maint_forget_receipt_token(p_receipt bigint) returns int
language sql volatile {_DEFINER} as $$
  with gone as (
    update public.sessions s set push_token = null
    from public.push_receipts r
    where r.id = p_receipt and s.id = r.session_id and s.push_token is not null
      and r.token_sha256 = public.digest(s.push_token, 'sha256')
    returning 1)
  select count(*)::int from gone
$$
"""

# a profile-level row (patient_id set) is not the user's consent that lets caregivers in
# (caregiver_sharing_given reads patient_id is null only): it no longer ends anything
_TRIGGER = """create trigger consents_caregiver_withdrawn after insert on consents
   for each row when (new.kind = 'caregiver_sharing' and not new.granted{only_user})
   execute function consents_caregiver_withdrawn()"""

_CONSENT_WITHDRAWN_OLD = f"""
create or replace function consents_caregiver_withdrawn() returns trigger
language plpgsql {_DEFINER} as $$
begin
  update public.caregiver_invitations set status = 'revoked', responded_at = now()
    where invited_by = new.user_id and status = 'pending';
  return null;
end $$
"""

# Q42: the consent is what lets caregivers in, so withdrawing it lets them out
_CONSENT_WITHDRAWN = f"""
create or replace function consents_caregiver_withdrawn() returns trigger
language plpgsql {_DEFINER} as $$
declare
  ended record;
begin
  update public.caregiver_invitations set status = 'revoked', responded_at = now()
    where invited_by = new.user_id and status = 'pending';
  for ended in
    update public.patient_access a set revoked_at = now()
      where a.level = 'caregiver' and a.revoked_at is null
        and a.patient_id in (select o.patient_id from public.patient_access o
                             where o.user_id = new.user_id and o.level = 'owner'
                               and o.revoked_at is null)
      returning a.patient_id, a.user_id
  loop
    delete from public.caregiver_alert_settings
      where patient_id = ended.patient_id and caregiver_user_id = ended.user_id;
    insert into public.audit_logs (actor_id, actor_role, action, entity, entity_id,
                                   patient_id, diff)
      select u.id, u.role::text, 'caregiver.consent_revoke', 'user', ended.user_id::text,
             ended.patient_id, null
      from public.users u where u.id = new.user_id;
  end loop;
  return null;
end $$
"""


def upgrade() -> None:
    op.execute(
        "alter table push_receipts add column token_sha256 bytea"
        " check (octet_length(token_sha256) = 32)"
    )
    # Expo's request-level codes have underscores (PUSH_TOO_MANY_EXPERIENCE_IDS)
    op.execute("alter table push_receipts drop constraint push_receipts_error_check")
    op.execute(
        "alter table push_receipts add constraint push_receipts_error_check"
        " check (error ~ '^[A-Za-z_]{1,40}$')"
    )
    op.execute("drop function maint_push_queue(int)")
    op.execute(_queue(with_locale=True))
    op.execute(_FORGET_RECEIPT_TOKEN)
    op.execute("revoke execute on function maint_push_queue(int) from public")
    op.execute("revoke execute on function maint_forget_receipt_token(bigint) from public")
    op.execute(
        """grant execute on function maint_push_queue(int), maint_forget_receipt_token(bigint)
           to labtrack_maint"""
    )
    op.execute(_CONSENT_WITHDRAWN)
    op.execute("drop trigger consents_caregiver_withdrawn on consents")
    op.execute(_TRIGGER.format(only_user=" and new.patient_id is null"))


def downgrade() -> None:
    op.execute("drop trigger consents_caregiver_withdrawn on consents")
    op.execute(_TRIGGER.format(only_user=""))
    op.execute(_CONSENT_WITHDRAWN_OLD)
    op.execute("drop function maint_forget_receipt_token(bigint)")
    op.execute("drop function maint_push_queue(int)")
    op.execute(_queue(with_locale=False))
    op.execute("revoke execute on function maint_push_queue(int) from public")
    op.execute("grant execute on function maint_push_queue(int) to labtrack_maint")
    op.execute("alter table push_receipts drop column token_sha256")
    op.execute("update push_receipts set error = 'Unknown' where error ~ '_'")
    op.execute("alter table push_receipts drop constraint push_receipts_error_check")
    op.execute(
        "alter table push_receipts add constraint push_receipts_error_check"
        " check (error ~ '^[A-Za-z]{1,40}$')"
    )
