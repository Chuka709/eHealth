"""Extraction: date precision, analysed time, more issue codes, stuck documents (Phase 4.4).

From the 4.4 reviews:
- `lab_reports.collected_precision` ('day' | 'minute'): a report that prints only the day
  (УНТЭ "Илгээсэн") is kept as that day, never as a made-up midnight time - it is shown
  without a time and never used where the hour matters (tacrolimus trough vs dose; H30).
  `analysed_at`: when the lab analysed the sample (УНТЭ "Шинжилсэн"), kept apart.
- Issue codes: `name_missing`, `date_missing`, `date_inconsistent`, `unit_missing`,
  `truncated` (medical review 4.4).
- `maint_sweep_extractions()`: a document left in "processing" (worker killed, time limit)
  for 10 minutes is "failed" with `extraction_timeout`; one still "queued" after 15 minutes
  (a lost task) is handed back - ids only - to read again, at most every 15 minutes, until a
  day after the upload, then failed.
  Runs as labtrack_maint; returns document and uploader ids only.

Revision ID: 0032
Revises: 0031
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD = (
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
)
ISSUES = (
    *_OLD,
    "name_missing",
    "date_missing",
    "date_inconsistent",
    "unit_missing",
    "truncated",
)


def _issue_checks(issues: tuple[str, ...]) -> None:
    listed = ", ".join(f"'{i}'" for i in issues)
    for table in ("lab_results", "extraction_runs"):
        op.execute(f"alter table {table} drop constraint {table}_issues_check")
        op.execute(
            f"alter table {table} add constraint {table}_issues_check"
            f" check (issues <@ array[{listed}]::text[])"
        )


def upgrade() -> None:
    _issue_checks(ISSUES)
    op.execute(
        "alter table lab_reports add column collected_precision text not null default 'minute'"
        " check (collected_precision in ('day', 'minute')),"
        " add column analysed_at timestamptz"
    )
    op.execute("grant insert (collected_precision, analysed_at) on lab_reports to labtrack_app")
    op.execute(
        """create function maint_sweep_extractions()
           returns table (document_id uuid, user_id uuid)
           language plpgsql volatile security definer
           set search_path = pg_catalog, public, pg_temp as $$
           begin
             update public.documents d set status = 'failed', error_code = 'extraction_timeout'
               where (d.status = 'processing' and d.updated_at < now() - interval '10 minutes')
                  or (d.status = 'queued' and d.created_at < now() - interval '1 day');
             -- handed back at most every 15 minutes: the time it was handed back is kept
             return query
               update public.documents d set updated_at = now()
                where d.status = 'queued' and d.recorded_by is not null
                  and coalesce(d.updated_at, d.created_at) < now() - interval '15 minutes'
               returning d.id, d.recorded_by;
           end $$"""
    )
    op.execute("revoke execute on function maint_sweep_extractions() from public")
    op.execute("grant execute on function maint_sweep_extractions() to labtrack_maint")


def downgrade() -> None:
    op.execute("drop function maint_sweep_extractions()")
    op.execute("alter table lab_reports drop column analysed_at, drop column collected_precision")
    old = ", ".join(f"'{i}'" for i in _OLD)
    for table in ("lab_results", "extraction_runs"):
        # the rows stay; only the newer issue codes are dropped from them
        op.execute(
            f"update {table} set issues = array(select i from unnest(issues) i"
            f" where i = any(array[{old}]::text[]))"
            f" where not (issues <@ array[{old}]::text[])"
        )
    _issue_checks(_OLD)
