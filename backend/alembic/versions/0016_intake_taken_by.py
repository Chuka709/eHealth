"""Who marked a dose taken decides who may undo it (push security review of 0014; H20).

0014 let a taken dose be deleted by whoever FIRST wrote the row (recorded_by). When a
caregiver's phone recorded "skipped" and the patient's own phone then merged it into "taken",
the caregiver - the row's first writer - could still delete the patient's "taken". Now
`taken_by` (set by the database when a row becomes taken or late, never by the caller) is
what counts: a taken dose is deleted only by whoever marked it taken, or by the profile's
owner. A skipped record stays deletable by any writer.

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-04
"""

import importlib.util
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _revision(filename: str) -> ModuleType:
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_SET_ROW_WRITER = """
create or replace function set_row_writer() returns trigger language plpgsql
set search_path = pg_catalog, public, pg_temp as $$
begin
  -- not for the database's own updates (a purged user's FK set null runs this at depth 2)
  if pg_trigger_depth() > 1 then
    return new;
  end if;
  if public.app_user_id() is not null or current_user = 'labtrack_app' then
    if tg_op = 'INSERT' then
      new.recorded_by := public.app_user_id();
      if tg_table_name = 'medication_intakes' then
        new.taken_by := case when new.status <> 'skipped' then public.app_user_id() end;
      end if;
    else
      new.recorded_by := old.recorded_by;
      new.updated_by := public.app_user_id();
      if tg_table_name = 'medication_intakes' then
        -- the user whose record made the dose taken; kept once taken (taken never reverts)
        new.taken_by := case
          when old.status = 'skipped' and new.status <> 'skipped' then public.app_user_id()
          else old.taken_by end;
      end if;
    end if;
  end if;
  return new;
end $$
"""

_DELETE_POLICY = """
create policy medication_intakes_delete on medication_intakes for delete to labtrack_app
using (can_write_patient(patient_id) and (status = 'skipped'
       or taken_by = app_user_id() or is_owner(patient_id)))
"""


def _old_writer() -> str:
    m14 = _revision("0014_transplants_medications.py")
    (sql,) = [s for s in m14._FUNCTIONS if "create function set_row_writer(" in s]
    return str(sql).replace("create function", "create or replace function", 1)


def upgrade() -> None:
    op.execute(
        "alter table medication_intakes add column taken_by uuid references users"
        " on delete set null"
    )
    # existing taken rows: the first writer marked them taken only if nobody changed the row
    # since; otherwise who did is unknown, and only the owner may delete (taken_by null)
    op.execute(
        "update medication_intakes set taken_by = case"
        " when updated_by is null or updated_by = recorded_by then recorded_by end"
        " where status <> 'skipped'"
    )
    op.execute(_SET_ROW_WRITER)
    op.execute("drop policy medication_intakes_delete on medication_intakes")
    op.execute(_DELETE_POLICY)


def downgrade() -> None:
    op.execute("drop policy medication_intakes_delete on medication_intakes")
    op.execute(
        """create policy medication_intakes_delete on medication_intakes for delete
           to labtrack_app using (can_write_patient(patient_id) and (status = 'skipped'
           or recorded_by = app_user_id() or is_owner(patient_id)))"""
    )
    op.execute(_old_writer())
    op.execute("alter table medication_intakes drop column taken_by")
