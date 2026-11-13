"""Reads for one test's trend chart (Phase 6.4; docs/06 §2). Confirmed values only (rule 4):
the points query filters on the report's status itself. RLS decides whose rows the caller
sees; reads are not audited (2.7a)."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Row
from sqlalchemy.ext.asyncio import AsyncSession

from labtrack.db.sql import bound_text

MAX_POINTS = 2000  # one test over decades of monthly tests, with room to spare
MAX_EVENTS = 500

_TEST = bound_text(
    "select code, name_mn, name_en, canonical_unit, decimals, kind::text as kind, category"
    " from test_catalog where code = :c"
)
_POINTS = bound_text(
    "select lr.id, lr.report_id, r.document_id, r.lab_name, lr.collected_at,"
    " r.collected_precision, lr.raw_value, lr.raw_unit, lr.comparator, lr.value_text,"
    " lr.qualitative, lr.unit_canonical, lr.value_canonical, lr.ref_text,"
    " lr.ref_low_canonical, lr.ref_high_canonical, lr.critical_text,"
    " lr.critical_low_canonical, lr.critical_high_canonical, lr.flag::text as flag, lr.issues"
    " from lab_results lr"
    " join lab_reports r on r.id = lr.report_id and r.patient_id = lr.patient_id"
    " where lr.patient_id = :p and lr.test_code = :c and r.status = 'confirmed'"
    " and lr.collected_at is not null"
    " and (cast(:since as timestamptz) is null or lr.collected_at >= :since)"
    " and (cast(:until as timestamptz) is null or lr.collected_at < :until)"
    " order by lr.collected_at desc, lr.id desc limit :n"
)
_TRANSPLANTS = bound_text(
    "select id, organ::text as organ, transplant_date, date_precision,"
    " graft_status::text as graft_status from transplants where patient_id = :p"
    " order by (graft_status in ('functioning', 'unknown')) desc, transplant_date desc,"
    " created_at desc"
)
_EVENTS = bound_text(
    "select id, kind::text as kind, title, started_on, ended_on from clinical_events"
    " where patient_id = :p order by started_on desc limit :n"
)
# the medicines linked to this test through the catalog (never by name)
_LINKED = bound_text(
    "select m.id, m.name, m.started_on, m.stopped_on, m.planned_end_on from medications m"
    " join medication_catalog c on c.code = m.catalog_code"
    " where m.patient_id = :p and c.related_test_code = :c order by m.created_at"
)
_REGIMENS = bound_text(
    "select medication_id, effective_from, seq, voided_at, schedule, dose_unit, dose_unit_text"
    " from medication_regimens where patient_id = :p"
    " and medication_id = any(cast(:m as uuid[]))"
)


async def test(db: AsyncSession, code: str) -> Row[Any] | None:
    return (await db.execute(_TEST, {"c": code})).one_or_none()


async def points(
    db: AsyncSession,
    patient_id: UUID,
    code: str,
    since: datetime | None,
    until: datetime | None,
) -> Sequence[Row[Any]]:
    """Newest first, at most MAX_POINTS + 1 (one more tells the caller there were more)."""
    params = {"p": patient_id, "c": code, "since": since, "until": until, "n": MAX_POINTS + 1}
    return (await db.execute(_POINTS, params)).all()


async def transplants(db: AsyncSession, patient_id: UUID) -> Sequence[Row[Any]]:
    """Functioning (or unknown) grafts first, most recent first."""
    return (await db.execute(_TRANSPLANTS, {"p": patient_id})).all()


async def events(db: AsyncSession, patient_id: UUID) -> Sequence[Row[Any]]:
    """The most recent MAX_EVENTS, oldest first."""
    rows = (await db.execute(_EVENTS, {"p": patient_id, "n": MAX_EVENTS})).all()
    return list(reversed(rows))


async def linked_medications(db: AsyncSession, patient_id: UUID, code: str) -> Sequence[Row[Any]]:
    return (await db.execute(_LINKED, {"p": patient_id, "c": code})).all()


async def regimens(
    db: AsyncSession, patient_id: UUID, medication_ids: list[UUID]
) -> Sequence[Row[Any]]:
    if not medication_ids:
        return []
    return (await db.execute(_REGIMENS, {"p": patient_id, "m": medication_ids})).all()
