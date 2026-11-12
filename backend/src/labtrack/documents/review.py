"""The person's review of a draft lab report (Phase 5.3; docs/06 §4, docs/08 "Хянах"; rule 4).

Every edit is recomputed in `core` exactly as a reading is (rule 6): the row's value, unit and
ranges as the person typed them, the test they picked (which becomes their own synonym for
the printed name), flags, catalog-unit values and issues; the report's rows are all redone
when its date changes (their date issues follow). `acknowledged`: the issues the person
looked at and kept - only issues the row still has; a new text, another test or another
date drops them (they were about what was there before). Some issues are never just accepted:
a missing, ambiguous or future date is corrected by choosing the date (H3, H30); a possibly
critical, unreadable-critical, implausible or corrected-critical value and a name that does
not fit the profile are accepted one at a time, each audited apart (H1, H2, H5). A row read as
critical keeps what was read (`read_value`, `read_critical_text`) and gets `critical_edited`
when an edit makes it no longer critical - the banner stays until it is accepted. Rejecting a
report, or deleting a row, that may hold a critical value needs `critical_seen`. Every change
locks the report row first (no edit lands in a report being confirmed). Confirming needs a
date and every row's issues acknowledged (also checked by the database - 0036). Nothing here
suggests a value; audits carry ids and field names only.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Final
from uuid import UUID, uuid4

from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from labtrack import consents
from labtrack.api.errors import AppError
from labtrack.core.lab_drafts import (
    Catalog,
    DraftReport,
    DraftResult,
    Precision,
    day_start,
    redraft_result,
    report_issues,
    with_history,
)
from labtrack.core.text import normalize_name
from labtrack.db.sql import bound_text
from labtrack.documents.catalog import load_catalog, load_prior, patient_sex
from labtrack.extraction.types import ReadResult
from labtrack.records.repository import audit

MAX_ROWS: Final = 500
# what a reader found doubtful about the printed text: kept while that text is unchanged
_READER_ISSUES: Final = frozenset({"not_in_source", "low_confidence", "truncated"})
# corrected by choosing the date, never accepted as they are
NOT_ACCEPTED: Final = frozenset({"date_missing", "date_ambiguous", "date_future"})
# accepted one at a time, each audited apart
ONE_AT_A_TIME: Final = frozenset(
    {
        "possible_critical",
        "critical_unreadable",
        "implausible",
        "critical_edited",
        "name_mismatch",
        "name_missing",
    }
)
_NAME_ISSUES: Final = frozenset({"name_mismatch", "name_missing"})
# the report's own issues (on every row): accepted for the report, never row by row
REPORT_ISSUES: Final = frozenset({*_NAME_ISSUES, "date_old", "date_inconsistent"})
_CRITICAL_FLAGS: Final = frozenset({"critical_low", "critical_high"})

_REPORT = bound_text(
    "select id, patient_id, document_id, status::text as status, specimen, collected_at,"
    " collected_precision, date_ambiguous, analysed_at, reported_at, name_match_score,"
    " has_unconfirmed_critical, extraction_run_id, source"
    " from lab_reports where id = :r and patient_id = :p"
)
# the draft locked for this change (RLS: drafts of the caller's writable profiles only)
_LOCK = bound_text(
    "select id from lab_reports where id = :r and patient_id = :p and status = 'needs_review'"
    " for update"
)
_ROWS = bound_text(
    "select id, position, test_code, raw_name, raw_value, raw_unit, ref_text, critical_text,"
    " lab_flag, source_page, source_snippet, issues, acknowledged, flag::text as flag,"
    " read_was_critical"
    " from lab_results where report_id = :r and patient_id = :p order by position"
)
_UPDATE_ROW = bound_text(
    "update lab_results set test_code = :code, raw_value = :value, raw_unit = :unit,"
    " value_numeric = :numeric, comparator = :comparator, value_text = :text,"
    " qualitative = :qualitative, ref_text = :ref_text, ref_low = :ref_low,"
    " ref_high = :ref_high, critical_text = :critical_text, critical_low = :critical_low,"
    " critical_high = :critical_high, unit_canonical = :unit_canonical,"
    " value_canonical = :value_canonical, ref_low_canonical = :ref_low_canonical,"
    " ref_high_canonical = :ref_high_canonical, critical_low_canonical = :critical_low_canonical,"
    " critical_high_canonical = :critical_high_canonical, flag = cast(:flag as result_flag),"
    " flag_source = :flag_source, flag_mismatch = :flag_mismatch,"
    " issues = cast(:issues as text[]), acknowledged = cast(:acknowledged as text[]),"
    " confidence = :confidence, edited_by_user = edited_by_user or :edited,"
    # what was read, kept at the first change of the text (old values on the right)
    " read_value = case when :changed then coalesce(read_value, raw_value) else read_value end,"
    " read_critical_text = case when :changed and read_value is null then critical_text"
    " else read_critical_text end,"
    " read_was_critical = case when :changed then coalesce(read_was_critical, :was_critical)"
    " else read_was_critical end"
    " where id = :id and patient_id = :p"
)
_INSERT_ROW = bound_text(
    "insert into lab_results (id, report_id, patient_id, position, raw_name, raw_value)"
    " values (:id, :r, :p, :position, :name, :value)"
)
_DELETE_ROW = bound_text(
    "delete from lab_results where id = :id and report_id = :r and patient_id = :p"
)
_UPDATE_REPORT = bound_text(
    "update lab_reports set collected_at = :collected,"
    " collected_precision = :precision, date_ambiguous = false"
    " where id = :r and patient_id = :p"
)
_LAB = bound_text("update lab_reports set lab_name = :lab where id = :r and patient_id = :p")
_CRITICAL = bound_text(
    "update lab_reports set has_unconfirmed_critical = exists (select 1 from lab_results x"
    " where x.report_id = :r and (x.flag in ('critical_low', 'critical_high')"
    " or 'possible_critical' = any(x.issues)"
    # a corrected critical reading: until the person accepts the correction
    " or ('critical_edited' = any(x.issues) and not 'critical_edited' = any(x.acknowledged))))"
    " where id = :r and patient_id = :p"
)
_SYNONYM = bound_text(
    "insert into test_synonyms (test_code, synonym, synonym_norm, user_id)"
    " values (:c, :s, :k, app_user_id()) on conflict do nothing"
)
_CONFIRM = bound_text("select confirm_lab_report(:r)")
_REJECT = bound_text("select reject_lab_report(:r)")
_SURE: Final = Decimal("1.00")
_UNSURE: Final = Decimal("0.80")


@dataclass(frozen=True)
class RowEdit:
    """What the person changed on a row; None leaves a field as it is."""

    raw_value: str | None = None
    raw_unit: str | None = None
    ref_text: str | None = None
    critical_text: str | None = None
    test_code: str | None = None
    acknowledge: tuple[str, ...] = ()
    clear: frozenset[str] = frozenset()  # fields set back to empty: unit, ref, critical


@dataclass(frozen=True)
class ReportEdit:
    lab_name: str | None = None
    collected_at: datetime | None = None
    collected_precision: Precision | None = None
    acknowledge: tuple[str, ...] = ()  # report issues (dates, name) on every row


@dataclass(frozen=True)
class _Row:
    id: UUID
    position: int
    picked: str | None
    read: ReadResult
    acknowledged: frozenset[str]
    edited: bool
    changed: bool = False  # the printed text changed in this edit
    was_critical: bool = False  # read as critical (or possibly) before any edit


async def _report(db: AsyncSession, patient_id: UUID, report_id: UUID) -> Any:
    report = (await db.execute(_REPORT, {"r": report_id, "p": patient_id})).first()
    if report is None:
        raise AppError(404, "review.not_found")
    if report.status != "needs_review":
        raise AppError(409, "review.not_draft")
    if (await db.execute(_LOCK, {"r": report_id, "p": patient_id})).first() is None:
        raise AppError(409, "review.not_draft")  # confirmed or rejected meanwhile
    # as it is now that it is locked
    return (await db.execute(_REPORT, {"r": report_id, "p": patient_id})).one()


def _is_critical(flag: str | None, issues: Iterable[str]) -> bool:
    return flag in _CRITICAL_FLAGS or bool({"possible_critical", "critical_edited"} & set(issues))


async def _rows(db: AsyncSession, patient_id: UUID, report_id: UUID) -> list[Any]:
    return list((await db.execute(_ROWS, {"r": report_id, "p": patient_id})).all())


def _kept_reader_issues(row: Any, read: ReadResult) -> tuple[str, ...]:
    """A reader's doubts hold while the printed text is as it was read."""
    same = (row.raw_value, row.raw_unit, row.ref_text, row.critical_text) == (
        read.raw_value, read.raw_unit, read.ref_text, read.critical_text,
    )  # fmt: skip
    return tuple(i for i in row.issues if i in _READER_ISSUES) if same else ()


def _as_read(row: Any, edit: RowEdit | None = None) -> tuple[ReadResult, bool]:
    e = edit or RowEdit()

    def pick(field: str, new: str | None, old: str | None) -> str | None:
        if field in e.clear:
            return None
        return new.strip() or None if new is not None else old

    value = e.raw_value.strip() if e.raw_value is not None else row.raw_value
    read = ReadResult(
        raw_name=row.raw_name,
        raw_value=value or row.raw_value,
        raw_unit=pick("raw_unit", e.raw_unit, row.raw_unit),
        ref_text=pick("ref_text", e.ref_text, row.ref_text),
        lab_flag=row.lab_flag,
        page=row.source_page,
        snippet=row.source_snippet or "",
        critical_text=pick("critical_text", e.critical_text, row.critical_text),
    )
    read = replace(read, issues=_kept_reader_issues(row, read))
    changed = (read.raw_value, read.raw_unit, read.ref_text, read.critical_text) != (
        row.raw_value, row.raw_unit, row.ref_text, row.critical_text,
    )  # fmt: skip
    return read, changed


def _params(row: _Row, draft: DraftResult, patient_id: UUID, ack: Iterable[str]) -> dict[str, Any]:
    issues = list(draft.issues)
    if row.was_critical and not _is_critical(draft.flag, issues):
        issues.append("critical_edited")  # read as critical: the edit must be accepted
    acknowledged = sorted(set(ack) & set(issues))
    return {
        "id": row.id,
        "p": patient_id,
        "code": draft.test_code,
        "value": draft.raw_value,
        "unit": draft.raw_unit,
        "numeric": draft.value_numeric,
        "comparator": draft.comparator,
        "text": draft.value_text,
        "qualitative": draft.qualitative,
        "ref_text": draft.ref_text,
        "ref_low": draft.ref_low,
        "ref_high": draft.ref_high,
        "critical_text": draft.critical_text,
        "critical_low": draft.critical_low,
        "critical_high": draft.critical_high,
        "unit_canonical": draft.unit_canonical,
        "value_canonical": draft.value_canonical,
        "ref_low_canonical": draft.ref_low_canonical,
        "ref_high_canonical": draft.ref_high_canonical,
        "critical_low_canonical": draft.critical_low_canonical,
        "critical_high_canonical": draft.critical_high_canonical,
        "flag": draft.flag,
        "flag_source": draft.flag_source,
        "flag_mismatch": draft.flag_mismatch,
        "issues": issues,
        "acknowledged": acknowledged,
        # how sure the reading was - an accepted issue does not make it surer
        "confidence": _UNSURE if issues else _SURE,
        "edited": row.edited,
        "changed": row.changed,
        "was_critical": row.was_critical,
    }


async def _redo(
    db: AsyncSession,
    patient_id: UUID,
    report: Any,
    rows: Sequence[_Row],
    *,
    catalog: Catalog,
    mine: Mapping[str, str],
    extra_ack: Mapping[UUID, Iterable[str]],
) -> None:
    """Recompute and store these rows of the report, then the report's critical mark."""
    issues = report_issues(
        collected_at=report.collected_at,
        collected_precision=report.collected_precision,
        date_ambiguous=report.date_ambiguous,
        analysed_at=report.analysed_at,
        reported_at=report.reported_at,
        name_score=report.name_match_score,
        # a reading checks the printed name; a report typed from a scan or photo is
        # checked by the person (the name on it is theirs to confirm - H2); a paper result
        # typed in with no file has nothing to check
        read_from_document=report.document_id is not None,
        now=datetime.now(UTC),
    )
    sex = await patient_sex(db, patient_id)
    drafts = [
        redraft_result(
            r.position,
            r.read,
            specimen=report.specimen,
            catalog=catalog,
            user_synonyms=mine,
            report_issues=issues,
            sex=sex,
            picked_test=r.picked,
        )
        for r in rows
    ]
    whole = DraftReport(
        lab_name=None, panel_name=None, specimen=report.specimen,
        collected_at=report.collected_at, collected_precision=report.collected_precision,
        analysed_at=report.analysed_at, reported_at=report.reported_at,
        date_ambiguous=report.date_ambiguous, results=tuple(drafts),
    )  # fmt: skip
    prior = await load_prior(db, patient_id, [whole], report_id=report.id)
    done = with_history(whole, prior, catalog).results
    for row, draft in zip(rows, done, strict=True):
        ack = {*row.acknowledged, *extra_ack.get(row.id, ())}
        await db.execute(_UPDATE_ROW, _params(row, draft, patient_id, ack))
    await db.execute(_CRITICAL, {"r": report.id, "p": patient_id})
    if report.source == "typed":  # may have become critical by this change (H5)
        await db.execute(_NOTIFY_TYPED, {"r": report.id})


def _row(stored: Any, edit: RowEdit | None = None, *, new_date: bool = False) -> _Row:
    read, changed = _as_read(stored, edit)
    picked = (edit.test_code if edit and edit.test_code else None) or stored.test_code
    other_test = bool(edit and edit.test_code and edit.test_code != stored.test_code)
    # a new text or test drops what was accepted about the old one; a new date all but the
    # name (dates, delta and duplicate checks were about the old date)
    if changed or other_test:
        acknowledged: frozenset[str] = frozenset()
    elif new_date:
        acknowledged = frozenset(stored.acknowledged) & _NAME_ISSUES
    else:
        acknowledged = frozenset(stored.acknowledged)
    was = stored.read_was_critical
    was_critical = was if was is not None else _is_critical(stored.flag, stored.issues)
    return _Row(
        stored.id, stored.position, picked, read, acknowledged, changed or other_test,
        changed=changed, was_critical=was_critical,
    )  # fmt: skip


def _check_ack(requested: Iterable[str], issues: Iterable[str]) -> None:
    asked = set(requested)
    if not asked <= set(issues) or asked & NOT_ACCEPTED:
        raise AppError(422, "review.issue_not_open")
    if asked & ONE_AT_A_TIME and len(asked) > 1:
        raise AppError(422, "review.acknowledge_one")


async def edit_result(
    db: AsyncSession, patient_id: UUID, report_id: UUID, result_id: UUID, edit: RowEdit
) -> None:
    report = await _report(db, patient_id, report_id)
    stored = next((r for r in await _rows(db, patient_id, report_id) if r.id == result_id), None)
    if stored is None:
        raise AppError(404, "review.not_found")
    catalog, mine = await load_catalog(db)
    if edit.test_code is not None and edit.test_code not in catalog.tests:
        raise AppError(422, "review.unknown_test")
    new_text = (edit.raw_value, edit.raw_unit, edit.ref_text, edit.critical_text, edit.test_code)
    if edit.acknowledge and (any(t is not None for t in new_text) or edit.clear):
        raise AppError(422, "review.acknowledge_alone")  # accept what is seen, not new text
    if set(edit.acknowledge) & REPORT_ISSUES:
        raise AppError(422, "review.issue_not_open")  # the report's, accepted for the report
    _check_ack(edit.acknowledge, stored.issues)
    row = _row(stored, edit)
    await _redo(
        db, patient_id, report, [row], catalog=catalog, mine=mine,
        extra_ack={row.id: edit.acknowledge},
    )  # fmt: skip
    if edit.test_code and edit.test_code != stored.test_code:
        # the person's pick becomes their own synonym for this printed name (docs/05)
        key = normalize_name(stored.raw_name)
        if key:
            await db.execute(_SYNONYM, {"c": edit.test_code, "s": stored.raw_name[:200], "k": key})
    fields = [f for f in ("raw_value", "raw_unit", "ref_text", "critical_text", "test_code")
              if getattr(edit, f) is not None] + sorted(edit.clear)  # fmt: skip
    if edit.acknowledge:
        fields.append("acknowledged")
    flagged = sorted(set(edit.acknowledge) & ONE_AT_A_TIME)
    action = "result.accept_flagged" if flagged else "result.edit"
    await audit(db, action, "lab_result", result_id, patient_id, fields + flagged)


async def add_result(
    db: AsyncSession,
    patient_id: UUID,
    report_id: UUID,
    *,
    new_id: UUID,
    raw_name: str,
    edit: RowEdit,
) -> None:
    report = await _report(db, patient_id, report_id)
    rows = await _rows(db, patient_id, report_id)
    if len(rows) >= MAX_ROWS:
        raise AppError(409, "review.too_many_rows")
    if not edit.raw_value or not edit.raw_value.strip() or not raw_name.strip():
        raise AppError(422, "validation")
    catalog, mine = await load_catalog(db)
    if edit.test_code is not None and edit.test_code not in catalog.tests:
        raise AppError(422, "review.unknown_test")
    position = max((r.position for r in rows), default=-1) + 1
    if position >= MAX_ROWS:  # rows deleted before: positions are not reused
        raise AppError(409, "review.too_many_rows")
    await db.execute(
        _INSERT_ROW,
        {"id": new_id, "r": report_id, "p": patient_id, "position": position,
         "name": raw_name.strip()[:200], "value": edit.raw_value.strip()[:200]},
    )  # fmt: skip
    stored = next(r for r in await _rows(db, patient_id, report_id) if r.id == new_id)
    # typed in by the person: nothing was read, so nothing is kept as read
    row = replace(_row(stored, replace(edit, acknowledge=())), edited=True, changed=False)
    await _redo(db, patient_id, report, [row], catalog=catalog, mine=mine, extra_ack={})
    await audit(db, "result.add", "lab_result", new_id, patient_id, None)


async def delete_result(
    db: AsyncSession,
    patient_id: UUID,
    report_id: UUID,
    result_id: UUID,
    *,
    critical_seen: bool = False,
) -> None:
    await _report(db, patient_id, report_id)
    stored = next((r for r in await _rows(db, patient_id, report_id) if r.id == result_id), None)
    if stored is None:
        raise AppError(404, "review.not_found")
    critical = _is_critical(stored.flag, stored.issues) or bool(stored.read_was_critical)
    if critical and not critical_seen:
        raise AppError(409, "review.critical_needs_ack")  # the banner must not just vanish
    await db.execute(_DELETE_ROW, {"id": result_id, "r": report_id, "p": patient_id})
    await db.execute(_CRITICAL, {"r": report_id, "p": patient_id})
    action = "result.delete_critical" if critical else "result.delete"
    await audit(db, action, "lab_result", result_id, patient_id, None)


async def edit_report(
    db: AsyncSession, patient_id: UUID, report_id: UUID, edit: ReportEdit
) -> None:
    report = await _report(db, patient_id, report_id)
    stored = await _rows(db, patient_id, report_id)
    if not set(edit.acknowledge) <= REPORT_ISSUES:
        raise AppError(422, "review.issue_not_open")
    _check_ack(edit.acknowledge, {i for r in stored for i in r.issues})
    if edit.acknowledge and edit.collected_at is not None:
        raise AppError(422, "review.acknowledge_alone")
    if (edit.collected_at is None) != (edit.collected_precision is None):
        raise AppError(422, "validation")  # a day or a minute: always said (H30)
    if edit.collected_at is not None:
        if edit.collected_at.tzinfo is None:
            raise AppError(422, "validation")
        await db.execute(
            _UPDATE_REPORT,
            {"r": report_id, "p": patient_id,
             "collected": _moment(edit.collected_at, edit.collected_precision),
             "precision": edit.collected_precision},
        )  # fmt: skip
    if edit.lab_name is not None:
        await db.execute(_LAB, {"lab": edit.lab_name.strip()[:200] or None, "r": report_id,
                                "p": patient_id})  # fmt: skip
    report = await _report(db, patient_id, report_id)
    catalog, mine = await load_catalog(db)
    rows = [_row(r, new_date=edit.collected_at is not None) for r in stored]
    await _redo(
        db, patient_id, report, rows, catalog=catalog, mine=mine,
        extra_ack={r.id: edit.acknowledge for r in rows},
    )  # fmt: skip
    fields = [f for f in ("lab_name", "collected_at") if getattr(edit, f) is not None]
    if edit.acknowledge:
        fields.append("acknowledged")
    flagged = sorted(set(edit.acknowledge) & ONE_AT_A_TIME)
    action = "report.accept_name" if flagged else "report.edit"
    await audit(db, action, "lab_report", report_id, patient_id, fields + flagged)


def _pg(exc: DBAPIError) -> object:
    return getattr(exc.orig, "__cause__", None) or exc.orig


def _moment(at: datetime, precision: Precision | None) -> datetime:
    return day_start(at) if precision == "day" else at


def _status_error(exc: DBAPIError) -> AppError:
    text = str(getattr(exc.orig, "args", [""])[0] if exc.orig else "")
    for marker, code in (
        ("report has open issues", "review.open_issues"),
        ("report has no date", "review.no_date"),  # missing, ambiguous or in the future
        ("report has no results", "review.no_results"),
        ("report not a draft", "review.not_draft"),
        ("report not found", "review.not_found"),
    ):
        if marker in text:
            return AppError(404 if code == "review.not_found" else 409, code)
    raise exc


async def open_issue_count(db: AsyncSession, patient_id: UUID, report_id: UUID) -> int:
    rows = await _rows(db, patient_id, report_id)
    return sum(1 for r in rows if not set(r.issues) <= set(r.acknowledged))


async def confirm(db: AsyncSession, patient_id: UUID, report_id: UUID) -> None:
    await _report(db, patient_id, report_id)
    if await open_issue_count(db, patient_id, report_id):
        raise AppError(409, "review.open_issues")
    try:
        async with db.begin_nested():
            await db.execute(_CONFIRM, {"r": report_id})
    except DBAPIError as exc:
        raise _status_error(exc) from None


async def reject(
    db: AsyncSession, patient_id: UUID, report_id: UUID, *, critical_seen: bool = False
) -> None:
    report = await _report(db, patient_id, report_id)
    if report.has_unconfirmed_critical:
        if not critical_seen:
            raise AppError(409, "review.critical_needs_ack")  # H5: never silently dropped
        await audit(db, "report.reject_critical", "lab_report", report_id, patient_id, None)
    try:
        async with db.begin_nested():
            await db.execute(_REJECT, {"r": report_id})
    except DBAPIError as exc:
        raise _status_error(exc) from None


# --- typed in by hand, and the wrong profile (Phase 5.4) ---------------------------------------

_NEW_REPORT = bound_text(
    "insert into lab_reports (id, patient_id, document_id, lab_name, collected_at,"
    " collected_precision) values (:r, :p, :d, :lab, :at, :precision)"
)
_DOCUMENT = bound_text(
    "select status::text as status from documents where id = :d and patient_id = :p"
)
_DOC_REPORTS = bound_text(
    "select id from lab_reports where document_id = :d and patient_id = :p"
    " and status = 'needs_review'"
)
_MOVE = bound_text("select move_document(:d, :t)")
_NOTIFY_READ = bound_text("select notify_document_read(:d)")
_NOTIFY_TYPED = bound_text("select notify_report_critical(:r)")
_CAN_WRITE = bound_text("select coalesce(can_write_patient(:p), false)")
MAX_TYPED_ROWS: Final = 100


@dataclass(frozen=True)
class TypedRow:
    raw_name: str
    edit: RowEdit


async def create_manual(
    db: AsyncSession,
    patient_id: UUID,
    *,
    report_id: UUID,
    document_id: UUID | None,
    lab_name: str | None,
    collected_at: datetime,
    collected_precision: Precision,
    rows: Sequence[TypedRow],
) -> None:
    """A report the person types in (a scan or photo that is not read - Q50, or a paper
    result): a draft like any other, checked by `core` row by row and confirmed the same way."""
    if not rows or len(rows) > MAX_TYPED_ROWS:
        raise AppError(422, "validation")
    if collected_at.tzinfo is None:
        raise AppError(422, "validation")
    if document_id is not None:
        doc = (await db.execute(_DOCUMENT, {"d": document_id, "p": patient_id})).first()
        if doc is None:
            raise AppError(404, "document.not_found")
        if doc.status not in {"needs_review", "failed"}:
            raise AppError(409, "document.not_ready")
    try:
        async with db.begin_nested():
            await db.execute(
                _NEW_REPORT,
                {"r": report_id, "p": patient_id, "d": document_id,
                 "lab": lab_name.strip()[:200] if lab_name and lab_name.strip() else None,
                 "at": _moment(collected_at, collected_precision),
                 "precision": collected_precision},
            )  # fmt: skip
    except DBAPIError as exc:  # the document moved or went meanwhile
        if getattr(_pg(exc), "sqlstate", None) == "23503":
            raise AppError(404, "document.not_found") from None
        raise
    await audit(db, "report.create", "lab_report", report_id, patient_id, None)
    for row in rows:
        await add_result(
            db, patient_id, report_id, new_id=uuid4(), raw_name=row.raw_name, edit=row.edit
        )
    # possibly critical: the owner and alerting caregivers were told by each row's change


async def move_document(
    db: AsyncSession, patient_id: UUID, document_id: UUID, target_id: UUID
) -> None:
    """ "Wrong profile": the document and its drafts go to the other profile, where they are
    checked again (no accepted issue moves along; the printed name is unchecked there)."""
    # the new profile's gate as for any route on it (a minor's consents - Q9), after access
    access = await db.execute(_CAN_WRITE, {"p": target_id})
    if not access.scalar_one():
        raise AppError(403, "review.move_target")
    await consents.require_for_patient(db, target_id)
    try:
        async with db.begin_nested():
            await db.execute(_MOVE, {"d": document_id, "t": target_id})
    except DBAPIError as exc:
        text = str(getattr(exc.orig, "args", [""])[0] if exc.orig else "")
        if "confirmed reports" in text:
            raise AppError(409, "review.move_confirmed") from None
        if "document not ready" in text:
            raise AppError(409, "document.not_ready") from None
        if "too many documents" in text:
            raise AppError(409, "document.too_many") from None
        if getattr(_pg(exc), "sqlstate", None) == "23505":  # the same file there already
            raise AppError(409, "document.conflict") from None
        if "target not allowed" in text:
            raise AppError(403, "review.move_target") from None
        if "document not found" in text:
            raise AppError(404, "document.not_found") from None
        raise
    catalog, mine = await load_catalog(db)
    for (rid,) in (await db.execute(_DOC_REPORTS, {"d": document_id, "p": target_id})).all():
        report = await _report(db, target_id, rid)
        rows = [_row(r) for r in await _rows(db, target_id, rid)]
        await _redo(db, target_id, report, rows, catalog=catalog, mine=mine, extra_ack={})
    # the new profile is told as for a read document (the old one's notices went - 0037);
    # typed-in drafts of it were told by their recomputation above
    status = (await db.execute(_DOCUMENT, {"d": document_id, "p": target_id})).scalar_one()
    if status == "needs_review":
        await db.execute(_NOTIFY_READ, {"d": document_id})
