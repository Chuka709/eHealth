"""Whose sample time a report shows (Q65, physician 2026-11-25, B).

- lab_reports.collected_edited: set by the database (a trigger) the moment the sample's date or
  time is changed after the report was made - the person added or corrected it in the review
  (Q54: a time the lab did not print). Never set by the app, never cleared. Reports changed
  before this migration are found in the audit log (`report.edit` with the `collected_at`
  field - values are never audited, so a time sent unchanged counts too: the safe side).
- A typed-in report (`source = 'typed'`) has the person's date and time from the start.
- share_labs returns `collected_by_user` so the shared view can say so: a tacrolimus trough is
  read by its time (KDIGO, IATDMCT 2019), so a time the person entered is never shown as the
  lab's.

Revision ID: 0049
Revises: 0048
Create Date: 2026-11-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0049"
down_revision: str | None = "0048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEFINER = "security definer set search_path = pg_catalog, public, pg_temp"
_UB = "(({x}) at time zone 'Asia/Ulaanbaatar')::date"


def _share_labs(by_user: bool) -> str:
    extra_col = ", collected_by_user boolean" if by_user else ""
    extra_val = ", (r.source = 'typed' or r.collected_edited)" if by_user else ""
    return f"""
    create function share_labs(p_session_hash text)
    returns table (collected_at timestamptz, collected_precision text, lab_name text,
                   test_code text, test_name_mn text, test_name_en text, raw_name text,
                   raw_value text, raw_unit text, ref_text text, critical_text text,
                   flag text, lab_flag text{extra_col})
    language sql stable {_DEFINER} as $$
      select r.collected_at, r.collected_precision, r.lab_name, v.test_code, t.name_mn,
             t.name_en, v.raw_name, v.raw_value, v.raw_unit, v.ref_text, v.critical_text,
             v.flag::text, v.lab_flag{extra_val}
      from public.share_scope_of(p_session_hash, 'labs') k
      join public.lab_reports r on r.patient_id = k.patient_id and r.status = 'confirmed'
        and r.collected_at is not null
      join public.lab_results v on v.report_id = r.id and v.patient_id = r.patient_id
      left join public.test_catalog t on t.code = v.test_code
      where (k.date_from is null or {_UB.format(x="r.collected_at")} >= k.date_from)
        and (k.date_to is null or {_UB.format(x="r.collected_at")} <= k.date_to)
      order by r.collected_at desc, r.id, v.position
      limit 3000
    $$
    """


def _replace_share_labs(by_user: bool) -> None:
    op.execute("drop function share_labs(text)")
    op.execute(_share_labs(by_user))
    op.execute("revoke execute on function share_labs(text) from public")
    op.execute("grant execute on function share_labs(text) to labtrack_app")


def upgrade() -> None:
    op.execute("alter table lab_reports add column collected_edited boolean not null default false")
    # before the trigger exists (it would keep the old value): what was changed until now
    op.execute(
        "update lab_reports set collected_edited = true where id::text in"
        " (select entity_id from audit_logs where entity = 'lab_report'"
        " and diff -> 'fields' ? 'collected_at')"
    )
    op.execute(
        """
        create function lab_reports_collected_edited() returns trigger
        language plpgsql set search_path = pg_catalog, public, pg_temp as $$
        begin
          if tg_op = 'INSERT' then
            new.collected_edited := false;  -- a new report is as read or typed (source says)
          elsif new.collected_at is distinct from old.collected_at
             or new.collected_precision is distinct from old.collected_precision then
            new.collected_edited := true;
          else
            new.collected_edited := old.collected_edited;  -- never cleared by an update
          end if;
          return new;
        end $$
        """
    )
    op.execute(
        "create trigger lab_reports_collected_edited before insert or update on lab_reports"
        " for each row execute function lab_reports_collected_edited()"
    )
    _replace_share_labs(by_user=True)


def downgrade() -> None:
    _replace_share_labs(by_user=False)
    op.execute("drop trigger lab_reports_collected_edited on lab_reports")
    op.execute("drop function lab_reports_collected_edited()")
    op.execute("alter table lab_reports drop column collected_edited")
