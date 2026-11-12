"""Reading a scanned document into draft lab reports (Phase 4.4; docs/05; Q50).

Runs on the default worker as the uploader (labtrack_app, app.user_id = the uploader), after
the virus scan left the document "queued"; the task gets two ids and nothing else (rule 3).
- "queued" -> "processing" in one update (a second run finds nothing to do).
- A PDF with a text layer in a known lab layout is read locally (no AI, nothing leaves).
  Draft reports and results, the run (what read it, how long, the raw reading without the
  printed name) and an audit row are written in one transaction -> "needs_review".
- A text PDF of no known layout goes to the AI (Phase 4.5, Q50) when AI reading is on, the
  person gave `ai_processing` + `cross_border` (and, for a child's profile, the profile's own
  consent), and their daily cap is not reached: only the text `deidentify` leaves, through
  Valkey to the AI worker (`ai_handoff`); the document stays "processing" until `save_ai`
  stores the answer as a draft like a local reading (method "ai"). Anything else - a scan or
  photo, an unknown layout without AI - is "failed" with `not_read`: entered by hand (Phase 5).
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
import secrets
import time
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import timedelta
from decimal import Decimal
from typing import Any, Final
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from structlog import get_logger

from labtrack.config import get_settings
from labtrack.consents import AI_EXTRACTION, VERSIONS
from labtrack.core.envelope import EnvelopeError
from labtrack.core.lab_drafts import (
    MAX_RESULTS,
    Catalog,
    CatalogTest,
    DraftReport,
    Prior,
    draft_report,
    name_match_score,
    with_history,
)
from labtrack.core.ranges import Sex
from labtrack.db.sql import bound_text
from labtrack.documents.service import _aad
from labtrack.extraction.deidentify import deidentify
from labtrack.extraction.isolated import Reading, from_json, read_isolated
from labtrack.extraction.llm import PROMPT_VERSION
from labtrack.extraction.types import PrintedIdentity, ReadDocument
from labtrack.extraction.verify import check_against_source
from labtrack.keys import decrypt_bytes, get_key_provider
from labtrack.storage import ObjectStore, StorageError, get_store
from labtrack.worker.ai_handoff import Handoff, ValkeyHandoff

log = get_logger(__name__)

PIPELINE_VERSION: Final = "p4.5"
MIN_AI_TEXT: Final = 40  # characters left after de-identification worth sending
AI_WAIT: Final = timedelta(minutes=4)  # the AI worker's answer, polled for until then
AI_ERRORS: Final = frozenset(
    {
        "ai_unavailable",
        "ai_rejected",
        "ai_refused",
        "ai_incomplete",
        "ai_empty",
        "ai_failed",
        "ai_input_missing",
        "ai_unconfigured",
    }
)
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
    "select code, canonical_unit, physio_min, physio_max, delta_check_pct from test_catalog"
    " where is_active"
)
_FACTORS = bound_text(
    "select c.test_code, c.from_unit, c.factor from unit_conversions c"
    " join test_catalog t on t.code = c.test_code and t.canonical_unit = c.to_unit"
)
# the profile's values of these tests in the catalog unit, confirmed or another draft still
# waiting (duplicate, delta checks); a value with a comparator is never compared
_PRIOR = bound_text(
    "select x.test_code, x.collected_at, x.value_canonical, r.status = 'confirmed' as confirmed"
    " from lab_results x"
    " join lab_reports r on r.id = x.report_id and r.status in ('confirmed', 'needs_review')"
    " where x.patient_id = :p and x.value_canonical is not null and x.collected_at is not null"
    " and x.comparator is null and x.test_code = any(cast(:codes as text[]))"
    # never this document's own rows (a reading of it again)
    " and r.document_id is distinct from :d"
)
_NOTIFY = bound_text("select notify_document_read(:d)")
_SYNONYMS = bound_text("select synonym_norm, test_code, user_id from test_synonyms")
_UNITS = bound_text("select alias_norm, unit from unit_aliases")
_PROFILE = bound_text("select full_name, sex::text as sex from patients where id = :p")
_RUN = bound_text(
    "insert into extraction_runs (id, patient_id, document_id, method, reader, prompt_version,"
    " pipeline_version, input_tokens, output_tokens, duration_ms, raw_output, issues)"
    " values (:id, :p, :d, :method, :reader, :prompt, :version, :tokens_in, :tokens_out, :ms,"
    " cast(:raw as jsonb), cast(:issues as text[]))"
)
_PROCESSING = bound_text("select patient_id from documents where id = :d and status = 'processing'")
_AI_CONSENT = bound_text("select ai_consent_ok(:p, cast(:v as jsonb))")
_OWN_CONSENTS = bound_text(
    "select distinct on (kind) kind, version, granted from consents"
    " where user_id = app_user_id() and patient_id is null"
    " and kind in ('ai_processing', 'cross_border') order by kind, id desc"
)
_AI_REQUEST = bound_text(
    "insert into ai_requests (document_id, patient_id, requested_by, nonce, name_match_score,"
    " name_printed, sent_text) values (:d, :p, app_user_id(), :n, :score, :printed, :text)"
)
_AI_REQUEST_FIND = bound_text(
    "select patient_id, nonce, name_match_score, name_printed, sent_text,"
    " created_at > now() - make_interval(secs => :wait) as waiting"
    " from ai_requests where document_id = :d"
)
_AI_REQUEST_DONE = bound_text("delete from ai_requests where document_id = :d")
_REPORT = bound_text(
    "insert into lab_reports (id, patient_id, document_id, extraction_run_id, lab_name,"
    " panel_name, specimen, collected_at, collected_precision, analysed_at, reported_at,"
    " date_ambiguous, name_match_score, has_unconfirmed_critical)"
    " values (:id, :p, :d, :run, :lab, :panel, :specimen, :collected, :precision, :analysed,"
    " :reported, :ambiguous, :score, :critical)"
)
_RESULT = bound_text(
    "insert into lab_results (report_id, patient_id, position, test_code, raw_name, raw_value,"
    " raw_unit, value_numeric, comparator, value_text, qualitative, ref_text, ref_low,"
    " ref_high, critical_text, critical_low, critical_high, lab_flag, issues, confidence,"
    " source_page, source_snippet, unit_canonical, value_canonical, ref_low_canonical,"
    " ref_high_canonical, critical_low_canonical, critical_high_canonical, flag, flag_source,"
    " flag_mismatch)"
    " values (:report, :p, :position, :code, :name, :value, :unit, :numeric, :comparator,"
    " :text, :qualitative, :ref_text, :ref_low, :ref_high, :critical_text, :critical_low,"
    " :critical_high, :lab_flag, cast(:issues as text[]), :confidence, :page, :snippet,"
    " :unit_canonical, :value_canonical, :ref_low_canonical, :ref_high_canonical,"
    " :critical_low_canonical, :critical_high_canonical, cast(:flag as result_flag),"
    " :flag_source, :flag_mismatch)"
)
_AUDIT = bound_text(
    "select audit_write('document.extract', 'document', cast(:d as text), :p, null)"
)
# a text layer read as printed: as sure as the printout; a row with an issue is less so
_SURE: Final = Decimal("1.00")
_UNSURE: Final = Decimal("0.80")


@dataclass(frozen=True)
class Outcome:
    result: str  # needs_review | not_read | sent_to_ai | waiting | failed | done


@dataclass(frozen=True)
class _Method:
    """What read it: "local" (a known layout) or "ai" (with the model's token counts)."""

    name: str = "local"
    prompt_version: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


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
    factors: dict[str, dict[str, Decimal]] = {}
    for r in (await conn.execute(_FACTORS)).all():
        factors.setdefault(r.test_code, {})[r.from_unit] = r.factor
    tests = {
        r.code: CatalogTest(
            r.code,
            r.canonical_unit,
            r.physio_min,
            r.physio_max,
            factors=factors.get(r.code, {}),
            delta_check_pct=r.delta_check_pct,
        )
        for r in (await conn.execute(_TESTS)).all()
    }
    synonyms: dict[str, str] = {}
    mine: dict[str, str] = {}
    for r in (await conn.execute(_SYNONYMS)).all():  # RLS: the global ones and the user's own
        (mine if r.user_id is not None else synonyms)[r.synonym_norm] = r.test_code
    units = {r.alias_norm: r.unit for r in (await conn.execute(_UNITS)).all()}
    return Catalog(tests=tests, synonyms=synonyms, unit_aliases=units), mine


def _read(data: bytes, claimed: _Claimed) -> Reading:
    """Blocking: the parse runs in a child process killed after READ_TIMEOUT_S (isolated.py).

    A scan or photo is not parsed at all (no local reader, and never sent to the AI - Q50).
    """
    if claimed.mime_type != "application/pdf" or claimed.has_text_layer is False:
        return Reading(None)
    reading = read_isolated(data, timeout=READ_TIMEOUT_S)
    document = reading.document
    if document is not None and any(len(r.results) > MAX_RESULTS for r in document.reports):
        return Reading(None)  # not a lab report as we know them
    return reading


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
    method: _Method,
) -> None:
    run_id = uuid4()
    await conn.execute(
        _RUN,
        {
            "id": run_id,
            "p": claimed.patient_id,
            "d": document_id,
            "method": method.name,
            "reader": document.reader,
            "prompt": method.prompt_version,
            "version": PIPELINE_VERSION,
            "tokens_in": method.input_tokens,
            "tokens_out": method.output_tokens,
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
                "critical": report.has_unconfirmed_critical,
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
        "critical_text": x.critical_text,
        "critical_low": x.critical_low,
        "critical_high": x.critical_high,
        "lab_flag": x.lab_flag,
        "issues": list(x.issues),
        "confidence": _UNSURE if x.issues else _SURE,
        "page": x.source_page,
        "snippet": x.source_snippet,
        "unit_canonical": x.unit_canonical,
        "value_canonical": x.value_canonical,
        "ref_low_canonical": x.ref_low_canonical,
        "ref_high_canonical": x.ref_high_canonical,
        "critical_low_canonical": x.critical_low_canonical,
        "critical_high_canonical": x.critical_high_canonical,
        "flag": x.flag,
        "flag_source": x.flag_source,
        "flag_mismatch": x.flag_mismatch,
    }


async def extract(  # noqa: PLR0911 - one exit per outcome
    engine: AsyncEngine,
    store: ObjectStore,
    document_id: UUID,
    user_id: UUID,
    handoff: Handoff | None = None,
) -> Outcome:
    claimed = await _claim(engine, user_id, document_id)
    if claimed is None:
        return Outcome("done")  # not queued (read already, or not yet scanned) or no access
    started = time.monotonic()
    try:
        sealed = await store.get(claimed.storage_key)
        data = await decrypt_bytes(get_key_provider(), sealed, _aad(document_id))
        reading = await asyncio.to_thread(_read, data, claimed)
        document = reading.document
        if document is None:
            if (
                reading.lines
                and handoff is not None
                and await _hand_to_ai(
                    engine,
                    user_id,
                    document_id,
                    patient_id=claimed.patient_id,
                    lines=reading.lines,
                    handoff=handoff,
                )
            ):
                return Outcome("sent_to_ai")
            await _finish(engine, user_id, document_id, "failed", "not_read")
            return Outcome("not_read")
        reports = await _store(
            engine,
            user_id,
            document_id,
            claimed=claimed,
            document=document,
            method=_Method(),
            started=started,
        )
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


async def _store(
    engine: AsyncEngine,
    user_id: UUID,
    document_id: UUID,
    *,
    claimed: _Claimed,
    document: ReadDocument,
    method: _Method,
    started: float,
    ai_request: Any = None,
) -> list[DraftReport]:
    """Drafts, run, audit and "needs_review" in one transaction, as the uploader. An AI
    reading carries no name: its name check was made before sending (`ai_request`)."""
    async with engine.connect() as conn, conn.begin():
        await _begin(conn, user_id)
        catalog, mine = await _catalog(conn)
        profile = (await conn.execute(_PROFILE, {"p": claimed.patient_id})).one()
        sex: Sex = (
            "male"
            if profile.sex == "male"
            else "female"
            if profile.sex == "female"
            else ("unknown")
        )
        if ai_request is None:
            score = name_match_score(document.identity, profile.full_name)
        else:
            score = ai_request.name_match_score if ai_request.name_printed else None
            await conn.execute(_AI_REQUEST_DONE, {"d": document_id})
        drafts = [
            draft_report(r, catalog, mine, name_score=score, sex=sex) for r in document.reports
        ]
        prior = await _prior(conn, claimed.patient_id, document_id, drafts)
        reports = [with_history(r, prior, catalog) for r in drafts]
        await _save(
            conn,
            document_id=document_id,
            claimed=claimed,
            document=document,
            reports=reports,
            score=score,
            duration_ms=int((time.monotonic() - started) * 1000),
            method=method,
        )
        await conn.execute(_FINISH, {"s": "needs_review", "e": None, "d": document_id})
        # review_ready, or critical_pending (H5): the database picks who is told. Raising
        # here rolls the drafts back with it - the sweep then fails the document
        await conn.execute(_NOTIFY, {"d": document_id})
    return reports


async def _prior(
    conn: AsyncConnection, patient_id: UUID, document_id: UUID, reports: Sequence[DraftReport]
) -> list[Prior]:
    codes = sorted({x.test_code for r in reports for x in r.results if x.test_code})
    if not codes:
        return []
    rows = (await conn.execute(_PRIOR, {"p": patient_id, "d": document_id, "codes": codes})).all()
    return [Prior(r.test_code, r.collected_at, r.value_canonical, r.confirmed) for r in rows]


async def _ai_allowed(conn: AsyncConnection, patient_id: UUID) -> bool:
    """The data owner's consent (`ai_consent_ok`, 0033: the profile owner's own for an adult,
    the owner's for that profile for a child) and the uploader's own - a caregiver's consent
    never sends someone else's results abroad."""
    versions = json.dumps({kind: VERSIONS[kind] for kind in AI_EXTRACTION})
    if not (await conn.execute(_AI_CONSENT, {"p": patient_id, "v": versions})).scalar_one():
        return False
    rows = (await conn.execute(_OWN_CONSENTS)).all()
    mine = {r.kind for r in rows if r.granted and r.version == VERSIONS.get(r.kind)}
    return mine >= AI_EXTRACTION


async def _hand_to_ai(
    engine: AsyncEngine,
    user_id: UUID,
    document_id: UUID,
    *,
    patient_id: UUID,
    lines: Sequence[tuple[int, str]],
    handoff: Handoff,
) -> bool:
    """True when the de-identified text went to the AI worker (the document stays
    "processing"); False when AI reading is off, not consented, over a daily cap, or too
    little text is left. The printed name is checked here, on the server, and only the
    score is kept with the request."""
    if not get_settings().ai_extraction_enabled:
        return False
    async with engine.connect() as conn, conn.begin():
        await _begin(conn, user_id)
        if not await _ai_allowed(conn, patient_id):
            return False
        profile = (await conn.execute(_PROFILE, {"p": patient_id})).scalar_one()
    clean = deidentify(lines, profile)
    if len(clean.text) < MIN_AI_TEXT:
        return False
    if not await handoff.reserve(user_id):
        log.info("document_ai_cap_reached", document_id=str(document_id))
        return False
    score = name_match_score(clean.identity, profile)
    nonce = secrets.token_hex(16)
    async with engine.connect() as conn, conn.begin():
        await _begin(conn, user_id)
        # a request left by an earlier, interrupted try is replaced
        await conn.execute(_AI_REQUEST_DONE, {"d": document_id})
        await conn.execute(
            _AI_REQUEST,
            {
                "d": document_id,
                "p": patient_id,
                "n": nonce,
                "score": score,
                "printed": score is not None,
                "text": clean.text,
            },
        )
    await handoff.put_input(document_id, nonce, clean.text)
    handoff.send(document_id, user_id)
    log.info("document_sent_to_ai", document_id=str(document_id))
    return True


def _untrusted(document: ReadDocument) -> ReadDocument:
    """The AI worker's reading without anything it claims about it: no issues, no evidence."""
    return replace(
        document,
        identity=PrintedIdentity(),
        reports=tuple(
            replace(r, results=tuple(replace(x, issues=(), snippet="") for x in r.results))
            for r in document.reports
        ),
    )


async def _fail_ai(engine: AsyncEngine, user_id: UUID, document_id: UUID, code: str) -> None:
    """The document failed and its request removed (read again later: a new request)."""
    await _finish(engine, user_id, document_id, "failed", code)
    try:
        async with engine.connect() as conn, conn.begin():
            await _begin(conn, user_id)
            await conn.execute(_AI_REQUEST_DONE, {"d": document_id})
    except Exception as exc:  # the row is harmless: replaced on the next request
        log.warning(
            "ai_request_not_removed", document_id=str(document_id), error=type(exc).__name__
        )


async def save_ai(  # noqa: PLR0911 - one exit per outcome
    engine: AsyncEngine, document_id: UUID, user_id: UUID, handoff: Handoff
) -> Outcome:
    """The AI worker's answer under this request's nonce, stored as a draft like a local
    reading - or the document failed with the answer's error code. Only the user who asked,
    only a document still "processing", only with their consent still given."""
    started = time.monotonic()
    async with engine.connect() as conn, conn.begin():
        await _begin(conn, user_id)
        processing = (await conn.execute(_PROCESSING, {"d": document_id})).scalar_one_or_none()
        request = (
            await conn.execute(
                _AI_REQUEST_FIND, {"d": document_id, "wait": AI_WAIT.total_seconds()}
            )
        ).first()
        allowed = request is not None and await _ai_allowed(conn, request.patient_id)
    if processing is None or request is None:
        return Outcome("done")  # swept, deleted, saved already, or not this user's request
    if not allowed:
        await _fail_ai(engine, user_id, document_id, "consent_withdrawn")
        return Outcome("failed")
    answer = await handoff.take_output(document_id, request.nonce)
    if answer is None:
        if request.waiting:
            return Outcome("waiting")  # polled again
        await _fail_ai(engine, user_id, document_id, "ai_failed")
        return Outcome("failed")
    if "error" in answer:
        code = str(answer["error"])
        await _fail_ai(engine, user_id, document_id, code if code in AI_ERRORS else "ai_failed")
        return Outcome("failed")
    try:
        # checked again here against the text this worker sent: the AI worker's own
        # checks are not trusted (commit security review 4.5)
        document = check_against_source(
            _untrusted(from_json(answer["document"])), request.sent_text
        )
        if not any(r.results for r in document.reports):
            await _fail_ai(engine, user_id, document_id, "not_read")
            return Outcome("not_read")
        method = _Method(
            "ai", PROMPT_VERSION, int(answer["input_tokens"]), int(answer["output_tokens"])
        )
        claimed = _Claimed(request.patient_id, "", "application/pdf", True)
        await _store(
            engine,
            user_id,
            document_id,
            claimed=claimed,
            document=document,
            method=method,
            started=started,
            ai_request=request,
        )
    except Exception as exc:
        log.error(  # noqa: TRY400 - no traceback: it may quote the document
            "document_ai_save_failed", document_id=str(document_id), error=type(exc).__name__
        )
        await _fail_ai(engine, user_id, document_id, "extraction_error")
        return Outcome("failed")
    return Outcome("needs_review")


def run_sync(app_url: str, document_id: str, user_id: str) -> str:
    async def main() -> str:
        engine = create_async_engine(app_url, hide_parameters=True, pool_reset_on_return="rollback")
        handoff = ValkeyHandoff()
        try:
            outcome = await extract(engine, get_store(), UUID(document_id), UUID(user_id), handoff)
            return outcome.result
        finally:
            await handoff.close()
            await engine.dispose()

    return asyncio.run(main())


def save_ai_sync(app_url: str, document_id: str, user_id: str) -> str:
    async def main() -> str:
        engine = create_async_engine(app_url, hide_parameters=True, pool_reset_on_return="rollback")
        handoff = ValkeyHandoff()
        try:
            outcome = await save_ai(engine, UUID(document_id), UUID(user_id), handoff)
            return outcome.result
        finally:
            await handoff.close()
            await engine.dispose()

    return asyncio.run(main())
