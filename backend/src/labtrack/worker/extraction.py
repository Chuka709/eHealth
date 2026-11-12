"""Reading a scanned document into draft lab reports (Phase 4.4; docs/05; Q50).

Runs on the default worker as the uploader (labtrack_app, app.user_id = the uploader), after
the virus scan left the document "queued"; the task gets two ids and nothing else (rule 3).
- "queued" -> "processing" in one update (a second run finds nothing to do).
- A PDF with a text layer in a known lab layout is read locally (no AI, nothing leaves).
  Draft reports and results, the run (what read it, how long, the raw reading without the
  printed name) and an audit row are written in one transaction -> "needs_review".
- Anything else - a scan or photo, an unknown layout - is "failed" with `not_read`: the person
  enters the results by hand (Phase 5) or, with their consent, the AI reads it (Phase 4.5).
- The untrusted PDF is parsed in a child process with memory and CPU limits, killed after
  READ_TIMEOUT_S -> `extraction_timeout` (commit security review); the child failing or any
  other error while reading -> "failed" with `extraction_error`; a page with far more text
  than a report, or a report of more than 500 rows -> `not_read`. A worker killed mid-read
  leaves "processing", which the maintenance sweep turns to "failed" (0032). Logs carry ids
  and error class names only.
- The database briefly away while claiming: the task is retried (Celery autoretry); once
  claimed, any error fails the document (`extraction_error`) - the person adds it again.
"""

import asyncio
import json
import time
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from structlog import get_logger

from labtrack.core.envelope import EnvelopeError
from labtrack.core.lab_drafts import (
    MAX_RESULTS,
    Catalog,
    CatalogTest,
    DraftReport,
    draft_report,
    name_match_score,
)
from labtrack.db.sql import bound_text
from labtrack.documents.service import _aad
from labtrack.extraction.isolated import read_isolated
from labtrack.extraction.types import ReadDocument
from labtrack.keys import decrypt_bytes, get_key_provider
from labtrack.storage import ObjectStore, StorageError, get_store

log = get_logger(__name__)

PIPELINE_VERSION: Final = "p4.4"
READ_TIMEOUT_S: Final = 60.0  # well within the task's soft time limit (120 s)
RAW_OUTPUT_LIMIT: Final = 250_000  # bytes; the column allows 256 KB (0031)

_SET_USER = bound_text("select set_config('app.user_id', :uid, true)")
_CLAIM = bound_text(
    "update documents set status = 'processing', error_code = null"
    " where id = :d and status = 'queued'"
    " returning patient_id, storage_key, mime_type, has_text_layer"
)
_FINISH = bound_text(
    "update documents set status = cast(:s as doc_status), error_code = :e"
    " where id = :d and status = 'processing'"
)
_TESTS = bound_text(
    "select code, canonical_unit, physio_min, physio_max from test_catalog where is_active"
)
_SYNONYMS = bound_text("select synonym_norm, test_code, user_id from test_synonyms")
_UNITS = bound_text("select alias_norm, unit from unit_aliases")
_PROFILE = bound_text("select full_name from patients where id = :p")
_RUN = bound_text(
    "insert into extraction_runs (id, patient_id, document_id, method, reader,"
    " pipeline_version, duration_ms, raw_output, issues)"
    " values (:id, :p, :d, 'local', :reader, :version, :ms, cast(:raw as jsonb),"
    " cast(:issues as text[]))"
)
_REPORT = bound_text(
    "insert into lab_reports (id, patient_id, document_id, extraction_run_id, lab_name,"
    " panel_name, specimen, collected_at, collected_precision, analysed_at, reported_at,"
    " date_ambiguous, name_match_score, has_unconfirmed_critical)"
    " values (:id, :p, :d, :run, :lab, :panel, :specimen, :collected, :precision, :analysed,"
    " :reported, :ambiguous, :score, false)"
)
_RESULT = bound_text(
    "insert into lab_results (report_id, patient_id, position, test_code, raw_name, raw_value,"
    " raw_unit, value_numeric, comparator, value_text, qualitative, ref_text, ref_low,"
    " ref_high, lab_flag, issues, confidence, source_page, source_snippet)"
    " values (:report, :p, :position, :code, :name, :value, :unit, :numeric, :comparator,"
    " :text, :qualitative, :ref_text, :ref_low, :ref_high, :lab_flag, cast(:issues as text[]),"
    " :confidence, :page, :snippet)"
)
_AUDIT = bound_text(
    "select audit_write('document.extract', 'document', cast(:d as text), :p, null)"
)
# a text layer read as printed: as sure as the printout; a row with an issue is less so
_SURE: Final = Decimal("1.00")
_UNSURE: Final = Decimal("0.80")


@dataclass(frozen=True)
class Outcome:
    result: str  # needs_review | not_read | failed | done | missing


@dataclass(frozen=True)
class _Claimed:
    patient_id: UUID
    storage_key: str
    mime_type: str
    has_text_layer: bool | None


async def _begin(conn: AsyncConnection, user_id: UUID) -> None:
    await conn.execute(_SET_USER, {"uid": str(user_id)})


async def _claim(engine: AsyncEngine, user_id: UUID, document_id: UUID) -> _Claimed | None:
    async with engine.connect() as conn, conn.begin():
        await _begin(conn, user_id)
        row = (await conn.execute(_CLAIM, {"d": document_id})).first()
    if row is None:
        return None
    return _Claimed(row.patient_id, row.storage_key, row.mime_type, row.has_text_layer)


async def _finish(
    engine: AsyncEngine, user_id: UUID, document_id: UUID, status: str, code: str | None
) -> None:
    """Never raises: a document it cannot move (access ended mid-read, database away) is left
    "processing" for the maintenance sweep (0032)."""
    try:
        async with engine.connect() as conn, conn.begin():
            await _begin(conn, user_id)
            changed = await conn.execute(_FINISH, {"s": status, "e": code, "d": document_id})
    except Exception as exc:  # logged by class only; the sweep finishes it
        log.warning(
            "document_status_not_set", document_id=str(document_id), error=type(exc).__name__
        )
        return
    if changed.rowcount == 0:
        log.warning("document_status_not_set", document_id=str(document_id))


async def _catalog(conn: AsyncConnection) -> tuple[Catalog, dict[str, str]]:
    tests = {
        r.code: CatalogTest(r.code, r.canonical_unit, r.physio_min, r.physio_max)
        for r in (await conn.execute(_TESTS)).all()
    }
    synonyms: dict[str, str] = {}
    mine: dict[str, str] = {}
    for r in (await conn.execute(_SYNONYMS)).all():  # RLS: the global ones and the user's own
        (mine if r.user_id is not None else synonyms)[r.synonym_norm] = r.test_code
    units = {r.alias_norm: r.unit for r in (await conn.execute(_UNITS)).all()}
    return Catalog(tests=tests, synonyms=synonyms, unit_aliases=units), mine


def _read(data: bytes, claimed: _Claimed) -> ReadDocument | None:
    """Blocking: the parse runs in a child process killed after READ_TIMEOUT_S (isolated.py)."""
    if claimed.mime_type != "application/pdf" or claimed.has_text_layer is False:
        return None  # a scan or photo: no local reader (Q50)
    document = read_isolated(data, timeout=READ_TIMEOUT_S)
    if document is None or any(len(r.results) > MAX_RESULTS for r in document.reports):
        return None
    return document


def _issues(reports: Sequence[DraftReport]) -> list[str]:
    return sorted({i for r in reports for x in r.results for i in x.issues})


def _raw_output(document: ReadDocument) -> str | None:
    raw = json.dumps(document.to_raw_output(), ensure_ascii=False)
    return raw if len(raw.encode()) <= RAW_OUTPUT_LIMIT else None


async def _save(
    conn: AsyncConnection,
    *,
    document_id: UUID,
    claimed: _Claimed,
    document: ReadDocument,
    reports: Sequence[DraftReport],
    score: Decimal | None,
    duration_ms: int,
) -> None:
    run_id = uuid4()
    await conn.execute(
        _RUN,
        {
            "id": run_id,
            "p": claimed.patient_id,
            "d": document_id,
            "reader": document.reader,
            "version": PIPELINE_VERSION,
            "ms": duration_ms,
            "raw": _raw_output(document),
            "issues": _issues(reports),
        },
    )
    for report in reports:
        report_id = uuid4()
        await conn.execute(
            _REPORT,
            {
                "id": report_id,
                "p": claimed.patient_id,
                "d": document_id,
                "run": run_id,
                "lab": report.lab_name,
                "panel": report.panel_name,
                "specimen": report.specimen,
                "collected": report.collected_at,
                "precision": report.collected_precision,
                "analysed": report.analysed_at,
                "reported": report.reported_at,
                "ambiguous": report.date_ambiguous,
                "score": score,
            },
        )
        for x in report.results:
            await conn.execute(_RESULT, _result_params(report_id, claimed.patient_id, x))
    await conn.execute(_AUDIT, {"d": str(document_id), "p": claimed.patient_id})


def _result_params(report_id: UUID, patient_id: UUID, x: Any) -> dict[str, Any]:
    return {
        "report": report_id,
        "p": patient_id,
        "position": x.position,
        "code": x.test_code,
        "name": x.raw_name,
        "value": x.raw_value,
        "unit": x.raw_unit,
        "numeric": x.value_numeric,
        "comparator": x.comparator,
        "text": x.value_text,
        "qualitative": x.qualitative,
        "ref_text": x.ref_text,
        "ref_low": x.ref_low,
        "ref_high": x.ref_high,
        "lab_flag": x.lab_flag,
        "issues": list(x.issues),
        "confidence": _UNSURE if x.issues else _SURE,
        "page": x.source_page,
        "snippet": x.source_snippet,
    }


async def extract(
    engine: AsyncEngine, store: ObjectStore, document_id: UUID, user_id: UUID
) -> Outcome:
    claimed = await _claim(engine, user_id, document_id)
    if claimed is None:
        return Outcome("done")  # not queued (read already, or not yet scanned) or no access
    started = time.monotonic()
    try:
        sealed = await store.get(claimed.storage_key)
        data = await decrypt_bytes(get_key_provider(), sealed, _aad(document_id))
        document = await asyncio.to_thread(_read, data, claimed)
        if document is None:
            await _finish(engine, user_id, document_id, "failed", "not_read")
            return Outcome("not_read")
        async with engine.connect() as conn, conn.begin():
            await _begin(conn, user_id)
            catalog, mine = await _catalog(conn)
            profile = (await conn.execute(_PROFILE, {"p": claimed.patient_id})).scalar_one()
            score = name_match_score(document.identity, profile)
            reports = [draft_report(r, catalog, mine, name_score=score) for r in document.reports]
            await _save(
                conn,
                document_id=document_id,
                claimed=claimed,
                document=document,
                reports=reports,
                score=score,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            await conn.execute(_FINISH, {"s": "needs_review", "e": None, "d": document_id})
    except TimeoutError:
        log.warning("document_extraction_timeout", document_id=str(document_id))
        await _finish(engine, user_id, document_id, "failed", "extraction_timeout")
        return Outcome("failed")
    except (StorageError, EnvelopeError):
        log.warning("document_extraction_unreadable", document_id=str(document_id))
        await _finish(engine, user_id, document_id, "failed", "unreadable")
        return Outcome("failed")
    except Exception as exc:
        # the class name only: the exception text may quote the document (rule 3)
        log.error(  # noqa: TRY400 - no traceback, it may quote the document
            "document_extraction_failed", document_id=str(document_id), error=type(exc).__name__
        )
        await _finish(engine, user_id, document_id, "failed", "extraction_error")
        return Outcome("failed")
    log.info("document_extracted", document_id=str(document_id), reports=len(reports))
    return Outcome("needs_review")


def run_sync(app_url: str, document_id: str, user_id: str) -> str:
    async def main() -> str:
        engine = create_async_engine(app_url, hide_parameters=True, pool_reset_on_return="rollback")
        try:
            outcome = await extract(engine, get_store(), UUID(document_id), UUID(user_id))
            return outcome.result
        finally:
            await engine.dispose()

    return asyncio.run(main())
