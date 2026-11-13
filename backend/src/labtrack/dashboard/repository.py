"""Reads for the Home dashboard (Phase 6.3; 0038). Only confirmed values (rule 4): the
`latest_results` view and the history query both filter on the report's status themselves.
RLS decides whose rows the caller sees; reads are not audited (2.7a), changes are."""

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import Row
from sqlalchemy.ext.asyncio import AsyncSession

from labtrack.db.sql import bound_text

HISTORY_PER_TEST = 30  # enough for a 10-point spark in one unit and the previous value

_ORGANS = bound_text(
    "select organ::text from transplants where patient_id = :p"
    " and graft_status in ('functioning', 'unknown')"
    " order by transplant_date desc, created_at desc"
)
# the medicines linked to a level test (through the catalog only, never by name); which are
# taken today is core's to say (core.medications.is_current)
_LINKED = bound_text(
    "select c.related_test_code as test_code, m.started_on, m.stopped_on, m.planned_end_on"
    " from medications m join medication_catalog c on c.code = m.catalog_code"
    " where m.patient_id = :p and c.related_test_code is not null"
)
_PINNED = bound_text("select test_codes from dashboard_cards where patient_id = :p")
_LATEST = bound_text(
    "select v.id, v.report_id, v.test_code, v.collected_at, v.raw_value, v.raw_unit,"
    " v.comparator, v.value_text, v.qualitative, v.unit_canonical, v.value_canonical,"
    " v.ref_text, v.ref_low_canonical, v.ref_high_canonical, v.flag::text as flag,"
    " lr.issues, t.name_mn, t.name_en, t.category"
    " from latest_results v"
    " join lab_results lr on lr.id = v.id and lr.patient_id = v.patient_id"
    " join test_catalog t on t.code = v.test_code"
    " where v.patient_id = :p"
)
_HISTORY = bound_text(
    "select id, test_code, collected_at, value_canonical, comparator, unit_canonical, flag,"
    " raw_value, raw_unit"
    " from (select lr.id, lr.test_code, lr.collected_at, lr.value_canonical, lr.comparator,"
    " lr.raw_value, lr.raw_unit,"
    " lr.unit_canonical, lr.flag::text as flag, row_number() over (partition by lr.test_code"
    " order by lr.collected_at desc, lr.id desc) as n"
    " from lab_results lr"
    " join lab_reports r on r.id = lr.report_id and r.patient_id = lr.patient_id"
    " where lr.patient_id = :p and r.status = 'confirmed' and lr.collected_at is not null"
    " and lr.test_code = any(cast(:codes as text[]))) x"
    " where n <= :n"
)
_TESTS = bound_text(
    "select code, name_mn, name_en, category from test_catalog"
    " where code = any(cast(:codes as text[])) and is_active"
)
_ACTIVE = bound_text(
    "select count(*) from test_catalog where code = any(cast(:codes as text[])) and is_active"
)
# update, else insert: an upsert would run the insert trigger on a kept, since retired test
_UPDATE = bound_text("update dashboard_cards set test_codes = :c where patient_id = :p")
_INSERT = bound_text("insert into dashboard_cards (patient_id, test_codes) values (:p, :c)")
_RESET = bound_text("delete from dashboard_cards where patient_id = :p")
_AUDIT = bound_text("select audit_write(:action, 'patient', cast(:eid as text), :pid, null)")


async def organs(db: AsyncSession, patient_id: UUID) -> list[str]:
    return list((await db.execute(_ORGANS, {"p": patient_id})).scalars())


async def linked_medications(db: AsyncSession, patient_id: UUID) -> Sequence[Row[Any]]:
    return (await db.execute(_LINKED, {"p": patient_id})).all()


async def pinned(db: AsyncSession, patient_id: UUID) -> list[str] | None:
    """The profile's own list, or None (no row - or the caller is a reader, who never sees
    it)."""
    value = (await db.execute(_PINNED, {"p": patient_id})).scalar_one_or_none()
    return None if value is None else list(value)


async def latest(db: AsyncSession, patient_id: UUID) -> Sequence[Row[Any]]:
    return (await db.execute(_LATEST, {"p": patient_id})).all()


async def history(db: AsyncSession, patient_id: UUID, codes: list[str]) -> Sequence[Row[Any]]:
    if not codes:
        return []
    params = {"p": patient_id, "codes": codes, "n": HISTORY_PER_TEST}
    return (await db.execute(_HISTORY, params)).all()


async def tests(db: AsyncSession, codes: list[str]) -> Sequence[Row[Any]]:
    if not codes:
        return []
    return (await db.execute(_TESTS, {"codes": codes})).all()


async def active_count(db: AsyncSession, codes: list[str]) -> int:
    return int((await db.execute(_ACTIVE, {"codes": codes})).scalar_one())


async def put_cards(db: AsyncSession, patient_id: UUID, codes: list[str]) -> None:
    params = {"p": patient_id, "c": codes}
    if (await db.execute(_UPDATE, params)).rowcount == 0:  # type: ignore[attr-defined]
        await db.execute(_INSERT, params)
    await db.execute(
        _AUDIT, {"action": "dashboard.cards_set", "eid": str(patient_id), "pid": patient_id}
    )


async def reset_cards(db: AsyncSession, patient_id: UUID) -> None:
    await db.execute(_RESET, {"p": patient_id})
    await db.execute(
        _AUDIT, {"action": "dashboard.cards_reset", "eid": str(patient_id), "pid": patient_id}
    )
