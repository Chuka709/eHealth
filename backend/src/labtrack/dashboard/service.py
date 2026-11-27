"""Home dashboard (Phase 6.3; docs/06 §1): the cards, the values worth a look, and each card's
small numbers - composed from `core/dashboard.py` (rule 6: the app computes nothing)."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from sqlalchemy import Row
from sqlalchemy.ext.asyncio import AsyncSession

from labtrack.core import dashboard as core
from labtrack.core.flags import Flag
from labtrack.core.lab_drafts import LOCAL_ZONE
from labtrack.core.medications import is_current
from labtrack.dashboard import repository as repo

# a value the lab marked critical, or whose printed critical range could not be used
_POSSIBLY_CRITICAL = frozenset({"possible_critical", "critical_unreadable"})


class BadCardsError(ValueError):
    """A repeated test, one not in the catalog, or too many."""


@dataclass(frozen=True)
class Value:
    """A test's latest confirmed value, as printed and in the catalog unit."""

    result_id: UUID
    report_id: UUID
    collected_at: datetime
    raw_value: str
    raw_unit: str | None
    comparator: str | None
    value_text: str | None
    qualitative: str | None
    value: Decimal | None
    unit: str | None
    ref_text: str | None
    ref_low: Decimal | None
    ref_high: Decimal | None
    flag: str
    possibly_critical: bool


@dataclass(frozen=True)
class Card:
    test_code: str
    name_mn: str
    name_en: str
    latest: Value | None
    change: core.Change | None
    # the previous value as ITS result printed it (the change line shows it, not a converted
    # number - a reader compares what the results say)
    previous_printed: tuple[str, str | None] | None
    spark: list[core.Point]
    spark_unit: str | None  # the unit of every spark point (the newest point's)


@dataclass(frozen=True)
class Attention:
    test_code: str
    name_mn: str
    name_en: str
    latest: Value


@dataclass(frozen=True)
class Dashboard:
    custom: bool  # the profile's own list (else the organ's cards)
    cards: list[Card]
    attention: list[Attention]


def _value(row: Row[Any]) -> Value:
    return Value(
        result_id=row.id,
        report_id=row.report_id,
        collected_at=row.collected_at,
        raw_value=row.raw_value,
        raw_unit=row.raw_unit,
        comparator=row.comparator,
        value_text=row.value_text,
        qualitative=row.qualitative,
        value=row.value_canonical,
        unit=row.unit_canonical,
        ref_text=row.ref_text,
        ref_low=row.ref_low_canonical,
        ref_high=row.ref_high_canonical,
        flag=row.flag,
        possibly_critical=bool(_POSSIBLY_CRITICAL & set(row.issues or ())),
    )


def _point(row: Row[Any], possibly_critical: bool = False) -> core.Point:
    return core.Point(
        result_id=str(row.id),
        collected_at=row.collected_at,
        value=row.value_canonical,
        comparator=row.comparator,
        unit=row.unit_canonical,
        flag=cast(Flag, row.flag),
        possibly_critical=possibly_critical,
        lab=getattr(row, "lab_name", None),
    )


async def _taken_levels(db: AsyncSession, patient_id: UUID, now: datetime) -> list[str]:
    """The level tests of the medicines taken on today's Ulaanbaatar date (a day's lag abroad
    at most - it only chooses which level card shows)."""
    today = now.astimezone(LOCAL_ZONE).date()
    return [
        m.test_code
        for m in await repo.linked_medications(db, patient_id)
        if (m.started_on is None or m.started_on <= today)
        and is_current(m.stopped_on, m.planned_end_on, today)
    ]


async def dashboard(db: AsyncSession, patient_id: UUID, now: datetime) -> Dashboard:
    latest_rows = await repo.latest(db, patient_id)
    by_code = {r.test_code: r for r in latest_rows}
    values = {code: _value(r) for code, r in by_code.items()}
    pinned = await repo.pinned(db, patient_id)
    codes = core.card_codes(
        pinned,
        cast(list[core.Organ], await repo.organs(db, patient_id)),
        await _taken_levels(db, patient_id, now),
        by_code,
    )
    names = {t.code: t for t in await repo.tests(db, codes)}
    codes = [c for c in codes if c in names]  # a retired test is not shown
    history: dict[str, list[core.Point]] = defaultdict(list)
    printed: dict[str, tuple[str, str | None]] = {}
    for row in await repo.history(db, patient_id, codes):
        history[row.test_code].append(_point(row))
        printed[str(row.id)] = (row.raw_value, row.raw_unit)
    cards = []
    for code in codes:
        test = names[code]
        found = by_code.get(code)
        # the latest as the history has it (with its lab): the same row, newest first
        latest_point = (
            next((p for p in history[code] if p.result_id == str(found.id)), _point(found))
            if found is not None
            else None
        )
        cards.append(
            Card(
                test_code=code,
                name_mn=test.name_mn,
                name_en=test.name_en,
                latest=values.get(code),
                change=(
                    change := (
                        core.change(latest_point, history[code], test.category)
                        if latest_point is not None
                        else None
                    )
                ),
                previous_printed=(
                    printed.get(change.previous.result_id) if change is not None else None
                ),
                spark=(points := core.spark(history[code])),
                spark_unit=points[-1].unit if points else None,
            )
        )
    # a retired catalog test leaves the cards but a flagged confirmed value of it is still
    # worth a look (safer to show than to hide)
    flagged = core.attention(
        core.Latest(code, _point(r, values[code].possibly_critical)) for code, r in by_code.items()
    )
    attention = [
        Attention(
            test_code=x.test_code,
            name_mn=by_code[x.test_code].name_mn,
            name_en=by_code[x.test_code].name_en,
            latest=values[x.test_code],
        )
        for x in flagged
    ]
    return Dashboard(custom=pinned is not None, cards=cards, attention=attention)


async def set_cards(db: AsyncSession, patient_id: UUID, codes: list[str]) -> None:
    if len(codes) > core.MAX_CARDS or len(set(codes)) != len(codes):
        raise BadCardsError
    # a test retired from the catalog that is already on the list may stay (as the database
    # allows): only newly added ones must be active
    kept = set(await repo.pinned(db, patient_id) or ())
    added = [c for c in codes if c not in kept]
    if added and await repo.active_count(db, added) != len(added):
        raise BadCardsError
    await repo.put_cards(db, patient_id, codes)


async def reset_cards(db: AsyncSession, patient_id: UUID) -> None:
    await repo.reset_cards(db, patient_id)
