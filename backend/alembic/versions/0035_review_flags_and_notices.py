"""Flags on drafts, and the notice when a document has been read (Phase 5.2; docs/05; H5).

- Issue codes: `possible_critical` (a value that may be critical but cannot be told - the
  banner shows for it), `critical_unreadable` (critical text printed but not readable),
  `critical_inside_reference` (printed critical limits inside the reference range - a misread
  column, likely), `no_conversion` (a known unit with no listed factor: off the trend, no
  plausibility check), `ref_not_used` (a range printed, none could be picked for the person).
- A qualitative result may be `normal` against a printed qualitative reference ("Сөрөг"):
  the flag check allowed `normal` only with numeric limits.
- `notify_document_read(document)`: the one way to announce a read document. Called by the
  worker in the uploader's context, once the drafts are saved. It decides the recipients
  itself, so no caller can push about a profile to anyone else:
  - a document with a draft that may hold a critical value -> `critical_pending` to the
    owner, the uploader and caregivers who keep critical alerts on (as for missed-dose
    alerts: active caregiver access, the alert not paused by the owner, consents not
    withdrawn, a person and not an admin role, the owner not deleting the account - Q46);
  - otherwise `review_ready` to the owner and the uploader.
  Readers (doctor, viewer) are never told about a draft. One notice per person, kind and
  document (unique index); the push text names nothing (worker/push.py).
- notify(): `review_ready` / `critical_pending` are no longer accepted from the app (any
  writer could otherwise push them about a profile to its other members at will).

Revision ID: 0035
Revises: 0034
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEFINER = "security definer set search_path = pg_catalog, public, pg_temp"

_OLD_ISSUES = (
    "not_in_source",
    "implausible",
    "ref_suspicious",
    "flag_mismatch",
    "unknown_unit",
    "unknown_test",
    "date_future",
    "date_old",
    "date_ambiguous",
    "name_mismatch",
    "possible_duplicate",
    "large_delta",
    "low_confidence",
    "name_missing",
    "date_missing",
    "date_inconsistent",
    "unit_missing",
    "truncated",
)
ISSUES = (
    *_OLD_ISSUES,
    "possible_critical",
    "critical_unreadable",
    "critical_inside_reference",
    "no_conversion",
    "ref_not_used",
)

_FLAG_CHECK_OLD = """check (flag not in ('normal', 'low', 'high') or ref_low is not null
       or ref_high is not null or flag_source in ('lab_flag', 'patient_target'))"""
_FLAG_CHECK_NEW = """check (flag not in ('normal', 'low', 'high') or ref_low is not null
       or ref_high is not null or flag_source in ('lab_flag', 'patient_target')
       or (flag = 'normal' and qualitative is not null and ref_text is not null))"""

# notify() as 0021 left it, with the two draft kinds switched on or off
_NOTIFY = """
create or replace function notify(p_user_id uuid, p_kind text, p_patient_id uuid,
                                  p_entity_id text, p_title_key text)
returns void language plpgsql volatile {definer} as $$
declare
  allowed boolean;
begin
  allowed := case
    when p_kind in ('review_ready', 'critical_pending') then
      {drafts}
    -- an invitation's notice: for that pending invitation, and only once
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
    when p_kind = 'reminder' then p_user_id = public.app_user_id()
    else false
  end;
  if not coalesce(allowed, false) then
    raise exception 'notification not allowed' using errcode = '42501';
  end if;
  insert into public.notifications (user_id, kind, patient_id, entity_id, title_key)
    values (p_user_id, p_kind, p_patient_id, p_entity_id, p_title_key);
end $$
"""
_DRAFTS_0021 = """p_patient_id is not null and public.can_write_patient(p_patient_id)
      and exists (select 1 from public.patient_access a
                  where a.patient_id = p_patient_id and a.user_id = p_user_id
                    and a.revoked_at is null
                    and (a.expires_at is null or a.expires_at > now()))"""

# one user's own consents (patient_id is null), the latest row per required kind (as 0026)
_WITHDRAWN = """exists (
        select 1 from (
          select distinct on (c.kind) c.granted from public.consents c
          where c.user_id = {u} and c.patient_id is null
            and c.kind in ('terms', 'privacy', 'sensitive_data')
          order by c.kind, c.created_at desc, c.id desc) latest
        where not latest.granted)"""

_DOCUMENT_READ = f"""
create function notify_document_read(p_document_id uuid) returns void
language plpgsql volatile {_DEFINER} as $$
declare
  doc record;
  v_critical boolean;
  v_kind text;
begin
  select d.id, d.patient_id, d.recorded_by into doc from public.documents d
    join public.patients p on p.id = d.patient_id and p.deleted_at is null
    where d.id = p_document_id and d.status = 'needs_review';
  if doc.id is null or doc.recorded_by is distinct from public.app_user_id()
     or not public.can_write_patient(doc.patient_id) then
    raise exception 'notification not allowed' using errcode = '42501';
  end if;
  -- only drafts a reading of this document made (a run of this document)
  if not exists (select 1 from public.lab_reports r
                 join public.extraction_runs x on x.id = r.extraction_run_id
                   and x.document_id = doc.id
                 where r.document_id = doc.id and r.status = 'needs_review') then
    return;
  end if;
  -- an owner who asked to delete the account: nothing more is told about it (Q46)
  if exists (select 1 from public.patient_access o join public.users ou on ou.id = o.user_id
             where o.patient_id = doc.patient_id and o.level = 'owner'
               and o.revoked_at is null and ou.deleted_at is not null) then
    return;
  end if;
  v_critical := exists (select 1 from public.lab_reports r
                      join public.extraction_runs x on x.id = r.extraction_run_id
                        and x.document_id = doc.id
                      where r.document_id = doc.id and r.status = 'needs_review'
                        and r.has_unconfirmed_critical);
  v_kind := case when v_critical then 'critical_pending' else 'review_ready' end;
  insert into public.notifications (user_id, kind, patient_id, entity_id, title_key)
  select t.user_id, v_kind, doc.patient_id, doc.id::text, 'notification.' || v_kind
  from (
    -- the owner and the uploader (a caregiver who added it)
    select a.user_id from public.patient_access a
      join public.users u on u.id = a.user_id and u.deleted_at is null
      where a.patient_id = doc.patient_id and a.revoked_at is null
        and (a.expires_at is null or a.expires_at > now())
        and (a.level = 'owner' or a.user_id = doc.recorded_by)
        and a.level in ('owner', 'caregiver')
    union
    -- caregivers who keep critical alerts on
    select s.caregiver_user_id from public.caregiver_alert_settings s
      join public.patient_access a on a.patient_id = s.patient_id
        and a.user_id = s.caregiver_user_id and a.level = 'caregiver'
        and a.revoked_at is null and (a.expires_at is null or a.expires_at > now())
      join public.users u on u.id = s.caregiver_user_id and u.account_status = 'active'
        and u.deleted_at is null and u.role in ('user', 'doctor')
      where v_critical and s.patient_id = doc.patient_id and s.critical_result
        and not s.owner_paused
        and not {_WITHDRAWN.format(u="s.caregiver_user_id")}
        and not exists (select 1 from public.patient_access o
                        where o.patient_id = s.patient_id and o.level = 'owner'
                          and o.revoked_at is null
                          and {_WITHDRAWN.format(u="o.user_id")})
  ) t
  -- the caller learns nothing back (not even how many caregivers were told)
  on conflict do nothing;
end $$
"""

_NOTICE_INDEX = (
    "create unique index notifications_draft_notice on notifications (user_id, kind, entity_id)"
    " where kind in ('review_ready', 'critical_pending')"
)


def _issue_checks(issues: tuple[str, ...]) -> None:
    listed = ", ".join(f"'{i}'" for i in issues)
    for table in ("lab_results", "extraction_runs"):
        op.execute(f"alter table {table} drop constraint {table}_issues_check")
        op.execute(
            f"alter table {table} add constraint {table}_issues_check"
            f" check (issues <@ array[{listed}]::text[])"
        )


def _flag_check(check: str) -> None:
    op.execute("alter table lab_results drop constraint lab_results_flag_check")
    op.execute(f"alter table lab_results add constraint lab_results_flag_check {check}")


def upgrade() -> None:
    _issue_checks(ISSUES)
    # the unnamed check from 0031 has a generated name; find it by its text
    op.execute(
        """do $$
        declare c text;
        begin
          select conname into strict c from pg_constraint
            where conrelid = 'public.lab_results'::regclass and contype = 'c'
              and pg_get_constraintdef(oid) like '%flag_source = ANY%lab_flag%patient_target%'
              and pg_get_constraintdef(oid) like '%ref_low IS NOT NULL%';
          if c <> 'lab_results_flag_check' then  -- named so already after a downgrade
            execute format('alter table public.lab_results rename constraint %I'
                           ' to lab_results_flag_check', c);
          end if;
        end $$"""
    )
    _flag_check(_FLAG_CHECK_NEW)
    # older duplicates (0021's notify() let the app add these) would block the index
    op.execute(
        "delete from notifications n using notifications m"
        " where n.kind in ('review_ready', 'critical_pending') and m.kind = n.kind"
        " and m.user_id = n.user_id and m.entity_id = n.entity_id and m.id < n.id"
    )
    op.execute(_NOTICE_INDEX)
    op.execute(_NOTIFY.format(definer=_DEFINER, drafts="false"))
    op.execute(_DOCUMENT_READ)
    op.execute("revoke execute on function notify_document_read(uuid) from public")
    op.execute("grant execute on function notify_document_read(uuid) to labtrack_app")


def downgrade() -> None:
    op.execute("drop function notify_document_read(uuid)")
    op.execute(_NOTIFY.format(definer=_DEFINER, drafts=_DRAFTS_0021))
    op.execute("drop index notifications_draft_notice")
    op.execute("update lab_results set flag = 'unknown' where flag = 'normal'"
               " and ref_low is null and ref_high is null"
               " and flag_source not in ('lab_flag', 'patient_target')")  # fmt: skip
    _flag_check(_FLAG_CHECK_OLD)
    # rows keep their older issue codes only
    old = ", ".join(f"'{i}'" for i in _OLD_ISSUES)
    for table in ("lab_results", "extraction_runs"):
        op.execute(
            f"update {table} set issues = array(select i from unnest(issues) i"
            f" where i in ({old}))"
            f" where not (issues <@ array[{old}]::text[])"
        )
    _issue_checks(_OLD_ISSUES)
