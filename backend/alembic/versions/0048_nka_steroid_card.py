"""Confirmed "no known allergies" and the steroid emergency card mark (Q39, Q36; physician
2026-11-18, ★; hazards H17, H39).

- no_known_allergies: one dated statement per profile that the person confirmed they have no
  known allergy - unlike "none recorded" (FHIR: SNOMED 716186003 "No known allergy"). Written by
  whoever may record allergies, through functions; refused while an allergy is recorded, and
  removed by the database the moment one is added (the two can never be shown together).
- steroid_cards: a profile marked as needing a steroid emergency card (adrenal insufficiency
  after long steroid use). Marked by a treating doctor (shown the NHS 2020 threshold) or by the
  owner as their doctor told them; the app never infers it from the medicines (rule 10). Whose
  mark it is stays visible. Cleared by the owner or a treating doctor; audited by id only.

Revision ID: 0048
Revises: 0047
Create Date: 2026-11-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0048"
down_revision: str | None = "0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEFINER = "security definer set search_path = pg_catalog, public, pg_temp"

_TABLES = [
    """
    create table no_known_allergies (
      patient_id uuid primary key references patients on delete cascade,
      confirmed_on date not null,
      confirmed_by uuid references users on delete set null,
      created_at timestamptz not null default now()
    )
    """,
    """
    create table steroid_cards (
      patient_id uuid primary key references patients on delete cascade,
      marked_on date not null,
      marked_by uuid references users on delete set null,
      by_doctor boolean not null,
      created_at timestamptz not null default now()
    )
    """,
]

# one lock per profile for the statement and the allergies that end it
_NKA_LOCK = "perform pg_advisory_xact_lock(hashtextextended('nka:' || {p}::text, 0))"

_FUNCTIONS = [
    f"""
    create function confirm_no_known_allergies(p uuid) returns date
    language plpgsql volatile {_DEFINER} as $$
    declare
      d date := public.local_today();
    begin
      if not public.can_write_patient(p) then
        raise exception 'not a writer' using errcode = '42501';
      end if;
      {_NKA_LOCK.format(p="p")};
      if exists (select 1 from public.allergies a where a.patient_id = p) then
        raise exception 'an allergy is recorded' using errcode = '23514';
      end if;
      insert into public.no_known_allergies (patient_id, confirmed_on, confirmed_by)
        values (p, d, public.app_user_id())
        on conflict (patient_id) do update
          set confirmed_on = excluded.confirmed_on, confirmed_by = excluded.confirmed_by,
              created_at = now();
      perform public.caregiver_audit('allergy.none_confirmed', 'patient', p::text, p, null);
      return d;
    end $$
    """,
    f"""
    create function clear_no_known_allergies(p uuid) returns boolean
    language plpgsql volatile {_DEFINER} as $$
    begin
      if not public.can_write_patient(p) then
        raise exception 'not a writer' using errcode = '42501';
      end if;
      delete from public.no_known_allergies where patient_id = p;
      if not found then
        return false;
      end if;
      perform public.caregiver_audit('allergy.none_cleared', 'patient', p::text, p, null);
      return true;
    end $$
    """,
    # an allergy added (by any route) ends the statement, under the same lock as confirming
    f"""
    create function allergies_end_no_known() returns trigger
    language plpgsql {_DEFINER} as $$
    begin
      {_NKA_LOCK.format(p="new.patient_id")};
      delete from public.no_known_allergies where patient_id = new.patient_id;
      if found then
        perform public.caregiver_audit('allergy.none_ended', 'patient', new.patient_id::text,
          new.patient_id, null);
      end if;
      return null;
    end $$
    """,
    f"""
    create function set_steroid_card(p uuid, p_on boolean) returns boolean
    language plpgsql volatile {_DEFINER} as $$
    declare
      doctor boolean := public.is_treating_doctor(p);
      n integer;
    begin
      if not (doctor or public.is_owner(p)) then
        raise exception 'not the owner or a treating doctor' using errcode = '42501';
      end if;
      if p_on then
        -- a doctor's mark is never replaced by the owner's own
        insert into public.steroid_cards (patient_id, marked_on, marked_by, by_doctor)
          values (p, public.local_today(), public.app_user_id(), doctor)
          on conflict (patient_id) do update
            set marked_on = excluded.marked_on, marked_by = excluded.marked_by,
                by_doctor = excluded.by_doctor, created_at = now()
            where excluded.by_doctor or not public.steroid_cards.by_doctor;
        get diagnostics n = row_count;
        if n = 0 then
          return false;  -- the doctor's mark stays: nothing changed, nothing audited
        end if;
        perform public.caregiver_audit('steroid_card.set', 'patient', p::text, p,
          jsonb_build_object('by_doctor', doctor));
        return true;
      end if;
      delete from public.steroid_cards where patient_id = p;
      if not found then
        return false;
      end if;
      perform public.caregiver_audit('steroid_card.clear', 'patient', p::text, p,
        jsonb_build_object('by_doctor', doctor));
      return true;
    end $$
    """,
    # what readers see, with the doctor's name (users is not readable to them directly)
    f"""
    create function profile_steroid_card(p uuid)
    returns table (marked_on date, by_doctor boolean, doctor_name text)
    language sql stable {_DEFINER} as $$
      select s.marked_on, s.by_doctor,
             case when s.by_doctor and u.deleted_at is null then u.display_name end
      from public.steroid_cards s
      left join public.users u on u.id = s.marked_by
      where public.can_read_patient(p) and s.patient_id = p
    $$
    """,
    # the shared summary (0042): the statement, for the 'summary' section
    f"""
    create function share_no_known_allergies(p_session_hash text) returns date
    language sql stable {_DEFINER} as $$
      select n.confirmed_on
      from public.share_scope_of(p_session_hash, 'summary') k
      join public.patients x on x.id = k.patient_id and x.deleted_at is null
      join public.no_known_allergies n on n.patient_id = k.patient_id
    $$
    """,
]

_APP = [
    "confirm_no_known_allergies(uuid)",
    "clear_no_known_allergies(uuid)",
    "set_steroid_card(uuid, boolean)",
    "profile_steroid_card(uuid)",
    "share_no_known_allergies(text)",
]


def upgrade() -> None:
    for sql in _TABLES:
        op.execute(sql)
    for table in ("no_known_allergies", "steroid_cards"):
        op.execute(f"alter table {table} enable row level security")
        op.execute(f"alter table {table} force row level security")
        op.execute(
            f"create policy {table}_owner on {table} for all to labtrack_owner"
            " using (true) with check (true)"
        )
        # read by whoever reads the profile; written only through the functions
        op.execute(
            f"create policy {table}_select on {table} for select to labtrack_app"
            " using (can_read_patient(patient_id))"
        )
        op.execute(f"grant select on {table} to labtrack_app")
        op.execute(f"revoke truncate on {table} from public")
    for sql in _FUNCTIONS:
        op.execute(sql)
    op.execute("revoke execute on function allergies_end_no_known() from public")
    op.execute(
        """create trigger allergies_end_no_known after insert on allergies
           for each row execute function allergies_end_no_known()"""
    )
    for name in _APP:
        op.execute(f"revoke execute on function {name} from public")
    op.execute(f"grant execute on function {', '.join(_APP)} to labtrack_app")


def downgrade() -> None:
    for name in reversed(_APP):
        op.execute(f"drop function {name}")
    op.execute("drop trigger allergies_end_no_known on allergies")
    op.execute("drop function allergies_end_no_known()")
    op.execute("drop table steroid_cards")
    op.execute("drop table no_known_allergies")
