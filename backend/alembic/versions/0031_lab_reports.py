"""Lab reports read from documents: runs, reports, results (Phase 4.1; docs/03, 05).

- `extraction_runs`: one row per attempt to read a document - by the local text parser or by
  the AI (Q50) - with what read it and how long it took. Append-only for the app (the worker
  inserts in the uploader's context); `raw_output` is the reader's own output (PHI), kept
  without the printed identity (the worker strips it) and capped in size.
- `lab_reports` / `lab_results`: drafts (rule 4) - always inserted as `needs_review`; status,
  confirmation and later edits come with the review screen (Phase 5), so the app may not set
  or change them here. A result's patient is its report's, and a report's document and run are
  the profile's own (composite FKs - no row of another profile can be linked).
- Who sees what: the profile's writers (owner, caregiver) see drafts and runs; readers
  (doctor, viewer) see only confirmed reports and their results - an unchecked draft never
  reaches anyone else. Results are added only to one's own draft report; a recorder deletes
  only their own draft, the owner any report; a result's date is its report's.
- Ranges and critical limits only as written on the document (rule 5); numbers are `numeric`
  (rule 7). The person's name as printed is not kept, only how well it matched the profile
  (`name_match_score`, data minimisation).
- Deleting a document keeps its reports (document_id set null) and drops its runs - also when
  a caregiver deletes the document they uploaded (0029), the one way runs go without the owner.

Revision ID: 0031
Revises: 0030
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ISSUES = (
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
_ISSUE_LIST = ", ".join(f"'{i}'" for i in ISSUES)

_RUN_INSERT = (
    "id, patient_id, document_id, method, reader, prompt_version, pipeline_version,"
    " input_tokens, output_tokens, cost_usd, duration_ms, raw_output, issues, error_code"
)
_REPORT_INSERT = (
    "id, patient_id, document_id, extraction_run_id, lab_name, panel_name, specimen,"
    " collected_at, reported_at, date_ambiguous, name_match_score, has_unconfirmed_critical"
)
_RESULT_INSERT = (
    "id, report_id, patient_id, position, test_code, raw_name, raw_value, raw_unit,"
    " value_numeric, comparator, value_text, qualitative, ref_text, ref_low, ref_high,"
    " critical_text, critical_low, critical_high, lab_flag, unit_canonical, value_canonical,"
    " ref_low_canonical, ref_high_canonical, critical_low_canonical, critical_high_canonical,"
    " flag, flag_source, flag_mismatch, confidence, issues, source_page, source_snippet"
)
_RESULT_READ = """can_read_patient(patient_id) and exists (select 1 from lab_reports r
                   where r.id = report_id and r.status = 'confirmed')"""
_RESULT_ADD = """exists (select 1 from lab_reports r
                  where r.id = report_id and r.patient_id = lab_results.patient_id
                    and r.status = 'needs_review' and r.recorded_by = app_user_id())"""


def _rls(table: str, *, read: str, insert: str, delete: str) -> None:
    """Writers of the profile see every row; `read` adds what readers see."""
    op.execute(f"alter table {table} enable row level security")
    op.execute(f"alter table {table} force row level security")
    op.execute(
        f"create policy {table}_owner on {table} for all to labtrack_owner"
        " using (true) with check (true)"
    )
    op.execute(
        f"""create policy {table}_select on {table} for select to labtrack_app
           using (can_write_patient(patient_id) or ({read}))"""
    )
    op.execute(
        f"""create policy {table}_insert on {table} for insert to labtrack_app
           with check (can_write_patient(patient_id) and {insert})"""
    )
    op.execute(
        f"""create policy {table}_delete on {table} for delete to labtrack_app
           using (can_write_patient(patient_id) and {delete})"""
    )
    op.execute(f"revoke truncate on {table} from public")


def upgrade() -> None:
    op.execute("create type report_status as enum ('needs_review', 'confirmed', 'rejected')")
    op.execute(
        """create type result_flag as enum ('normal', 'low', 'high', 'critical_low',
           'critical_high', 'abnormal', 'no_reference', 'unknown')"""
    )
    op.execute(
        f"""
        create table extraction_runs (
          id uuid primary key default gen_random_uuid(),
          patient_id uuid not null references patients on delete cascade,
          document_id uuid not null,
          method text not null check (method in ('local', 'ai')),
          reader text not null check (reader ~ '^[a-z0-9._:-]{{1,80}}$'),
          prompt_version text check (prompt_version ~ '^[a-z0-9._-]{{1,40}}$'),
          pipeline_version text not null check (pipeline_version ~ '^[a-z0-9._-]{{1,40}}$'),
          input_tokens int check (input_tokens >= 0),
          output_tokens int check (output_tokens >= 0),
          cost_usd numeric(10, 5) check (cost_usd >= 0),
          duration_ms int check (duration_ms >= 0),
          raw_output jsonb check (pg_column_size(raw_output) <= 262144),
          issues text[] not null default '{{}}' check (issues <@ array[{_ISSUE_LIST}]::text[]),
          error_code text check (error_code ~ '^[a-z_]{{1,40}}$'),
          recorded_by uuid references users on delete set null,
          created_at timestamptz not null default now(),
          unique (id, patient_id),
          foreign key (document_id, patient_id) references documents (id, patient_id)
            on delete cascade
        )
        """
    )
    op.execute("create index on extraction_runs (document_id, created_at desc)")
    op.execute("create index on extraction_runs (patient_id, created_at desc)")
    _rls("extraction_runs", read="false", insert="true", delete="is_owner(patient_id)")
    op.execute("grant select, delete on extraction_runs to labtrack_app")
    op.execute(f"grant insert ({_RUN_INSERT}) on extraction_runs to labtrack_app")
    op.execute(
        """create trigger extraction_runs_writer before insert on extraction_runs
           for each row execute function set_row_writer()"""
    )

    op.execute(
        """
        create table lab_reports (
          id uuid primary key default gen_random_uuid(),
          patient_id uuid not null references patients on delete cascade,
          document_id uuid,
          extraction_run_id uuid,
          lab_name text check (length(lab_name) <= 200),
          panel_name text check (length(panel_name) <= 200),
          specimen text check (length(specimen) <= 100),
          collected_at timestamptz,
          reported_at timestamptz,
          date_ambiguous boolean not null default false,
          name_match_score numeric(3, 2) check (name_match_score between 0 and 1),
          has_unconfirmed_critical boolean not null default false,
          status report_status not null default 'needs_review',
          confirmed_by uuid references users on delete set null,
          confirmed_at timestamptz,
          recorded_by uuid references users on delete set null,
          updated_by uuid references users on delete set null,
          created_at timestamptz not null default now(),
          updated_at timestamptz,
          unique (id, patient_id),
          check ((status = 'confirmed') = (confirmed_at is not null)),
          check (status = 'confirmed' or confirmed_by is null),
          foreign key (document_id, patient_id) references documents (id, patient_id)
            on delete set null (document_id),
          foreign key (extraction_run_id, patient_id) references extraction_runs (id, patient_id)
            on delete set null (extraction_run_id)
        )
        """
    )
    op.execute("create index on lab_reports (patient_id, collected_at desc)")
    op.execute("create index on lab_reports (document_id)")
    _rls(
        "lab_reports",
        read="can_read_patient(patient_id) and status = 'confirmed'",
        insert="true",
        delete=(
            "(is_owner(patient_id) or (recorded_by = app_user_id() and status = 'needs_review'))"
        ),
    )
    op.execute("grant select, delete on lab_reports to labtrack_app")
    op.execute(f"grant insert ({_REPORT_INSERT}) on lab_reports to labtrack_app")
    op.execute(
        """create trigger lab_reports_writer before insert or update on lab_reports
           for each row execute function set_row_writer()"""
    )
    op.execute(
        """create trigger lab_reports_touch before update on lab_reports
           for each row execute function touch_updated_at()"""
    )

    op.execute(
        f"""
        create table lab_results (
          id uuid primary key default gen_random_uuid(),
          report_id uuid not null,
          patient_id uuid not null references patients on delete cascade,
          position int not null check (position between 0 and 499),
          test_code text references test_catalog,
          raw_name text not null check (length(raw_name) between 1 and 200),
          raw_value text not null check (length(raw_value) between 1 and 200),
          raw_unit text check (length(raw_unit) <= 50),
          value_numeric numeric,
          comparator text check (comparator in ('<', '<=', '>', '>=')),
          value_text text check (length(value_text) <= 200),
          qualitative text check (qualitative in ('positive', 'negative', 'equivocal')),
          ref_text text check (length(ref_text) <= 300),
          ref_low numeric, ref_high numeric,
          critical_text text check (length(critical_text) <= 300),
          critical_low numeric, critical_high numeric,
          lab_flag text check (length(lab_flag) <= 10),
          unit_canonical text check (length(unit_canonical) <= 50),
          value_canonical numeric,
          ref_low_canonical numeric, ref_high_canonical numeric,
          critical_low_canonical numeric, critical_high_canonical numeric,
          flag result_flag not null default 'unknown',
          flag_source text check (flag_source in
            ('computed_document_range', 'lab_flag', 'patient_target', 'none')),
          flag_mismatch boolean not null default false,
          confidence numeric(3, 2) check (confidence between 0 and 1),
          issues text[] not null default '{{}}' check (issues <@ array[{_ISSUE_LIST}]::text[]),
          source_page int check (source_page between 1 and 50),
          source_snippet text check (length(source_snippet) <= 500),
          edited_by_user boolean not null default false,
          collected_at timestamptz,
          recorded_by uuid references users on delete set null,
          created_at timestamptz not null default now(),
          unique (report_id, position),
          check (ref_low is null or ref_high is null or ref_low <= ref_high),
          check (critical_low is null or critical_high is null or critical_low <= critical_high),
          check (comparator is null or value_numeric is not null),
          check (flag not in ('normal', 'low', 'high') or ref_low is not null
                 or ref_high is not null or flag_source in ('lab_flag', 'patient_target')),
          check (flag_source is distinct from 'none' or flag in ('no_reference', 'unknown')),
          foreign key (report_id, patient_id) references lab_reports (id, patient_id)
            on delete cascade
        )
        """
    )
    op.execute("create index on lab_results (patient_id, test_code, collected_at desc)")
    # results go with their report (cascade); none is deleted alone until review (Phase 5)
    _rls("lab_results", read=_RESULT_READ, insert=_RESULT_ADD, delete="false")
    op.execute("grant select on lab_results to labtrack_app")
    op.execute(f"grant insert ({_RESULT_INSERT}) on lab_results to labtrack_app")
    op.execute(
        """create trigger lab_results_writer before insert on lab_results
           for each row execute function set_row_writer()"""
    )
    # a result's date is its report's (the trend index), never set apart from it
    op.execute(
        """create function lab_results_collected_at() returns trigger language plpgsql
           set search_path = pg_catalog, public, pg_temp as $$
           begin
             select r.collected_at into new.collected_at from public.lab_reports r
               where r.id = new.report_id;
             return new;
           end $$"""
    )
    op.execute("revoke execute on function lab_results_collected_at() from public")
    op.execute("grant execute on function lab_results_collected_at() to labtrack_app")
    op.execute(
        """create trigger lab_results_collected_at before insert on lab_results
           for each row execute function lab_results_collected_at()"""
    )


def downgrade() -> None:
    op.execute("drop table lab_results")
    op.execute("drop function lab_results_collected_at()")
    op.execute("drop table lab_reports")
    op.execute("drop table extraction_runs")
    op.execute("drop type result_flag")
    op.execute("drop type report_status")
