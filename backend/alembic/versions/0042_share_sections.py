"""What a share link shows, section by section (Phase 7.3; Q62, H37).

A viewing session reads nothing through the row policies (0041). Each section is a definer
function of its own: it checks the session, that the link includes the section, and applies
the link's date range - all in the database. Only what a doctor needs is returned: no free-text
notes, no ids of who recorded what, no contacts, no documents, no drafts (confirmed lab
results only).

- summary: whose record (name, birth date, sex) and allergies;
- labs: confirmed results, as printed, with the lab's range and the flag;
- meds: medicines taken within the range, with their dose history in the range (voided
  rows left out; no ids);
- transplant: transplants (no notes);
- events: events overlapping the range;
- vitals: measurements within the range.

A link on a minor's profile also needs the owner's consents for that profile (Q9), as the app
asks of everyone (0041 left this open - Q62).

Revision ID: 0042
Revises: 0041
Create Date: 2026-11-17
"""

import importlib.util
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

from alembic import op

revision: str = "0042"
down_revision: str | None = "0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEFINER = "security definer set search_path = pg_catalog, public, pg_temp"


def _revision(filename: str) -> ModuleType:
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_M41 = _revision("0041_share_links.py")
(_OWNER_OK_OLD,) = [f for f in _M41._FUNCTIONS if "function share_link_owner_ok(" in f]
_OWNER_OK_OLD = _OWNER_OK_OLD.replace("create function", "create or replace function", 1)
_MINOR_TAIL = """                 and c.kind in ('terms', 'privacy', 'sensitive_data')) = 3)
    $$"""
if _MINOR_TAIL not in _OWNER_OK_OLD:
    raise RuntimeError("share_link_owner_ok of 0041 changed")
# a minor's profile: the owner's consents given for that profile too (latest per kind)
_OWNER_OK_NEW = _OWNER_OK_OLD.replace(
    _MINOR_TAIL,
    """                 and c.kind in ('terms', 'privacy', 'sensitive_data')) = 3
          -- a minor's (as is_minor_patient reads it; that one needs a reader)
          and (not coalesce(x.birth_date > public.local_today() - interval '18 years', false) or (
            not exists (
              select 1 from (
                select distinct on (c.kind) c.granted from public.consents c
                where c.user_id = u.id and c.patient_id = l.patient_id
                  and c.kind in ('terms', 'privacy', 'sensitive_data')
                order by c.kind, c.created_at desc, c.id desc) latest
              where not latest.granted)
            and (select count(distinct c.kind) from public.consents c
                 where c.user_id = u.id and c.patient_id = l.patient_id
                   and c.kind in ('terms', 'privacy', 'sensitive_data')) = 3)))
    $$""",
)

# the session's link, if it is live and includes the section (alias-free; used by each one)
_SCOPE = f"""
create function share_scope_of(p_session_hash text, p_scope text)
returns table (patient_id uuid, date_from date, date_to date)
language sql stable {_DEFINER} as $$
  select l.patient_id, l.date_from, l.date_to
  from public.share_sessions s
  join public.share_links l on l.id = s.link_id
  where public.app_user_id() is null and s.token_hash = p_session_hash
    and s.expires_at > now() and l.revoked_at is null and l.expires_at > now()
    and p_scope = any(l.scopes) and public.share_link_owner_ok(l.id)
$$
"""

# the Ulaanbaatar day of a moment
_UB = "(({x}) at time zone 'Asia/Ulaanbaatar')::date"

_SECTIONS = [
    f"""
    create function share_summary(p_session_hash text)
    returns table (full_name text, birth_date date, sex text)
    language sql stable {_DEFINER} as $$
      select x.full_name, x.birth_date, x.sex::text
      from public.share_scope_of(p_session_hash, 'summary') k
      join public.patients x on x.id = k.patient_id and x.deleted_at is null
    $$
    """,
    f"""
    create function share_allergies(p_session_hash text)
    returns table (substance text, reaction text, severity text, noted_on date)
    language sql stable {_DEFINER} as $$
      select a.substance, a.reaction, a.severity, a.noted_on
      from public.share_scope_of(p_session_hash, 'summary') k
      join public.allergies a on a.patient_id = k.patient_id
      order by a.substance
    $$
    """,
    f"""
    create function share_labs(p_session_hash text)
    returns table (collected_at timestamptz, collected_precision text, lab_name text,
                   test_code text, test_name_mn text, test_name_en text, raw_name text,
                   raw_value text, raw_unit text, ref_text text, critical_text text,
                   flag text, lab_flag text)
    language sql stable {_DEFINER} as $$
      select r.collected_at, r.collected_precision, r.lab_name, v.test_code, t.name_mn,
             t.name_en, v.raw_name, v.raw_value, v.raw_unit, v.ref_text, v.critical_text,
             v.flag::text, v.lab_flag
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
    """,
    # medicines taken within the range, each with its dose history in the range (the dose in
    # force when the range begins, and every change up to its end); no ids; a stop after the
    # range is not shown (it lies outside what was shared)
    f"""
    create function share_medications(p_session_hash text)
    returns table (name text, brand text, form text, strength text, route text,
                   purpose text, started_on date, stopped_on date, planned_end_on date,
                   regimens jsonb)
    language sql stable {_DEFINER} as $$
      select m.name, m.brand, m.form, m.strength, m.route, m.purpose, m.started_on,
             case when k.date_to is not null and m.stopped_on > k.date_to then null
                  else m.stopped_on end,
             case when k.date_to is not null and m.planned_end_on > k.date_to then null
                  else m.planned_end_on end,
             coalesce((
               select jsonb_agg(jsonb_build_object(
                        'effective_from', g.effective_from,
                        'dose_amount', trim_scale(g.dose_amount)::text, 'dose_unit', g.dose_unit,
                        'dose_unit_text', g.dose_unit_text, 'schedule', g.schedule,
                        'instructions', g.instructions)
                      order by g.effective_from, g.seq)
               from public.medication_regimens g
               where g.medication_id = m.id and g.patient_id = m.patient_id
                 and g.voided_at is null
                 and (k.date_to is null or g.effective_from <= k.date_to)
                 and (k.date_from is null or g.effective_from >= k.date_from
                      or g.effective_from = (
                        select max(g2.effective_from) from public.medication_regimens g2
                        where g2.medication_id = m.id and g2.voided_at is null
                          and g2.effective_from <= k.date_from))), '[]'::jsonb)
      from public.share_scope_of(p_session_hash, 'meds') k
      join public.medications m on m.patient_id = k.patient_id
      where (k.date_to is null or m.started_on is null or m.started_on <= k.date_to)
        and (k.date_from is null or m.stopped_on is null or m.stopped_on >= k.date_from)
      order by m.stopped_on nulls first, m.name
    $$
    """,
    f"""
    create function share_transplants(p_session_hash text)
    returns table (organ text, organ_detail text, transplant_date date, date_precision text,
                   country text, hospital text, transplant_number int, donor_type text,
                   recipient_blood_type text, donor_blood_type text, abo_incompatible boolean,
                   cmv_donor text, cmv_recipient text, ebv_donor text, ebv_recipient text,
                   primary_disease text, induction_therapy text, graft_status text,
                   graft_status_date date, follow_up_center text, follow_up_doctor text)
    language sql stable {_DEFINER} as $$
      select x.organ::text, x.organ_detail, x.transplant_date, x.date_precision, x.country,
             x.hospital, x.transplant_number, x.donor_type::text, x.recipient_blood_type,
             x.donor_blood_type, x.abo_incompatible, x.cmv_donor, x.cmv_recipient,
             x.ebv_donor, x.ebv_recipient, x.primary_disease, x.induction_therapy,
             x.graft_status::text, x.graft_status_date, x.follow_up_center, x.follow_up_doctor
      from public.share_scope_of(p_session_hash, 'transplant') k
      join public.transplants x on x.patient_id = k.patient_id
      order by x.transplant_date desc nulls last
    $$
    """,
    f"""
    create function share_events(p_session_hash text)
    returns table (kind text, title text, started_on date, ended_on date, place text,
                   outcome text)
    language sql stable {_DEFINER} as $$
      select e.kind::text, e.title, e.started_on,
             case when k.date_to is not null and e.ended_on > k.date_to then null
                  else e.ended_on end,
             e.place, e.outcome
      from public.share_scope_of(p_session_hash, 'events') k
      join public.clinical_events e on e.patient_id = k.patient_id
      where (k.date_to is null or e.started_on <= k.date_to)
        and (k.date_from is null or coalesce(e.ended_on, e.started_on) >= k.date_from)
      order by e.started_on desc
    $$
    """,
    f"""
    create function share_vitals(p_session_hash text)
    returns table (kind text, value numeric, unit text, measured_at timestamptz,
                   group_no int)
    language sql stable {_DEFINER} as $$
      -- a reading's parts (blood pressure) share a number, never an id
      select v.kind::text, v.value, v.unit, v.measured_at,
             case when v.group_id is not null
                  then (dense_rank() over (order by v.group_id))::int end
      from public.share_scope_of(p_session_hash, 'vitals') k
      join public.vitals v on v.patient_id = k.patient_id
      where (k.date_from is null or {_UB.format(x="v.measured_at")} >= k.date_from)
        and (k.date_to is null or {_UB.format(x="v.measured_at")} <= k.date_to)
      order by v.measured_at desc
      limit 3000
    $$
    """,
]

# the viewer finishes: the session ends now (not only the browser's cookie)
_SECTIONS.append(
    f"""
    create function share_session_end(p_session_hash text) returns void
    language sql volatile {_DEFINER} as $$
      update public.share_sessions set expires_at = now()
      where public.app_user_id() is null and token_hash = p_session_hash
        and expires_at > now()
    $$
    """
)

_APP = [
    "share_session_end(text)",
    "share_summary(text)",
    "share_allergies(text)",
    "share_labs(text)",
    "share_medications(text)",
    "share_transplants(text)",
    "share_events(text)",
    "share_vitals(text)",
]


def upgrade() -> None:
    op.execute(_OWNER_OK_NEW)
    op.execute(_SCOPE)
    for sql in _SECTIONS:
        op.execute(sql)
    for name in ("share_scope_of(text, text)", *_APP):
        op.execute(f"revoke execute on function {name} from public")
    op.execute(f"grant execute on function {', '.join(_APP)} to labtrack_app")


def downgrade() -> None:
    for name in reversed(_APP):
        op.execute(f"drop function {name}")
    op.execute("drop function share_scope_of(text, text)")
    op.execute(_OWNER_OK_OLD)
