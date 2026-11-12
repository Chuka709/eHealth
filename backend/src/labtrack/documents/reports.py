"""Lab reports read from a document (Phase 4.6; docs/05, docs/08 "Хянах").

What RLS lets the caller see (0031): the profile's writers see the drafts, readers (doctor,
viewer) only confirmed reports - an unchecked draft never reaches anyone else (rule 4).
Nothing here judges a value: ranges, flags and issues are as stored. Reads are not audited,
as with every other read (2.7a); the document's own view is (`document.view`).
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from labtrack.core.lab_drafts import LOCAL_ZONE
from labtrack.core.medications import minutes_between
from labtrack.db.sql import bound_text
from labtrack.documents import service

MAX_REPORTS = 100  # a 20-page document of small panels, with room to spare


@dataclass(frozen=True)
class Result:
    id: UUID
    position: int
    test_code: str | None
    test_name_mn: str | None
    test_name_en: str | None
    raw_name: str
    raw_value: str
    raw_unit: str | None
    value_numeric: Decimal | None
    comparator: str | None
    value_text: str | None
    qualitative: str | None
    ref_text: str | None
    ref_low: Decimal | None
    ref_high: Decimal | None
    critical_text: str | None
    critical_low: Decimal | None
    critical_high: Decimal | None
    lab_flag: str | None
    flag: str
    flag_source: str | None
    flag_mismatch: bool
    unit_canonical: str | None
    value_canonical: Decimal | None
    issues: list[str]
    acknowledged: list[str]
    edited_by_user: bool
    read_value: str | None  # as read, before the person's correction (None: not corrected)
    read_critical_text: str | None
    source_page: int | None


@dataclass(frozen=True)
class LastDose:
    """The last dose of a medicine linked to a drug-level test, logged before the sample
    (docs/08 "Эмийн түвшин ↔ тун"): a fact for the doctor reading the trough - no judgement.
    `taken_at` None with `time_unknown`: the sample's time is not printed (only its day)."""

    test_code: str
    medication_id: UUID
    medication_name: str
    taken_at: datetime | None
    minutes_before: int | None
    time_unknown: bool
    other_records: int  # more "taken" records of that same dose (Q24): shown, never merged


@dataclass(frozen=True)
class Report:
    id: UUID
    document_id: UUID | None
    method: str | None  # local | ai; None for a reader (runs are the writers' only)
    status: str
    lab_name: str | None
    panel_name: str | None
    specimen: str | None
    collected_at: datetime | None
    collected_precision: str
    analysed_at: datetime | None
    reported_at: datetime | None
    date_ambiguous: bool
    name_match_score: Decimal | None
    has_unconfirmed_critical: bool
    created_at: datetime
    results: list[Result]
    last_doses: list[LastDose]


_REPORTS = bound_text(
    "select r.id, r.document_id, run.method, r.status::text as status, r.lab_name,"
    " r.panel_name, r.specimen, r.collected_at, r.collected_precision, r.analysed_at,"
    " r.reported_at, r.date_ambiguous,"
    # how the printed name matched: for the profile's writers only, like the run (security
    # review 4.6) - a reader sees the confirmed values, not how they were read
    " case when can_write_patient(r.patient_id) then r.name_match_score end"
    " as name_match_score, r.has_unconfirmed_critical,"
    " r.created_at"
    " from lab_reports r left join extraction_runs run"
    " on run.id = r.extraction_run_id and run.patient_id = r.patient_id"
    " where r.patient_id = :p and (r.document_id = :d or r.id = :r)"
    " order by r.collected_at nulls last, r.panel_name nulls last, r.id limit :n"
)
_RESULTS = bound_text(
    "select x.report_id, x.id, x.position, x.test_code, c.name_mn as test_name_mn,"
    " c.name_en as test_name_en, x.raw_name, x.raw_value, x.raw_unit, x.value_numeric,"
    " x.comparator, x.value_text, x.qualitative, x.ref_text, x.ref_low, x.ref_high,"
    " x.critical_text, x.critical_low, x.critical_high, x.lab_flag, x.flag::text as flag,"
    " x.flag_source, x.flag_mismatch, x.unit_canonical, x.value_canonical,"
    " x.issues, x.acknowledged, x.edited_by_user, x.read_value, x.read_critical_text,"
    " x.source_page"
    " from lab_results x left join test_catalog c on c.code = x.test_code"
    " where x.patient_id = :p and x.report_id = any(:ids)"
    " order by x.report_id, x.position"
)


# the latest logged dose (or extra "taken" record) of each linked medicine, within 72 hours
# before the sample; medicines linked to the test through the catalog only (never by name)
_LAST_DOSES = bound_text(
    "select distinct on (c.related_test_code, m.id) c.related_test_code as test_code,"
    " m.id as medication_id, m.name as medication_name, i.taken_at,"
    # more records of that dose logged up to the sample (later ones say nothing about it)
    " (select count(*) from medication_intake_extra e where e.intake_id = i.id"
    " and e.taken_at <= :at)::int"
    " as other_records"
    " from medications m"
    " join medication_catalog c on c.code = m.catalog_code"
    " join medication_intakes i on i.medication_id = m.id and i.patient_id = m.patient_id"
    " where m.patient_id = :p and c.related_test_code = any(cast(:codes as text[]))"
    " and i.status in ('taken', 'late') and i.taken_at is not null"
    " and i.taken_at <= :at and i.taken_at > :at - interval '72 hours'"
    " order by c.related_test_code, m.id, i.taken_at desc"
)
# with only the sample's day: the linked medicines taken on that day, without a dose
_LINKED = bound_text(
    "select distinct c.related_test_code as test_code, m.id as medication_id,"
    " m.name as medication_name from medications m"
    " join medication_catalog c on c.code = m.catalog_code"
    " where m.patient_id = :p and c.related_test_code = any(cast(:codes as text[]))"
    " and (m.started_on is null or m.started_on <= :day)"
    " and (m.stopped_on is null or m.stopped_on >= :day)"
)


async def last_doses(
    db: AsyncSession,
    patient_id: UUID,
    codes: list[str],
    collected_at: datetime | None,
    precision: str,
) -> list[LastDose]:
    if not codes or collected_at is None:
        return []
    if precision != "minute":  # a day only: which dose came before is not known
        day = collected_at.astimezone(LOCAL_ZONE).date()
        rows = (await db.execute(_LINKED, {"p": patient_id, "codes": codes, "day": day})).all()
        return [
            LastDose(r.test_code, r.medication_id, r.medication_name, None, None, True, 0)
            for r in rows
        ]
    rows = (
        await db.execute(_LAST_DOSES, {"p": patient_id, "codes": codes, "at": collected_at})
    ).all()
    return [
        LastDose(
            r.test_code,
            r.medication_id,
            r.medication_name,
            r.taken_at,
            minutes_between(r.taken_at, collected_at),
            False,
            r.other_records,
        )
        for r in rows
    ]


async def _reports(
    db: AsyncSession, patient_id: UUID, *, document_id: UUID | None, report_id: UUID | None
) -> list[Report]:
    params = {"p": patient_id, "d": document_id, "r": report_id, "n": MAX_REPORTS}
    rows = (await db.execute(_REPORTS, params)).mappings().all()
    if not rows:
        return []
    by_report: dict[UUID, list[Result]] = {r["id"]: [] for r in rows}
    found = await db.execute(_RESULTS, {"p": patient_id, "ids": list(by_report)})
    for x in found.mappings().all():
        fields: dict[str, Any] = dict(x)
        by_report[fields.pop("report_id")].append(Result(**fields))
    out = []
    for r in rows:
        results = by_report[r["id"]]
        codes = sorted({x.test_code for x in results if x.test_code})
        doses = await last_doses(db, patient_id, codes, r["collected_at"], r["collected_precision"])
        out.append(Report(**dict(r), results=results, last_doses=doses))
    return out


async def for_document(db: AsyncSession, patient_id: UUID, document_id: UUID) -> list[Report]:
    """The document's reports with their results, as far as the caller may see them."""
    await service.get(db, patient_id, document_id)  # 404 for another profile's document
    return await _reports(db, patient_id, document_id=document_id, report_id=None)


async def for_report(db: AsyncSession, patient_id: UUID, report_id: UUID) -> Report | None:
    found = await _reports(db, patient_id, document_id=None, report_id=report_id)
    return found[0] if found else None
