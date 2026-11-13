"""Home dashboard: the latest confirmed value of each test, and the cards a profile keeps
(Phase 6.1; docs/06 §1, docs/03 "latest_results").

- `latest_results`: a plain view, NOT a materialized one - a materialized view holds its rows
  as its owner read them and so would bypass row level security. `security_invoker` makes the
  caller's RLS on `lab_results`/`lab_reports` apply; the (patient_id, test_code, collected_at
  desc) index keeps it fast. Only results of CONFIRMED reports with a catalog test and a date
  (rule 4: a draft never reaches the dashboard - writers see drafts in `lab_results`, so the
  view filters them itself). Ties on the same moment: the later-confirmed report, then id.
- `dashboard_cards`: one row per profile - the test cards its writers pinned, in order. No row
  = the cards for the organ (core, Phase 6.2); an empty list = the person chose none. Only the
  profile's writers see or change it (a reader's view is Phase 7). The database checks the
  codes (a catalog test, active when newly added; no repeat; at most 24) and records who wrote it.

Revision ID: 0038
Revises: 0037
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MAX_CARDS = 24

_VIEW = """
create view latest_results with (security_invoker = true, security_barrier = true) as
select distinct on (lr.patient_id, lr.test_code)
  lr.id, lr.patient_id, lr.report_id, lr.test_code, lr.collected_at,
  lr.raw_value, lr.raw_unit, lr.comparator, lr.value_text, lr.qualitative,
  lr.unit_canonical, lr.value_canonical, lr.ref_text,
  lr.ref_low_canonical, lr.ref_high_canonical,
  lr.critical_low_canonical, lr.critical_high_canonical,
  lr.flag, lr.flag_source
from lab_results lr
join lab_reports r on r.id = lr.report_id and r.patient_id = lr.patient_id
where r.status = 'confirmed' and lr.test_code is not null and lr.collected_at is not null
order by lr.patient_id, lr.test_code, lr.collected_at desc, r.confirmed_at desc nulls last,
  lr.id desc
"""

_TABLE = """
create table dashboard_cards (
  patient_id uuid primary key references patients on delete cascade,
  test_codes text[] not null default '{}',
  recorded_by uuid references users on delete set null,
  updated_by uuid references users on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz
)
"""

_CHECK = f"""
create function dashboard_cards_check() returns trigger language plpgsql
set search_path = pg_catalog, public, pg_temp as $$
declare
  kept text[] := '{{}}';
begin
  if tg_op = 'UPDATE' then
    kept := old.test_codes;  -- a test retired from the catalog does not block other changes
  end if;
  if new.test_codes is null or cardinality(new.test_codes) > {MAX_CARDS}
     or array_position(new.test_codes, null) is not null then
    raise exception 'dashboard_cards: bad list' using errcode = '23514';
  end if;
  if (select count(distinct c) from unnest(new.test_codes) c) <> cardinality(new.test_codes)
  then
    raise exception 'dashboard_cards: repeated test' using errcode = '23514';
  end if;
  if exists (select 1 from unnest(new.test_codes) c
             where not exists (select 1 from public.test_catalog t
                               where t.code = c and (t.is_active or c = any(kept)))) then
    raise exception 'dashboard_cards: unknown test' using errcode = '23503';
  end if;
  return new;
end $$
"""

_WRITE = "can_write_patient(patient_id)"


def upgrade() -> None:
    op.execute(_VIEW)
    op.execute("revoke all on latest_results from public")
    op.execute("grant select on latest_results to labtrack_app")

    op.execute(_TABLE)
    op.execute("alter table dashboard_cards enable row level security")
    op.execute("alter table dashboard_cards force row level security")
    op.execute(
        "create policy dashboard_cards_owner on dashboard_cards for all to labtrack_owner"
        " using (true) with check (true)"
    )
    op.execute(
        f"create policy dashboard_cards_select on dashboard_cards for select to labtrack_app"
        f" using ({_WRITE})"
    )
    op.execute(
        f"create policy dashboard_cards_insert on dashboard_cards for insert to labtrack_app"
        f" with check ({_WRITE})"
    )
    op.execute(
        f"create policy dashboard_cards_update on dashboard_cards for update to labtrack_app"
        f" using ({_WRITE}) with check ({_WRITE})"
    )
    op.execute(
        f"create policy dashboard_cards_delete on dashboard_cards for delete to labtrack_app"
        f" using ({_WRITE})"
    )
    op.execute("grant select, delete on dashboard_cards to labtrack_app")
    op.execute("grant insert (patient_id, test_codes) on dashboard_cards to labtrack_app")
    op.execute("grant update (test_codes) on dashboard_cards to labtrack_app")
    op.execute("revoke truncate on dashboard_cards from public")

    op.execute(_CHECK)
    op.execute("revoke execute on function dashboard_cards_check() from public")
    op.execute(
        """create trigger dashboard_cards_check before insert or update on dashboard_cards
           for each row execute function dashboard_cards_check()"""
    )
    op.execute(
        """create trigger dashboard_cards_writer before insert or update on dashboard_cards
           for each row execute function set_row_writer()"""
    )
    op.execute(
        """create trigger dashboard_cards_touch before update on dashboard_cards
           for each row execute function touch_updated_at()"""
    )


def downgrade() -> None:
    op.execute("drop table dashboard_cards")
    op.execute("drop function dashboard_cards_check()")
    op.execute("drop view latest_results")
