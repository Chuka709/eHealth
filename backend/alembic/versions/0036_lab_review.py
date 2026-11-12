"""Review of draft lab reports: edit, add, delete, confirm, reject (Phase 5.3; docs/06 §4).

- A draft (`needs_review`) is edited by any writer of the profile (owner, caregiver): the
  report's date and lab, a row's value, unit, ranges, test and what follows from them (the
  API recomputes them in `core` - rule 6), and `acknowledged` - the issues the person looked
  at and accepted. A confirmed or rejected report is never edited again (a new upload or a
  later correction step replaces it).
- Rows may be added to and deleted from a draft by any writer (0031 let only the report's
  recorder add, and nobody delete).
- A row's date follows its report's, also when the report's date is changed.
- `confirm_lab_report(report)`: only a draft with a date (not ambiguous, not in the
  future) and every row's issues
  acknowledged (or none); sets confirmed_by/at, clears `has_unconfirmed_critical`, audits
  (ids only); the document is `confirmed` once none of its reports is a draft any more.
  `reject_lab_report(report)`: the draft is kept as `rejected` (never shown as a value).
  Errors: 'report not a draft' / 'report has open issues' / 'report has no date' (42501 for
  no access).
- A confirmed report: shown to the profile's readers (0031); its numbers enter the trend.

Revision ID: 0036
Revises: 0035
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEFINER = "security definer set search_path = pg_catalog, public, pg_temp"

_RESULT_EDIT = (
    "test_code, raw_value, raw_unit, value_numeric, comparator, value_text, qualitative,"
    " ref_text, ref_low, ref_high, critical_text, critical_low, critical_high, unit_canonical,"
    " value_canonical, ref_low_canonical, ref_high_canonical, critical_low_canonical,"
    " critical_high_canonical, flag, flag_source, flag_mismatch, confidence, issues,"
    " acknowledged, edited_by_user, read_value, read_critical_text, read_was_critical"
)
_REPORT_EDIT = (
    "lab_name, collected_at, collected_precision, date_ambiguous, has_unconfirmed_critical"
)
_DRAFT = """exists (select 1 from lab_reports r
             where r.id = report_id and r.patient_id = lab_results.patient_id
               and r.status = 'needs_review')"""
_RESULT_ADD_0031 = """exists (select 1 from lab_reports r
                  where r.id = report_id and r.patient_id = lab_results.patient_id
                    and r.status = 'needs_review' and r.recorded_by = app_user_id())"""

_STATUS_FN = f"""
create function {{name}}(p_report_id uuid) returns void
language plpgsql volatile {_DEFINER} as $$
declare
  rep record;
begin
  select r.id, r.patient_id, r.document_id, r.status, r.collected_at, r.date_ambiguous
    into rep
    from public.lab_reports r where r.id = p_report_id for update;
  if rep.id is null or not public.can_write_patient(rep.patient_id) then
    raise exception 'report not found' using errcode = '42501';
  end if;
  if rep.status <> 'needs_review' then
    raise exception 'report not a draft';
  end if;
{{checks}}
  update public.lab_reports set {{set}}, updated_by = public.app_user_id(),
    updated_at = now() where id = rep.id;
  perform public.audit_write('{{action}}', 'lab_report', rep.id::text, rep.patient_id, null);
  -- the document is done once none of its reports waits for review
  if rep.document_id is not null and not exists (
       select 1 from public.lab_reports r
       where r.document_id = rep.document_id and r.status = 'needs_review') then
    update public.documents set status = case when exists (
        select 1 from public.lab_reports r
        where r.document_id = rep.document_id and r.status = 'confirmed')
      then 'confirmed'::public.doc_status else 'rejected'::public.doc_status end
      where id = rep.document_id and status = 'needs_review';
  end if;
end $$
"""
# a date the person chose: never missing, ambiguous or in the future (H3, H30)
_CONFIRM_CHECKS = """
  if rep.collected_at is null or rep.date_ambiguous
     or rep.collected_at > now() + interval '1 day' then
    raise exception 'report has no date';
  end if;
  if not exists (select 1 from public.lab_results x where x.report_id = rep.id) then
    raise exception 'report has no results';
  end if;
  if exists (select 1 from public.lab_results x
             where x.report_id = rep.id and not (x.issues <@ x.acknowledged)) then
    raise exception 'report has open issues';
  end if;"""
_CONFIRM_SET = (
    "status = 'confirmed', confirmed_by = public.app_user_id(), confirmed_at = now(),"
    " has_unconfirmed_critical = false"
)
_REJECT_SET = "status = 'rejected', has_unconfirmed_critical = false"

_FOLLOW_DATE = f"""
create function lab_reports_follow_date() returns trigger
language plpgsql {_DEFINER} as $$
begin
  update public.lab_results set collected_at = new.collected_at
    where report_id = new.id and patient_id = new.patient_id
      and collected_at is distinct from new.collected_at;
  return new;
end $$
"""


# as 0035 left lab_results.issues
ISSUES = (
    "not_in_source", "implausible", "ref_suspicious", "flag_mismatch", "unknown_unit",
    "unknown_test", "date_future", "date_old", "date_ambiguous", "name_mismatch",
    "possible_duplicate", "large_delta", "low_confidence", "name_missing", "date_missing",
    "date_inconsistent", "unit_missing", "truncated", "possible_critical",
    "critical_unreadable", "critical_inside_reference", "no_conversion", "ref_not_used",
)  # fmt: skip
# a row read as critical (or possibly so) whose edit makes it no longer so (medical review)
NEW_ISSUES = (*ISSUES, "critical_edited")


def _issue_list(issues: tuple[str, ...] = NEW_ISSUES) -> str:
    return ", ".join(f"'{i}'" for i in issues)


def _issue_checks(issues: tuple[str, ...]) -> None:
    for table in ("lab_results", "extraction_runs"):
        op.execute(f"alter table {table} drop constraint {table}_issues_check")
        op.execute(
            f"alter table {table} add constraint {table}_issues_check"
            f" check (issues <@ array[{_issue_list(issues)}]::text[])"
        )


def upgrade() -> None:
    _issue_checks(NEW_ISSUES)
    op.execute("alter table lab_results add column acknowledged text[] not null default '{}'")
    # only issues the row has can be accepted (security review L3)
    op.execute(
        "alter table lab_results add constraint lab_results_acknowledged_check"
        " check (acknowledged <@ issues)"
    )
    # what was read before the person's first edit, shown as "corrected from" (medical M-3)
    op.execute(
        "alter table lab_results add column read_value text"
        " check (length(read_value) <= 200),"
        " add column read_critical_text text check (length(read_critical_text) <= 300),"
        " add column read_was_critical boolean"
    )
    # edits: drafts only, by a writer of the profile
    op.execute(f"grant update ({_RESULT_EDIT}) on lab_results to labtrack_app")
    op.execute(
        f"""create policy lab_results_update on lab_results for update to labtrack_app
           using (can_write_patient(patient_id) and {_DRAFT})
           with check (can_write_patient(patient_id) and {_DRAFT})"""
    )
    op.execute("drop policy lab_results_delete on lab_results")
    op.execute(
        f"""create policy lab_results_delete on lab_results for delete to labtrack_app
           using (can_write_patient(patient_id) and {_DRAFT})"""
    )
    op.execute("grant delete on lab_results to labtrack_app")
    op.execute("drop policy lab_results_insert on lab_results")
    op.execute(
        f"""create policy lab_results_insert on lab_results for insert to labtrack_app
           with check (can_write_patient(patient_id) and {_DRAFT})"""
    )
    op.execute(f"grant update ({_REPORT_EDIT}) on lab_reports to labtrack_app")
    op.execute(
        """create policy lab_reports_update on lab_reports for update to labtrack_app
           using (can_write_patient(patient_id) and status = 'needs_review')
           with check (can_write_patient(patient_id) and status = 'needs_review')"""
    )
    op.execute(_FOLLOW_DATE)
    op.execute("revoke execute on function lab_reports_follow_date() from public")
    op.execute(
        """create trigger lab_reports_follow_date after update of collected_at on lab_reports
           for each row execute function lab_reports_follow_date()"""
    )
    for name, checks, set_, action in (
        ("confirm_lab_report", _CONFIRM_CHECKS, _CONFIRM_SET, "report.confirm"),
        ("reject_lab_report", "", _REJECT_SET, "report.reject"),
    ):
        op.execute(_STATUS_FN.format(name=name, checks=checks, set=set_, action=action))
        op.execute(f"revoke execute on function {name}(uuid) from public")
        op.execute(f"grant execute on function {name}(uuid) to labtrack_app")


def downgrade() -> None:
    op.execute("drop function reject_lab_report(uuid)")
    op.execute("drop function confirm_lab_report(uuid)")
    op.execute("drop trigger lab_reports_follow_date on lab_reports")
    op.execute("drop function lab_reports_follow_date()")
    op.execute("drop policy lab_reports_update on lab_reports")
    op.execute(f"revoke update ({_REPORT_EDIT}) on lab_reports from labtrack_app")
    op.execute("drop policy lab_results_insert on lab_results")
    op.execute(
        f"""create policy lab_results_insert on lab_results for insert to labtrack_app
           with check (can_write_patient(patient_id) and {_RESULT_ADD_0031})"""
    )
    op.execute("drop policy lab_results_delete on lab_results")
    op.execute(
        """create policy lab_results_delete on lab_results for delete to labtrack_app
           using (can_write_patient(patient_id) and false)"""
    )
    op.execute("revoke delete on lab_results from labtrack_app")
    op.execute("drop policy lab_results_update on lab_results")
    op.execute(f"revoke update ({_RESULT_EDIT}) on lab_results from labtrack_app")
    op.execute(
        "alter table lab_results drop column acknowledged, drop column read_value,"
        " drop column read_critical_text, drop column read_was_critical"
    )
    op.execute(
        "update lab_results set issues = array_remove(issues, 'critical_edited')"
        " where 'critical_edited' = any(issues)"
    )
    _issue_checks(ISSUES)
