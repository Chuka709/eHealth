"""Reading by AI: owner's consent, caps, de-identified handoff, nonce, saved as a draft (4.5).

The handoff is in memory and the AI worker's task runs with a fake reader - no network.
"""

from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.config import get_settings
from labtrack.consents import VERSIONS
from labtrack.db.sql import bound_text
from labtrack.extraction.isolated import from_json, to_json
from labtrack.extraction.llm import AiAnswer, AiReadError
from labtrack.extraction.types import ReadDocument, ReadReport, ReadResult
from labtrack.storage import MemoryObjectStore
from labtrack.worker import ai_handoff, ai_tasks
from labtrack.worker import extraction as worker

from .conftest import as_user, grant, make_patient, make_user, scalar
from .test_document_extraction import _queued, _reader, _status, test_code  # noqa: F401

pytestmark = pytest.mark.db

LINES = (
    (1, "ОВОГ: Тест РЕГИСТР: УБ90010112"),
    (1, "НЭР: Patient ТӨРСӨН: 1990/01/01"),
    (1, "Lab report for Test Patient"),
    (1, "Glucose 5.4 mmol/L 3.9 - 6.1"),
    (1, "Creatinine 80 umol/L 62 - 115"),
)


class MemoryHandoff:
    def __init__(self, *, cap: int = 10) -> None:
        self.inputs: dict[str, tuple[str, str]] = {}
        self.outputs: dict[tuple[str, str], dict[str, Any]] = {}
        self.sent: list[tuple[str, str]] = []
        self.cap = cap

    async def reserve(self, user_id: UUID) -> bool:
        self.cap -= 1
        return self.cap >= 0

    async def put_input(self, document_id: UUID, nonce: str, text: str) -> None:
        self.inputs[str(document_id)] = (nonce, text)

    async def take_output(self, document_id: UUID, nonce: str) -> dict[str, Any] | None:
        return self.outputs.pop((str(document_id), nonce), None)

    def send(self, document_id: UUID, user_id: UUID) -> None:
        self.sent.append((str(document_id), str(user_id)))

    def answer(self, document_id: UUID, answer: dict[str, Any]) -> None:
        nonce, _ = self.inputs[str(document_id)]
        self.outputs[(str(document_id), nonce)] = answer


def _settings(monkeypatch: pytest.MonkeyPatch, *, enabled: bool) -> None:
    """The worker's settings with AI reading switched (settings are frozen: a copy)."""
    changed = get_settings().model_copy(update={"ai_extraction_enabled": enabled})
    monkeypatch.setattr(worker, "get_settings", lambda: changed)


@pytest.fixture
def ai_on(monkeypatch: pytest.MonkeyPatch) -> None:
    _settings(monkeypatch, enabled=True)


async def _consent(app_engine: AsyncEngine, user: UUID, *, granted: bool = True) -> None:
    async with as_user(app_engine, user) as conn:
        for kind in ("ai_processing", "cross_border"):
            await conn.execute(
                bound_text(
                    "insert into consents (user_id, kind, version, granted)"
                    " values (app_user_id(), :k, :v, :g)"
                ),
                {"k": kind, "v": VERSIONS[kind], "g": granted},
            )


def _answer(code: str, value: str = "5.4") -> ReadDocument:
    row = ReadResult("Glucose", value, "mmol/L", "3.9 - 6.1", None, 1, "")
    return ReadDocument(
        reader="ai:test-model",
        reports=(ReadReport("Lab", None, "serum", "2025-08-18", None, (row,)),),
    )


def _good(code: str) -> dict[str, Any]:
    return {
        "document": to_json(_answer(code)),
        "model": "test-model",
        "input_tokens": 900,
        "output_tokens": 120,
    }


async def _setup(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> tuple[MemoryObjectStore, UUID, UUID, UUID]:
    store, user = MemoryObjectStore(), await make_user(owner_engine)
    patient = await make_patient(app_engine, user)
    doc = await _queued(app_engine, store, user, patient)
    monkeypatch.setattr(worker, "_read", _reader(None, LINES))
    return store, user, patient, doc


async def test_with_the_owners_consent_only_deidentified_text_goes_out(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch, ai_on: None
) -> None:
    store, user, _, doc = await _setup(app_engine, owner_engine, monkeypatch)
    await _consent(app_engine, user)
    handoff = MemoryHandoff()
    assert (await worker.extract(app_engine, store, doc, user, handoff)).result == "sent_to_ai"
    assert await _status(app_engine, user, doc) == ("processing", None)
    assert handoff.sent == [(str(doc), str(user))]
    nonce, text = handoff.inputs[str(doc)]
    for secret in ("Тест", "УБ90010112", "1990/01/01", "Patient"):
        assert secret not in text
    assert "Glucose 5.4 mmol/L 3.9 - 6.1" in text
    async with as_user(app_engine, user) as conn:
        row = (
            await conn.execute(
                bound_text("select nonce, name_printed from ai_requests where document_id = :d"),
                {"d": doc},
            )
        ).one()
    assert (row.nonce, row.name_printed) == (nonce, True)  # the name was checked here


@pytest.mark.parametrize("why", ["no_consent", "withdrawn", "ai_off", "cap"])
async def test_without_consent_switched_off_or_over_the_cap_nothing_leaves(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    ai_on: None,
    why: str,
) -> None:
    store, user, _, doc = await _setup(app_engine, owner_engine, monkeypatch)
    handoff = MemoryHandoff(cap=0 if why == "cap" else 10)
    if why != "no_consent":
        await _consent(app_engine, user)
    if why == "withdrawn":
        await _consent(app_engine, user, granted=False)
    if why == "ai_off":
        _settings(monkeypatch, enabled=False)
    assert (await worker.extract(app_engine, store, doc, user, handoff)).result == "not_read"
    assert await _status(app_engine, user, doc) == ("failed", "not_read")
    assert (handoff.inputs, handoff.sent) == ({}, [])


async def test_a_caregivers_consent_never_sends_the_owners_results(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch, ai_on: None
) -> None:
    store = MemoryObjectStore()
    owner, carer = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    await grant(app_engine, owner, patient, carer, "caregiver")
    await _consent(app_engine, carer)  # the caregiver agreed; the owner did not
    doc = await _queued(app_engine, store, carer, patient)
    monkeypatch.setattr(worker, "_read", _reader(None, LINES))
    handoff = MemoryHandoff()
    assert (await worker.extract(app_engine, store, doc, carer, handoff)).result == "not_read"
    assert handoff.inputs == {}
    await _consent(app_engine, owner)  # with the owner's consent too, it may go
    doc2 = await _queued(app_engine, store, carer, patient)
    assert (await worker.extract(app_engine, store, doc2, carer, handoff)).result == "sent_to_ai"


async def test_the_answer_under_the_nonce_is_saved_as_a_draft_read_by_ai(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    ai_on: None,
    test_code: str,  # noqa: F811
) -> None:
    store, user, patient, doc = await _setup(app_engine, owner_engine, monkeypatch)
    await _consent(app_engine, user)
    handoff = MemoryHandoff()
    await worker.extract(app_engine, store, doc, user, handoff)
    # an answer under another nonce (a replay, a forgery) is not this request's
    handoff.outputs[(str(doc), "0" * 32)] = _good(test_code)
    assert (await worker.save_ai(app_engine, doc, user, handoff)).result == "waiting"
    handoff.answer(doc, _good(test_code))
    # another user's save task finds no request of theirs
    stranger = await make_user(owner_engine)
    assert (await worker.save_ai(app_engine, doc, stranger, handoff)).result == "done"
    assert (await worker.save_ai(app_engine, doc, user, handoff)).result == "needs_review"
    assert await _status(app_engine, user, doc) == ("needs_review", None)
    async with as_user(app_engine, user) as conn:
        run = (
            await conn.execute(
                bound_text(
                    "select method, reader, prompt_version, input_tokens, output_tokens"
                    " from extraction_runs where document_id = :d"
                ),
                {"d": doc},
            )
        ).one()
        issues = await scalar(
            conn,
            bound_text("select issues from lab_results where patient_id = :p"),
            {"p": patient},
        )
        left = await scalar(
            conn, bound_text("select count(*) from ai_requests where document_id = :d"), {"d": doc}
        )
    assert tuple(run) == ("ai", "ai:test-model", "v1", 900, 120)
    # "Тест" (Cyrillic) is not the profile's "Test": the server's name check says so
    assert "name_mismatch" in issues
    assert left == 0


@pytest.mark.parametrize(
    ("answer", "code"),
    [({"error": "ai_refused"}, "ai_refused"), ({"error": "made up"}, "ai_failed")],
)
async def test_an_error_answer_fails_the_document_with_a_known_code(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    ai_on: None,
    answer: dict[str, Any],
    code: str,
) -> None:
    store, user, _, doc = await _setup(app_engine, owner_engine, monkeypatch)
    await _consent(app_engine, user)
    handoff = MemoryHandoff()
    await worker.extract(app_engine, store, doc, user, handoff)
    handoff.answer(doc, answer)
    assert (await worker.save_ai(app_engine, doc, user, handoff)).result == "failed"
    assert await _status(app_engine, user, doc) == ("failed", code)


async def test_no_answer_in_time_or_consent_withdrawn_fails_the_document(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    ai_on: None,
    test_code: str,  # noqa: F811
) -> None:
    store, user, patient, late = await _setup(app_engine, owner_engine, monkeypatch)
    await _consent(app_engine, user)
    handoff = MemoryHandoff()
    await worker.extract(app_engine, store, late, user, handoff)
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "update ai_requests set created_at = now() - make_interval(secs => :s)"
                " where document_id = :d"
            ),
            {"d": late, "s": timedelta(minutes=5).total_seconds()},
        )
    assert (await worker.save_ai(app_engine, late, user, handoff)).result == "failed"
    assert await _status(app_engine, user, late) == ("failed", "ai_failed")

    withdrawn = await _queued(app_engine, store, user, patient)
    await worker.extract(app_engine, store, withdrawn, user, handoff)
    handoff.answer(withdrawn, _good(test_code))
    await _consent(app_engine, user, granted=False)
    assert (await worker.save_ai(app_engine, withdrawn, user, handoff)).result == "failed"
    assert await _status(app_engine, user, withdrawn) == ("failed", "consent_withdrawn")


def test_the_ai_task_checks_rows_against_the_text_it_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = "--- хуудас 1 ---\nGlucose 5.4 mmol/L 3.9 - 6.1\nUrea 6.1 mmol/L 2.5 - 7.5"
    store: dict[str, Any] = {"in": ("ab" * 16, text), "out": None}
    monkeypatch.setattr(ai_handoff, "take_input", lambda d: store.pop("in", None))
    monkeypatch.setattr(ai_handoff, "put_output", lambda d, n, a: store.__setitem__("out", (n, a)))

    class Reader:
        def read(self, sent: str) -> AiAnswer:
            assert sent == text
            rows = (
                ReadResult("Glucose", "5.4", "mmol/L", "3.9 - 6.1", None, 1, ""),
                ReadResult("Urea", "61", "mmol/L", "2.5 - 7.5", None, 1, ""),  # misread
                ReadResult("Potassium", "4.2", "mmol/L", "3.5 - 5.1", None, 1, ""),  # made up
                ReadResult(  # a critical limit not in the text
                    "Glucose", "5.4", "mmol/L", "3.9 - 6.1", None, 1, "", critical_text="< 2.2"
                ),
            )
            reading = ReadDocument("ai:m", (ReadReport(None, None, None, None, None, rows),))
            return AiAnswer(reading, "m", 10, 5)

    assert ai_tasks.read_with_ai("doc", Reader) == "read"
    nonce, answer = store["out"]
    assert nonce == "ab" * 16
    glucose, urea, potassium, critical = from_json(answer["document"]).reports[0].results
    assert glucose.issues == ()
    assert glucose.snippet == "glucose 5.4 mmol/l 3.9 - 6.1"  # the sent line, not the model's
    assert "not_in_source" in urea.issues
    assert "not_in_source" in potassium.issues
    assert (critical.critical_text, critical.issues) == (None, ("not_in_source",))
    assert glucose.raw_unit == "mmol/L"  # its unit is in the text: no issue
    # taken once: a second run finds nothing and sends nothing out
    assert ai_tasks.read_with_ai("doc", Reader) == "ai_input_missing"


def test_the_ai_task_leaves_a_code_when_it_cannot_read(monkeypatch: pytest.MonkeyPatch) -> None:
    out: dict[str, Any] = {}
    monkeypatch.setattr(ai_handoff, "take_input", lambda d: ("cd" * 16, "Glucose 5.4"))
    monkeypatch.setattr(ai_handoff, "put_output", lambda d, n, a: out.update(a))

    class Refusing:
        def read(self, text: str) -> AiAnswer:
            raise AiReadError("ai_refused")

    assert ai_tasks.read_with_ai("doc", Refusing) == "ai_refused"
    assert ai_tasks.read_with_ai("doc", lambda: None) == "ai_unconfigured"


async def test_the_default_worker_checks_the_answer_itself(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    ai_on: None,
    test_code: str,  # noqa: F811
) -> None:
    """A made-up value the AI worker passed as fine is marked against the text sent."""
    store, user, patient, doc = await _setup(app_engine, owner_engine, monkeypatch)
    await _consent(app_engine, user)
    handoff = MemoryHandoff()
    await worker.extract(app_engine, store, doc, user, handoff)
    forged = _answer(test_code, value="9.9")  # not in the sent text
    handoff.answer(doc, {**_good(test_code), "document": to_json(forged)})
    assert (await worker.save_ai(app_engine, doc, user, handoff)).result == "needs_review"
    async with as_user(app_engine, user) as conn:
        issues = await scalar(
            conn,
            bound_text("select issues from lab_results where patient_id = :p"),
            {"p": patient},
        )
    assert "not_in_source" in issues


def test_a_value_found_only_under_another_tests_name_is_not_proof() -> None:
    from labtrack.extraction.verify import check_against_source  # noqa: PLC0415

    rows = (ReadResult("Potassium", "5.4", "mmol/L", None, None, 1, ""),)
    reading = ReadDocument("ai:m", (ReadReport(None, None, None, None, None, rows),))
    checked = check_against_source(reading, "Glucose 5.4 mmol/L 3.9 - 6.1")
    assert "not_in_source" in checked.reports[0].results[0].issues
