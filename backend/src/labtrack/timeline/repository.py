"""One timeline of a profile (Phase 6.5; docs/08 "Цагийн хэлхээс", docs/06 §5): transplants,
medicines started/stopped/changed, clinical events and CONFIRMED lab reports (rule 4: a draft
is not history yet - it waits in the uploads list). RLS decides whose rows the caller sees;
reads are not audited (2.7a).

Keyset pagination over (day, rank, id), newest first, one query over all sources.
"""

from collections.abc import Sequence
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import Row
from sqlalchemy.ext.asyncio import AsyncSession

from labtrack.db.sql import bound_text

KINDS = (
    "transplant",
    "medication_started",
    "medication_stopped",
    "regimen_changed",
    "event",
    "report",
)
# a day's order, newest first: a report of the day under the day's other entries
RANK = {
    "transplant": 6,
    "medication_started": 5,
    "medication_stopped": 4,
    "regimen_changed": 3,
    "event": 2,
    "report": 1,
}

_ITEMS = bound_text(
    "select kind, rank, id, day, precision, at, title, detail, ref_id, until_day,"
    " results, flagged, unflagged, day > :today as planned from ("
    # a transplant: its stored date is the first possible day of a month/year-only date
    " select 'transplant' as kind, 6 as rank, t.id, t.transplant_date as day,"
    " t.date_precision as precision, null::timestamptz as at, t.organ::text as title,"
    " t.graft_status::text as detail, null::uuid as ref_id, null::date as until_day,"
    " null::int as results, null::int as flagged, null::int as unflagged"
    " from transplants t where t.patient_id = :p"
    " union all"
    " select 'medication_started', 5, m.id, m.started_on, 'day', null, m.name, null, null,"
    " null, null, null, null from medications m"
    " where m.patient_id = :p and m.started_on is not null"
    " union all"
    # the stop day is the first day no longer taken (Q21)
    " select 'medication_stopped', 4, m.id, m.stopped_on, 'day', null, m.name, null, null,"
    " null, null, null, null from medications m"
    " where m.patient_id = :p and m.stopped_on is not null"
    " union all"
    # a dose or schedule change: a regimen after the medicine's first one, the latest
    # entered of its day, never a voided one (a mistaken future row)
    " select 'regimen_changed', 3, r.id, r.effective_from, 'day', null, m.name, null, m.id,"
    " null, null, null, null from medication_regimens r"
    " join medications m on m.id = r.medication_id and m.patient_id = r.patient_id"
    " where r.patient_id = :p and r.voided_at is null"
    " and exists (select 1 from medication_regimens e where e.medication_id = r.medication_id"
    " and e.patient_id = r.patient_id and e.voided_at is null"
    " and e.effective_from < r.effective_from)"
    " and not exists (select 1 from medication_regimens l"
    " where l.medication_id = r.medication_id and l.patient_id = r.patient_id"
    " and l.voided_at is null and l.effective_from = r.effective_from and l.seq > r.seq)"
    " union all"
    " select 'event', 2, e.id, e.started_on, 'day', null, e.title, e.kind::text, null,"
    " e.ended_on, null, null, null from clinical_events e where e.patient_id = :p"
    " union all"
    " select 'report', 1, r.id, (r.collected_at at time zone 'Asia/Ulaanbaatar')::date,"
    " r.collected_precision, r.collected_at, r.lab_name, r.source, r.document_id, null,"
    " (select count(*) from lab_results x where x.report_id = r.id"
    " and x.patient_id = r.patient_id)::int,"
    " (select count(*) from lab_results x where x.report_id = r.id"
    " and x.patient_id = r.patient_id"
    " and x.flag in ('low', 'high', 'critical_low', 'critical_high', 'abnormal'))::int,"
    # values with no usable range (no_reference, unknown): never "all fine" by omission
    " (select count(*) from lab_results x where x.report_id = r.id"
    " and x.patient_id = r.patient_id and x.flag in ('no_reference', 'unknown'))::int"
    " from lab_reports r where r.patient_id = :p and r.status = 'confirmed'"
    " and r.collected_at is not null"
    " and (cast(:lab as text) is null or r.lab_name = :lab)"
    " ) x"
    " where x.kind = any(cast(:kinds as text[]))"
    " and (cast(:day as date) is null or (x.day, x.rank, x.id::text) < (:day, :rank, :id))"
    " order by x.day desc, x.rank desc, x.id::text desc limit :n"
)
_LABS = bound_text(
    "select lab_name, count(*)::int as reports, max(collected_at) as latest from lab_reports"
    " where patient_id = :p and status = 'confirmed' and lab_name is not null"
    " group by lab_name order by max(collected_at) desc nulls last limit 100"
)


async def items(
    db: AsyncSession,
    patient_id: UUID,
    *,
    kinds: list[str],
    lab: str | None,
    after: tuple[date, int, str] | None,
    limit: int,
    today: date,
) -> Sequence[Row[Any]]:
    day, rank, last = after if after is not None else (None, None, None)
    params = {
        "p": patient_id,
        "kinds": kinds,
        "lab": lab,
        "day": day,
        "rank": rank,
        "id": last,
        "n": limit,
        "today": today,
    }
    return (await db.execute(_ITEMS, params)).all()


async def labs(db: AsyncSession, patient_id: UUID) -> Sequence[Row[Any]]:
    return (await db.execute(_LABS, {"p": patient_id})).all()
