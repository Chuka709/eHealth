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
    issues: list[str]
    source_page: int | None


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
    " where r.patient_id = :p and r.document_id = :d"
    " order by r.collected_at nulls last, r.panel_name nulls last, r.id limit :n"
)
_RESULTS = bound_text(
    "select x.report_id, x.id, x.position, x.test_code, c.name_mn as test_name_mn,"
    " c.name_en as test_name_en, x.raw_name, x.raw_value, x.raw_unit, x.value_numeric,"
    " x.comparator, x.value_text, x.qualitative, x.ref_text, x.ref_low, x.ref_high,"
    " x.critical_text, x.critical_low, x.critical_high, x.lab_flag, x.flag::text as flag,"
    " x.issues, x.source_page"
    " from lab_results x left join test_catalog c on c.code = x.test_code"
    " where x.patient_id = :p and x.report_id = any(:ids)"
    " order by x.report_id, x.position"
)


async def for_document(db: AsyncSession, patient_id: UUID, document_id: UUID) -> list[Report]:
    """The document's reports with their results, as far as the caller may see them."""
    await service.get(db, patient_id, document_id)  # 404 for another profile's document
    rows = (
        (await db.execute(_REPORTS, {"p": patient_id, "d": document_id, "n": MAX_REPORTS}))
        .mappings()
        .all()
    )
    if not rows:
        return []
    by_report: dict[UUID, list[Result]] = {r["id"]: [] for r in rows}
    found = await db.execute(_RESULTS, {"p": patient_id, "ids": list(by_report)})
    for x in found.mappings().all():
        fields: dict[str, Any] = dict(x)
        by_report[fields.pop("report_id")].append(Result(**fields))
    return [Report(**dict(r), results=by_report[r["id"]]) for r in rows]
