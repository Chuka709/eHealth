"""Reading what was read from a document over the API (Phase 4.6; rule 4, 0031 RLS)."""

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.db.sql import bound_text

from .conftest import ClientFactory
from .test_documents import _files, _pdf, _scanned
from .test_patients import _signed_in
from .test_records import _grant, _profile

pytestmark = pytest.mark.db


@pytest.fixture
async def client(client_from: ClientFactory) -> AsyncIterator[AsyncClient]:
    async with client_from() as c:
        yield c


async def _report(
    owner_engine: AsyncEngine, base: str, document_id: str, *, status: str = "needs_review"
) -> UUID:
    """A report with two rows, as the worker leaves it (fixture shortcut, as the owner role)."""
    patient = base.rsplit("/", 1)[1]
    report_id = uuid4()
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "insert into lab_reports (id, patient_id, document_id, lab_name, panel_name,"
                " collected_at, collected_precision, name_match_score, status, confirmed_at)"
                " values (:id, cast(:p as uuid), cast(:d as uuid), 'Лаб', 'Биохими',"
                " '2025-05-03T00:00:00+00', 'day', 0.95, cast(:s as report_status),"
                " case when :s = 'confirmed' then now() end)"
            ),
            {"id": report_id, "p": patient, "d": document_id, "s": status},
        )
        await conn.execute(
            bound_text(
                "insert into lab_results (report_id, patient_id, position, test_code, raw_name,"
                " raw_value, raw_unit, value_numeric, ref_text, ref_low, ref_high, issues)"
                " values (:r, cast(:p as uuid), 0, null, 'Шинэ тест', '12,40', 'г/л', 12.40,"
                " '3.5-5.1', 3.5, 5.1, array['unknown_test']),"
                " (:r, cast(:p as uuid), 1, null, 'Өнгө', 'шар', null, null, null, null, null,"
                " '{}')"
            ),
            {"r": report_id, "p": patient},
        )
    return report_id


async def _uploaded(client: AsyncClient, base: str, h: dict[str, str]) -> str:
    response = await client.post(f"{base}/documents", headers=h, **_files(_pdf()))  # type: ignore[arg-type]
    assert response.status_code == 201, response.text
    document_id: str = response.json()["id"]
    return document_id


async def test_the_writer_reads_the_draft_with_exact_numbers(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    document_id = await _uploaded(client, base, h)
    await _scanned(owner_engine, document_id, "needs_review")
    report_id = await _report(owner_engine, base, document_id)
    r = await client.get(f"{base}/documents/{document_id}/reports", headers=h)
    assert r.status_code == 200, r.text
    [report] = r.json()
    assert (report["id"], report["status"], report["collected_precision"]) == (
        str(report_id),
        "needs_review",
        "day",
    )
    assert report["name_match_score"] == "0.95"
    first, second = report["results"]
    # exact strings, as printed and as parsed (rule 7); nothing judged (flag as stored)
    assert (first["raw_value"], first["value_numeric"], first["ref_low"]) == (
        "12,40",
        "12.40",
        "3.5",
    )
    assert (first["flag"], first["issues"]) == ("unknown", ["unknown_test"])
    assert (second["raw_value"], second["value_numeric"]) == ("шар", None)
    assert "source_snippet" not in first


async def test_readers_see_only_confirmed_reports(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    document_id = await _uploaded(client, base, h)
    await _scanned(owner_engine, document_id, "needs_review")
    await _report(owner_engine, base, document_id)
    confirmed = await _report(owner_engine, base, document_id, status="confirmed")
    doctor, hd = await _signed_in(client, owner_engine)
    await _grant(owner_engine, base, doctor, "doctor")
    r = await client.get(f"{base}/documents/{document_id}/reports", headers=hd)
    assert r.status_code == 200, r.text
    assert [x["id"] for x in r.json()] == [str(confirmed)]
    assert r.json()[0]["method"] is None  # runs are the writers' only
    assert len(r.json()[0]["results"]) == 2


async def test_a_reader_never_learns_how_it_was_read(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    document_id = await _uploaded(client, base, h)
    report_id = await _report(owner_engine, base, document_id, status="confirmed")
    async with owner_engine.connect() as conn, conn.begin():
        run = (
            await conn.execute(
                bound_text(
                    "insert into extraction_runs (patient_id, document_id, method, reader,"
                    " pipeline_version) values (cast(:p as uuid), cast(:d as uuid), 'ai',"
                    " 'ai:test', 'p4.6') returning id"
                ),
                {"p": base.rsplit("/", 1)[1], "d": document_id},
            )
        ).scalar_one()
        await conn.execute(
            bound_text("update lab_reports set extraction_run_id = :r where id = :id"),
            {"r": run, "id": report_id},
        )
    [mine] = (await client.get(f"{base}/documents/{document_id}/reports", headers=h)).json()
    assert (mine["method"], mine["name_match_score"]) == ("ai", "0.95")
    for level in ("doctor", "viewer"):
        reader, hr = await _signed_in(client, owner_engine)
        await _grant(owner_engine, base, reader, level)
        r = await client.get(f"{base}/documents/{document_id}/reports", headers=hr)
        [theirs] = r.json()
        assert (theirs["method"], theirs["name_match_score"]) == (None, None), level
        assert len(theirs["results"]) == 2


async def test_a_caregiver_sees_the_draft(client: AsyncClient, owner_engine: AsyncEngine) -> None:
    _, h, base = await _profile(client, owner_engine)
    document_id = await _uploaded(client, base, h)
    draft = await _report(owner_engine, base, document_id)
    carer, hc = await _signed_in(client, owner_engine)
    await _grant(owner_engine, base, carer, "caregiver")
    r = await client.get(f"{base}/documents/{document_id}/reports", headers=hc)
    assert [x["id"] for x in r.json()] == [str(draft)]


async def test_strangers_and_other_profiles_get_nothing(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    document_id = await _uploaded(client, base, h)
    await _report(owner_engine, base, document_id)
    _, hs = await _signed_in(client, owner_engine)
    r = await client.get(f"{base}/documents/{document_id}/reports", headers=hs)
    assert r.status_code == 404
    # the same document asked for under one's own profile: not found, nothing leaks
    _, h2, other = await _profile(client, owner_engine)
    r = await client.get(f"{other}/documents/{document_id}/reports", headers=h2)
    assert r.status_code == 404


async def test_a_document_not_read_yet_has_no_reports(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    document_id = await _uploaded(client, base, h)
    r = await client.get(f"{base}/documents/{document_id}/reports", headers=h)
    assert (r.status_code, r.json()) == (200, [])
