"""Results typed in by hand, and a document moved to the right profile (Phase 5.4; docs/06 §4).

- A report typed in by the person (`POST …/reports`): no reading, no run; optionally linked to
  one of the profile's documents (a scan or photo that is not read - Q50). Confirming it sets
  such a document `confirmed` too (0036 did so only for a document waiting for review).
- `lab_reports.source` ('read' | 'typed'), set by the database from how the report was made
  (a reading has a run): shown to everyone who sees the report, never written by the app.
- `notify_report_critical(report)`: a typed-in draft that may hold a critical value tells the
  owner and the caregivers who keep critical alerts on, as a read document does (H5), but not
  the person acting; once per report. Asked after every change of a typed-in draft (it may
  become critical later) and after a move.
- `move_document(document, profile)`: "wrong profile" - only the source profile's owner moves
  a document (a caregiver never takes one out of the owner's profile), to another profile they
  write, when it is read or failed (never while being read) and none of its reports is
  confirmed. The composite foreign keys carry the profile along (on update cascade); accepted
  issues, the printed-name score and the AI request (made for the old profile) go; the old
  profile's notices about it are withdrawn and the new profile is told as for a read document
  (`notify_document_read` now also for the owner, not only the uploader). Audited on both
  profiles with both ids. A document keeps its storage key (its prefix is the first profile -
  only the stored key is used to read or delete it).

Revision ID: 0037
Revises: 0036
"""

from collections.abc import Sequence
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

from alembic import op

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEFINER = "security definer set search_path = pg_catalog, public, pg_temp"

# (table, constraint, definition, on delete)
_FKS = (
    ("extraction_runs", "extraction_runs_document_id_patient_id_fkey",
     "(document_id, patient_id) references documents (id, patient_id)", "on delete cascade"),
    ("lab_reports", "lab_reports_document_id_patient_id_fkey",
     "(document_id, patient_id) references documents (id, patient_id)",
     "on delete set null (document_id)"),
    ("lab_reports", "lab_reports_extraction_run_id_patient_id_fkey",
     "(extraction_run_id, patient_id) references extraction_runs (id, patient_id)",
     "on delete set null (extraction_run_id)"),
    ("lab_results", "lab_results_report_id_patient_id_fkey",
     "(report_id, patient_id) references lab_reports (id, patient_id)", "on delete cascade"),
    ("ai_requests", "ai_requests_document_id_patient_id_fkey",
     "(document_id, patient_id) references documents (id, patient_id)", "on delete cascade"),
)  # fmt: skip

_MOVE = f"""
create function move_document(p_document_id uuid, p_target uuid) returns void
language plpgsql volatile {_DEFINER} as $$
declare
  doc record;
begin
  select d.id, d.patient_id, d.status into doc from public.documents d
    where d.id = p_document_id for update;
  if doc.id is null or not public.can_write_patient(doc.patient_id)
     or not public.is_owner(doc.patient_id) then
    raise exception 'document not found' using errcode = '42501';
  end if;
  if p_target = doc.patient_id or not public.can_write_patient(p_target)
     or exists (select 1 from public.patients p where p.id = p_target and p.deleted_at is not null)
  then
    raise exception 'target not allowed' using errcode = '42501';
  end if;
  if doc.status not in ('needs_review', 'failed', 'rejected') then
    raise exception 'document not ready';
  end if;
  if exists (select 1 from public.lab_reports r
             where r.document_id = doc.id and r.status = 'confirmed') then
    raise exception 'document has confirmed reports';
  end if;
  if (select count(*) from public.documents where patient_id = p_target) >= 2000 then
    raise exception 'too many documents';
  end if;
  -- reviewed again on the new profile: what was accepted goes, and the printed name was
  -- checked against the old profile only (it is not kept - 0031)
  update public.lab_results x set acknowledged = '{{}}'
    from public.lab_reports r where r.id = x.report_id and r.document_id = doc.id;
  update public.lab_reports set name_match_score = null where document_id = doc.id;
  delete from public.ai_requests where document_id = doc.id;
  -- the old profile is no longer told about someone else's result
  delete from public.notifications
    where patient_id = doc.patient_id and kind in ('review_ready', 'critical_pending')
      and (entity_id = doc.id::text
           or entity_id in (select r.id::text from public.lab_reports r
                            where r.document_id = doc.id));
  -- one statement: the composite keys carry the profile to runs, reports and rows
  update public.documents set patient_id = p_target where id = doc.id;
  perform public.audit_write('document.move', 'document', doc.id::text, doc.patient_id,
    jsonb_build_object('from', doc.patient_id, 'to', p_target));
  perform public.audit_write('document.move', 'document', doc.id::text, p_target,
    jsonb_build_object('from', doc.patient_id, 'to', p_target));
end $$
"""

_SOURCE = f"""
create function lab_reports_source() returns trigger
language plpgsql {_DEFINER} as $$
begin
  new.source := case when new.extraction_run_id is null then 'typed' else 'read' end;
  return new;
end $$
"""

_DOC_DONE_0036 = "where id = rep.document_id and status = 'needs_review';"
_DOC_DONE = "where id = rep.document_id and status in ('needs_review', 'failed');"
_UPLOADER_0035 = "doc.recorded_by is distinct from public.app_user_id()"
_UPLOADER_OR_OWNER = (
    "(doc.recorded_by is distinct from public.app_user_id()"
    " and not public.is_owner(doc.patient_id))"
)


def _sibling(name: str) -> ModuleType:
    """An earlier revision's SQL text (committed revisions do not change)."""
    path = Path(__file__).with_name(name)
    spec = spec_from_file_location(f"labtrack_rev_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path.name)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _replaced(text: str, old: str, new: str) -> str:
    if old not in text:
        raise RuntimeError(old)  # never a silent no-op
    return text.replace(old, new)


def _critical_notice() -> str:
    """notify_document_read()'s recipients (0035), for a typed-in report, minus the typist."""
    withdrawn: str = _sibling("0035_review_flags_and_notices.py")._WITHDRAWN
    return f"""
create function notify_report_critical(p_report_id uuid) returns void
language plpgsql volatile {_DEFINER} as $$
declare
  rep record;
begin
  select r.id, r.patient_id, r.status, r.source, r.has_unconfirmed_critical
    into rep from public.lab_reports r
    join public.patients p on p.id = r.patient_id and p.deleted_at is null
    where r.id = p_report_id;
  -- any writer of the profile may ask (after an edit, a move): the database picks who is told
  if rep.id is null or not public.can_write_patient(rep.patient_id) then
    raise exception 'notification not allowed' using errcode = '42501';
  end if;
  if rep.status <> 'needs_review' or rep.source <> 'typed' or not rep.has_unconfirmed_critical
  then
    return;
  end if;
  if exists (select 1 from public.patient_access o join public.users ou on ou.id = o.user_id
             where o.patient_id = rep.patient_id and o.level = 'owner'
               and o.revoked_at is null and ou.deleted_at is not null) then
    return;  -- Q46
  end if;
  insert into public.notifications (user_id, kind, patient_id, entity_id, title_key)
  select t.user_id, 'critical_pending', rep.patient_id, rep.id::text,
         'notification.critical_pending'
  from (
    select a.user_id from public.patient_access a
      join public.users u on u.id = a.user_id and u.deleted_at is null
      where a.patient_id = rep.patient_id and a.level = 'owner' and a.revoked_at is null
    union
    select s.caregiver_user_id from public.caregiver_alert_settings s
      join public.patient_access a on a.patient_id = s.patient_id
        and a.user_id = s.caregiver_user_id and a.level = 'caregiver'
        and a.revoked_at is null and (a.expires_at is null or a.expires_at > now())
      join public.users u on u.id = s.caregiver_user_id and u.account_status = 'active'
        and u.deleted_at is null and u.role in ('user', 'doctor')
      where s.patient_id = rep.patient_id and s.critical_result and not s.owner_paused
        and not {withdrawn.format(u="s.caregiver_user_id")}
        and not exists (select 1 from public.patient_access o
                        where o.patient_id = s.patient_id and o.level = 'owner'
                          and o.revoked_at is null
                          and {withdrawn.format(u="o.user_id")})
  ) t
  where t.user_id <> public.app_user_id()
  on conflict do nothing;
end $$
"""


def _document_read(uploader: str, replacement: str) -> str:
    text: str = _sibling("0035_review_flags_and_notices.py")._DOCUMENT_READ
    text = _replaced(text, "create function", "create or replace function")
    return _replaced(text, uploader, replacement) if uploader != replacement else text


def _fks(on_update: str) -> None:
    for table, name, definition, on_delete in _FKS:
        op.execute(f"alter table {table} drop constraint {name}")
        op.execute(
            f"alter table {table} add constraint {name} foreign key {definition}"
            f" {on_delete}{on_update}"
        )


def _status_functions(done: str) -> None:
    """confirm/reject as 0036 wrote them, with the document's final status rule."""
    rev = _sibling("0036_lab_review.py")
    for name, checks, set_, action in (
        ("confirm_lab_report", rev._CONFIRM_CHECKS, rev._CONFIRM_SET, "report.confirm"),
        ("reject_lab_report", "", rev._REJECT_SET, "report.reject"),
    ):
        body = rev._STATUS_FN.format(name=name, checks=checks, set=set_, action=action)
        body = _replaced(body, "create function", "create or replace function")
        op.execute(_replaced(body, _DOC_DONE_0036, done))


def upgrade() -> None:
    _fks(" on update cascade")
    _status_functions(_DOC_DONE)
    op.execute(
        "alter table lab_reports add column source text not null default 'read'"
        " check (source in ('read', 'typed'))"
    )
    op.execute("update lab_reports set source = 'typed' where extraction_run_id is null")
    op.execute(_SOURCE)
    op.execute("revoke execute on function lab_reports_source() from public")
    op.execute(
        """create trigger lab_reports_source before insert on lab_reports
           for each row execute function lab_reports_source()"""
    )
    op.execute(_MOVE)
    op.execute(_document_read(_UPLOADER_0035, _UPLOADER_OR_OWNER))
    op.execute(_critical_notice())
    for fn in ("move_document(uuid, uuid)", "notify_report_critical(uuid)"):
        op.execute(f"revoke execute on function {fn} from public")
        op.execute(f"grant execute on function {fn} to labtrack_app")


def downgrade() -> None:
    op.execute("drop function notify_report_critical(uuid)")
    op.execute(_document_read(_UPLOADER_0035, _UPLOADER_0035))
    op.execute("drop function move_document(uuid, uuid)")
    op.execute("drop trigger lab_reports_source on lab_reports")
    op.execute("drop function lab_reports_source()")
    op.execute("alter table lab_reports drop column source")
    _status_functions(_DOC_DONE_0036)
    _fks("")
