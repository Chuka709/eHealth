"""A second "taken" record of one dose is kept, as a fact (Phase 2.8g; Q24; H20).

One planned dose keeps one row (medication_intakes): the earliest "taken" wins the merge
(H20). Until now a second "taken" - another person, another time - was lost, so a possible
second dose never showed. Decision Q24 (user, 2026-11-11): warn before recording, and keep it:

- medication_intake_extra: who (set by the database) and when, for a dose already taken.
  Append-only, read by whoever can read the profile, written by whoever can write it; at most
  10 per dose. Shown as a fact only - no threshold, no "double dose" judgement (rule 10b).
- intake_recorder_role(intake) / extra_recorder_role(extra): "you" / "owner" / "caregiver"
  for the row's writer, on a profile the caller can read - never a name (a caregiver does not
  learn the others' names - 2.8d), and never for an arbitrary user id (no oracle).
- a dose that others logged too cannot be undone (their records would go with it);
  cascades (a medicine or profile deleted) are not undos.

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-11
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEFINER = "security definer set search_path = pg_catalog, public, pg_temp"
MAX_PER_DOSE = 10

_TABLE = """
create table medication_intake_extra (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references patients on delete cascade,
  intake_id uuid not null references medication_intakes on delete cascade,
  status text not null check (status in ('taken', 'late')),
  taken_at timestamptz not null check (taken_at >= timestamptz '2000-01-01 00:00Z'),
  recorded_by uuid references users on delete set null,
  created_at timestamptz not null default now(),
  unique (intake_id, recorded_by, taken_at)
)
"""

_RULES = f"""
create function medication_intake_extra_rules() returns trigger language plpgsql
set search_path = pg_catalog, public, pg_temp as $$
begin
  -- the writer is whoever acts (the app or a definer function for the user), never the caller
  if public.app_user_id() is not null or current_user = 'labtrack_app' then
    new.recorded_by := public.app_user_id();
  end if;
  -- one writer per dose at a time, so the cap below holds under concurrent requests
  perform pg_advisory_xact_lock(hashtextextended(new.intake_id::text, 27));
  -- the row belongs to the same profile as its dose
  if not exists (select 1 from public.medication_intakes i
                 where i.id = new.intake_id and i.patient_id = new.patient_id) then
    raise exception 'not this profile''s dose' using errcode = '42501';
  end if;
  if (select count(*) from public.medication_intake_extra x
      where x.intake_id = new.intake_id) >= {MAX_PER_DOSE} then
    raise exception 'too many records of one dose' using errcode = '54000';
  end if;
  return new;
end $$
"""

_ROLE_OF = """
  select case
    when not public.can_read_patient({p}) or {u} is null then null
    when {u} = public.app_user_id() then 'you'
    when exists (select 1 from public.patient_access a
                 where a.patient_id = {p} and a.user_id = {u} and a.level = 'owner')
      then 'owner'
    else 'caregiver'
  end"""
_ROLES = [
    f"""
    create function intake_recorder_role(p_intake uuid) returns text
    language sql stable {_DEFINER} as $$
      {_ROLE_OF.format(p="i.patient_id", u="coalesce(i.taken_by, i.recorded_by)")}
      from public.medication_intakes i where i.id = p_intake
    $$
    """,
    f"""
    create function extra_recorder_role(p_extra uuid) returns text
    language sql stable {_DEFINER} as $$
      {_ROLE_OF.format(p="x.patient_id", u="x.recorded_by")}
      from public.medication_intake_extra x where x.id = p_extra
    $$
    """,
]

# undoing a dose that others logged too would erase their records: refused (2.8g review);
# deletions that cascade (a medicine, a profile, a purge) are not undos and still go through
_NO_UNDO = """
create function medication_intakes_keep_extra() returns trigger language plpgsql
set search_path = pg_catalog, public, pg_temp as $$
begin
  if current_user = 'labtrack_app' and pg_trigger_depth() = 1
     and exists (select 1 from public.medication_intake_extra x where x.intake_id = old.id) then
    raise exception 'others logged this dose too' using errcode = '42501',
      hint = 'intake_has_extra';
  end if;
  return old;
end $$
"""


def upgrade() -> None:
    op.execute(_TABLE)
    op.execute("create index on medication_intake_extra (intake_id)")
    op.execute("alter table medication_intake_extra enable row level security")
    op.execute("alter table medication_intake_extra force row level security")
    op.execute(
        "create policy medication_intake_extra_owner on medication_intake_extra"
        " for all to labtrack_owner using (true) with check (true)"
    )
    op.execute(
        """create policy medication_intake_extra_select on medication_intake_extra
           for select to labtrack_app using (can_read_patient(patient_id))"""
    )
    op.execute(
        """create policy medication_intake_extra_insert on medication_intake_extra
           for insert to labtrack_app with check (can_write_patient(patient_id))"""
    )
    # one's own extra record can be undone ("Буцаах"); nobody else's
    op.execute(
        """create policy medication_intake_extra_delete on medication_intake_extra
           for delete to labtrack_app
           using (recorded_by = app_user_id() and can_write_patient(patient_id))"""
    )
    op.execute("revoke truncate on medication_intake_extra from public")
    op.execute("grant select, delete on medication_intake_extra to labtrack_app")
    op.execute(
        "grant insert (patient_id, intake_id, status, taken_at) on medication_intake_extra"
        " to labtrack_app"
    )
    op.execute(_RULES)
    op.execute(
        """create trigger medication_intake_extra_rules before insert on medication_intake_extra
           for each row execute function medication_intake_extra_rules()"""
    )
    for sql in _ROLES:
        op.execute(sql)
    op.execute(_NO_UNDO)
    op.execute(
        """create trigger medication_intakes_keep_extra before delete on medication_intakes
           for each row execute function medication_intakes_keep_extra()"""
    )
    for fn in (
        "intake_recorder_role(uuid)",
        "extra_recorder_role(uuid)",
        "medication_intake_extra_rules()",
        "medication_intakes_keep_extra()",
    ):
        op.execute(f"revoke execute on function {fn} from public")
    op.execute(
        "grant execute on function intake_recorder_role(uuid), extra_recorder_role(uuid)"
        " to labtrack_app"
    )


def downgrade() -> None:
    op.execute("drop trigger medication_intakes_keep_extra on medication_intakes")
    op.execute("drop function medication_intakes_keep_extra()")
    op.execute("drop function extra_recorder_role(uuid)")
    op.execute("drop function intake_recorder_role(uuid)")
    op.execute("drop table medication_intake_extra")
    op.execute("drop function medication_intake_extra_rules()")
