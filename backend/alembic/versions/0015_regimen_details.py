"""Dose per time of day, voiding a mistaken future dose, course end, dose units (Phase 2.2
medical review; hazard H8; user decisions 2026-11-04).

- A schedule's times carry their own amount: tacrolimus 2 mg at 08:00 and 1.5 mg at 20:00 is
  one regimen, `{"type": "daily", "times": [{"at": "08:00", "amount": "2"}, {"at": "20:00",
  "amount": "1.5"}]}`. Amounts are exact decimal strings (never floats). `dose_amount` stays
  for as-needed (prn) doses only. Existing rows move their single amount onto every time.
- A future regimen entered by mistake can be voided (once, with a reason; who and when are
  the database's). The row stays - the history is still append-only - and a voided row is
  never the dose in force. Only rows that have not started yet: a past dose is history.
- `planned_end_on`: a course's planned last day (valganciclovir, co-trimoxazole, a taper);
  reminders stop after it.
- `dose_unit` is a code from a fixed list (mg / mcg ... one spelling each: no µg vs мкг mix-up
  that is a 1000-fold error); anything else is 'other' with the user's text.
- Intakes: `scheduled_at` is a whole minute (the schedule is HH:MM), so two devices' records of
  one dose always meet on the same key (H20).

Downgrade is lossy by nature (0014 has one amount per regimen): every time gets the first
time's amount, and a voided row looks like any other. It exists for development only.

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-04
"""

import os
from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UNITS = (
    "mg",
    "mcg",
    "g",
    "ml",
    "iu",
    "unit",
    "tablet",
    "capsule",
    "drop",
    "puff",
    "sachet",
    "patch",
    "other",
)
_UNITS_SQL = ", ".join(f"'{u}'" for u in UNITS)
_AMOUNT = r"^[0-9]{1,5}(\.[0-9]{1,4})?$"

_SCHEDULE_OK = rf"""
create function regimen_schedule_ok(s jsonb) returns boolean language sql immutable
set search_path = pg_catalog, public, pg_temp as $$
  -- coalesce: a missing key gives NULL, and a NULL check would pass
  select coalesce(jsonb_typeof(s) = 'object' and pg_column_size(s) <= 2000 and case
    when s->>'type' = 'prn' then s = '{{"type": "prn"}}'::jsonb
    when s->>'type' in ('daily', 'weekly') then
      (s - 'type' - 'times' - 'days') = '{{}}'::jsonb
      and (s->>'type' = 'weekly' or not s ? 'days')
      and jsonb_typeof(s->'times') = 'array'
      and jsonb_array_length(s->'times') between 1 and 12
      and not exists (
        select 1 from jsonb_array_elements(s->'times') t
        where jsonb_typeof(t) <> 'object'
           or case when jsonb_typeof(t) = 'object'
                   then (t - 'at' - 'amount') <> '{{}}'::jsonb else true end
           or coalesce(t->>'at', '') !~ '^([01][0-9]|2[0-3]):[0-5][0-9]$'
           -- (a CASE: SQL does not short-circuit OR, the cast must see a number)
           or (t ? 'amount' and case when coalesce(t->>'amount', '') ~ '{_AMOUNT}'
                                     then (t->>'amount')::numeric <= 0 else true end))
      -- amounts on every time or on none; each time once
      and (select count(*) filter (where t ? 'amount') in (0, count(*))
                  and count(distinct t->>'at') = count(*)
           from jsonb_array_elements(s->'times') t)
      and (s->>'type' = 'daily'
           or (jsonb_typeof(s->'days') = 'array'
               and jsonb_array_length(s->'days') between 1 and 7
               and not exists (select 1 from jsonb_array_elements(s->'days') d
                               where jsonb_typeof(d) <> 'number'
                                  or d::text !~ '^[1-7]$')
               and (select count(distinct d) = count(*)
                    from jsonb_array_elements(s->'days') d)))
    else false
  end, false)
$$
"""

_OLD_SCHEDULE_CHECK = "medication_regimens_schedule_check"

_VOID_ONCE = """
create function medication_regimens_void_once() returns trigger language plpgsql
set search_path = pg_catalog, public, pg_temp as $$
begin
  -- a deleted user's FK set null (voided_by / recorded_by) - nothing else
  if (to_jsonb(new) - '{voided_by,recorded_by}'::text[])
       = (to_jsonb(old) - '{voided_by,recorded_by}'::text[])
     and (new.voided_by is null or new.voided_by is not distinct from old.voided_by)
     and (new.recorded_by is null or new.recorded_by is not distinct from old.recorded_by) then
    return new;
  end if;
  -- only the void columns ever change (for every role, not only through the grants)
  if (to_jsonb(new) - '{voided_at,void_reason,voided_by}'::text[])
       <> (to_jsonb(old) - '{voided_at,void_reason,voided_by}'::text[]) then
    raise exception 'only voiding is allowed' using errcode = '23514';
  end if;
  if old.voided_at is not null then
    raise exception 'a voided dose stays voided' using errcode = '23514';
  end if;
  if new.voided_at is null then
    raise exception 'only voiding is allowed' using errcode = '23514';
  end if;
  if old.effective_from <= public.local_today() then
    raise exception 'a started dose is history' using errcode = '23514';
  end if;
  new.voided_at := now();
  new.voided_by := public.app_user_id();
  return new;
end $$
"""


def upgrade() -> None:
    op.execute(_SCHEDULE_OK)
    op.execute("revoke execute on function regimen_schedule_ok(jsonb) from public")
    op.execute("grant execute on function regimen_schedule_ok(jsonb) to labtrack_app")
    op.execute(f"alter table medication_regimens drop constraint {_OLD_SCHEDULE_CHECK}")
    op.execute("alter table medication_regimens drop constraint medication_regimens_check")
    # every time gets the old single amount; the column keeps only prn amounts
    op.execute(
        """update medication_regimens set
             schedule = jsonb_set(schedule, '{times}', (
               select jsonb_agg(case when dose_amount is null then jsonb_build_object('at', t)
                                     else jsonb_build_object('at', t, 'amount',
                                                             dose_amount::text) end
                                order by t)
               from jsonb_array_elements_text(schedule->'times') t)),
             dose_amount = null
           where schedule->>'type' in ('daily', 'weekly')"""
    )
    op.execute(
        "alter table medication_regimens add constraint medication_regimens_schedule_check"
        " check (regimen_schedule_ok(schedule))"
    )
    op.execute(
        """alter table medication_regimens
             add column dose_unit_text short_text,
             add column voided_at timestamptz,
             add column void_reason short_text,
             add column voided_by uuid references users on delete set null"""
    )
    op.execute(
        f"""update medication_regimens set
              dose_unit = case
                when lower(btrim(dose_unit)) in ({_UNITS_SQL}) then lower(btrim(dose_unit))
                when lower(btrim(dose_unit)) in ('мг') then 'mg'
                when lower(btrim(dose_unit)) in ('мкг', 'µg', 'μg', 'ug') then 'mcg'
                when lower(btrim(dose_unit)) in ('мл') then 'ml'
                else 'other' end,
              dose_unit_text = case
                when lower(btrim(dose_unit))
                     in ({_UNITS_SQL}, 'мг', 'мкг', 'µg', 'μg', 'ug', 'мл') then null
                else dose_unit end
           where dose_unit is not null"""
    )
    op.execute(
        f"""alter table medication_regimens
              add constraint medication_regimens_unit_check
                check (dose_unit is null or dose_unit in ({_UNITS_SQL})),
              add constraint medication_regimens_unit_text_check
                check ((dose_unit = 'other') = (dose_unit_text is not null)),
              add constraint medication_regimens_prn_amount_check
                check (dose_amount is null or schedule->>'type' = 'prn'),
              -- a unit exactly when there is an amount (prn column, or amounts on the times)
              add constraint medication_regimens_unit_amount_check
                check ((dose_unit is null) = (dose_amount is null
                    and not coalesce(schedule->'times'->0 ? 'amount', false))),
              add constraint medication_regimens_void_check
                check ((voided_at is null) = (void_reason is null))"""
    )
    op.execute(_VOID_ONCE)
    op.execute("revoke execute on function medication_regimens_void_once() from public")
    op.execute(
        """create trigger medication_regimens_void before update on medication_regimens
           for each row execute function medication_regimens_void_once()"""
    )
    op.execute("grant insert (dose_unit_text) on medication_regimens to labtrack_app")
    op.execute("grant update (voided_at, void_reason) on medication_regimens to labtrack_app")
    op.execute(
        """create policy medication_regimens_update on medication_regimens for update
           to labtrack_app using (can_write_patient(patient_id))
           with check (can_write_patient(patient_id))"""
    )

    op.execute("alter table medications add column planned_end_on date")
    op.execute(
        """alter table medications add constraint medications_planned_end_check
           check (planned_end_on is null or started_on is null or planned_end_on >= started_on)"""
    )
    op.execute(
        "grant insert (planned_end_on), update (planned_end_on) on medications to labtrack_app"
    )

    op.execute(
        """do $$ begin
             if exists (select 1 from medication_intakes where scheduled_at is not null
                        group by patient_id, medication_id, date_trunc('minute', scheduled_at)
                        having count(*) > 1) then
               raise exception '0015: intakes of one dose seconds apart - merge them first';
             end if;
           end $$"""
    )
    op.execute(
        """update medication_intakes set scheduled_at = date_trunc('minute', scheduled_at)
           where scheduled_at is not null"""
    )
    op.execute(
        """alter table medication_intakes add constraint medication_intakes_minute_check
           check (scheduled_at is null
                  or mod(extract(epoch from scheduled_at)::numeric, 60) = 0)"""
    )


def downgrade() -> None:
    # Voided rows would come back into force and per-time doses would collapse: outside
    # dev/test (disposable data; the test run migrates up, down and up), refuse.
    if os.environ.get("ENVIRONMENT") not in {"dev", "test"}:
        op.execute(
            """do $$ begin
                 if exists (select 1 from medication_regimens where voided_at is not null
                            or (select count(distinct t->>'amount')
                                from jsonb_array_elements(case when schedule ? 'times'
                                     then schedule->'times' else '[]'::jsonb end) t) > 1)
                 then
                   raise exception '0015 downgrade would lose voided or per-time doses';
                 end if;
               end $$"""
        )
    op.execute("alter table medication_intakes drop constraint medication_intakes_minute_check")
    op.execute(
        "revoke insert (planned_end_on), update (planned_end_on) on medications from labtrack_app"
    )
    op.execute("alter table medications drop column planned_end_on")
    op.execute("drop policy medication_regimens_update on medication_regimens")
    op.execute("revoke update (voided_at, void_reason) on medication_regimens from labtrack_app")
    op.execute("drop trigger medication_regimens_void on medication_regimens")
    op.execute("drop function medication_regimens_void_once()")
    for name in (
        "unit_check",
        "unit_text_check",
        "prn_amount_check",
        "unit_amount_check",
        "void_check",
        "schedule_check",
    ):
        op.execute(f"alter table medication_regimens drop constraint medication_regimens_{name}")
    # back to one amount per regimen (the first time's) and times as strings
    op.execute(
        """update medication_regimens set
             dose_amount = coalesce(dose_amount, (schedule->'times'->0->>'amount')::numeric),
             schedule = jsonb_set(schedule, '{times}', (
               select jsonb_agg(t->>'at' order by t->>'at')
               from jsonb_array_elements(schedule->'times') t))
           where schedule->>'type' in ('daily', 'weekly')"""
    )
    op.execute(
        """update medication_regimens set dose_unit = coalesce(dose_unit_text, dose_unit)
           where dose_unit is not null"""
    )
    op.execute(
        """alter table medication_regimens drop column voided_by, drop column void_reason,
             drop column voided_at, drop column dose_unit_text"""
    )
    op.execute(
        """alter table medication_regimens
             add constraint medication_regimens_check
               check ((dose_amount is null) = (dose_unit is null)),
             add constraint medication_regimens_schedule_check
               check (jsonb_typeof(schedule) = 'object'
                      and pg_column_size(schedule) <= 2000
                      and coalesce(schedule->>'type' = 'prn'
                           or (schedule->>'type' in ('daily','weekly')
                               and jsonb_typeof(schedule->'times') = 'array'
                               and jsonb_array_length(schedule->'times') between 1 and 12),
                           false)
                      and coalesce(schedule->>'type' <> 'weekly'
                           or (jsonb_typeof(schedule->'days') = 'array'
                               and jsonb_array_length(schedule->'days') between 1 and 7),
                           false))"""
    )
    op.execute("drop function regimen_schedule_ok(jsonb)")
