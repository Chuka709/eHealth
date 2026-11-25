"""Reviewing a draft lab report over the API (Phase 5.3; rules 4-6; 0036)."""

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.core.text import normalize_name, normalize_unit
from labtrack.db.sql import bound_text

from .conftest import ClientFactory
from .test_documents import _scanned
from .test_lab_reports import _report, _uploaded
from .test_patients import _signed_in
from .test_records import _grant, _profile

pytestmark = pytest.mark.db


@pytest.fixture
async def client(client_from: ClientFactory) -> AsyncIterator[AsyncClient]:
    async with client_from() as c:
        yield c


@pytest.fixture
async def code(owner_engine: AsyncEngine) -> AsyncIterator[str]:
    """A catalog test of its own in g/L, with a mg/dL factor (the test DB has no catalog)."""
    test = f"T_{uuid4().hex[:8].upper()}"
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "insert into test_catalog (code, name_mn, name_en, category, canonical_unit,"
                " physio_min, physio_max) values (:c, 'Тест', 'Test', 'test', 'g/L', 1, 200)"
            ),
            {"c": test},
        )
        for alias, unit in (("г/л", "g/L"), ("г/дл", "g/dL")):
            await conn.execute(
                bound_text(
                    "insert into unit_aliases (alias_norm, unit) values (:a, :u)"
                    " on conflict do nothing"
                ),
                {"a": normalize_unit(alias), "u": unit},
            )
        await conn.execute(
            bound_text(
                "insert into unit_conversions (test_code, from_unit, to_unit, factor)"
                " values (:c, 'g/dL', 'g/L', 10)"
            ),
            {"c": test},
        )
    yield test
    async with owner_engine.connect() as conn, conn.begin():
        for sql in (
            "delete from lab_results where test_code = :c",
            "delete from test_synonyms where test_code = :c",
            "update medications set catalog_code = null where catalog_code in"
            " (select code from medication_catalog where related_test_code = :c)",
            "delete from medication_catalog where related_test_code = :c",
            "delete from test_catalog where code = :c",
        ):
            await conn.execute(bound_text(sql), {"c": test})


async def _draft(client: AsyncClient, owner_engine: AsyncEngine) -> tuple[dict[str, str], str, str]:
    _, h, base = await _profile(client, owner_engine)
    document_id = await _uploaded(client, base, h)
    await _scanned(owner_engine, document_id, "needs_review")
    report_id = await _report(owner_engine, base, document_id)
    return h, base, str(report_id)


def _rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(report["results"], key=lambda x: x["position"])


async def test_picking_a_test_recomputes_the_row_and_learns_the_name(
    client: AsyncClient, owner_engine: AsyncEngine, code: str
) -> None:
    h, base, report = await _draft(client, owner_engine)
    first = _rows((await client.get(f"{base}/reports/{report}", headers=h)).json())[0]
    r = await client.patch(
        f"{base}/reports/{report}/results/{first['id']}", headers=h, json={"test_code": code}
    )
    assert r.status_code == 200, r.text
    row = _rows(r.json())[0]
    # 12,40 g/L against the printed 3.5-5.1: high, computed on the server (rule 6)
    assert (row["test_code"], row["flag"], row["flag_source"]) == (
        code,
        "high",
        "computed_document_range",
    )
    assert (row["unit_canonical"], row["value_canonical"]) == ("g/L", "12.40")
    assert "unknown_test" not in row["issues"]
    assert row["edited_by_user"]
    async with owner_engine.connect() as conn:
        learned = (
            await conn.execute(
                bound_text(
                    "select test_code from test_synonyms where synonym_norm = :k"
                    " and user_id is not null"
                ),
                {"k": normalize_name("Шинэ тест")},
            )
        ).scalar_one()
    assert learned == code


async def test_editing_the_value_and_unit_converts_by_the_tests_factor(
    client: AsyncClient, owner_engine: AsyncEngine, code: str
) -> None:
    h, base, report = await _draft(client, owner_engine)
    first = _rows((await client.get(f"{base}/reports/{report}", headers=h)).json())[0]
    url = f"{base}/reports/{report}/results/{first['id']}"
    r = await client.patch(
        url, headers=h, json={"test_code": code, "raw_value": "0,45", "raw_unit": "г/дл"}
    )
    assert r.status_code == 200, r.text
    row = _rows(r.json())[0]
    assert (row["raw_value"], row["value_numeric"], row["value_canonical"]) == (
        "0,45",
        "0.45",
        "4.50",
    )
    # the printed range is compared with the value in the unit both were printed in
    assert row["flag"] == "low"


async def test_confirm_needs_every_issue_looked_at(
    client: AsyncClient, owner_engine: AsyncEngine, code: str
) -> None:
    h, base, report = await _draft(client, owner_engine)
    first, second = _rows((await client.get(f"{base}/reports/{report}", headers=h)).json())
    r = await client.post(f"{base}/reports/{report}/confirm", headers=h)
    assert (r.status_code, r.json()["code"]) == (409, "review.open_issues")
    # an issue the row does not have cannot be accepted
    r = await client.patch(
        f"{base}/reports/{report}/results/{second['id']}",
        headers=h,
        json={"acknowledge": ["implausible"]},
    )
    assert (r.status_code, r.json()["code"]) == (422, "review.issue_not_open")
    r = await client.patch(
        f"{base}/reports/{report}/results/{first['id']}",
        headers=h,
        json={"acknowledge": ["unknown_test"]},
    )
    assert r.status_code == 200, r.text
    open_issues = [x for x in _rows(r.json()) if not set(x["issues"]) <= set(x["acknowledged"])]
    for row in open_issues:  # what is left (e.g. no_conversion / ref_not_used), one by one
        for issue in [i for i in row["issues"] if i not in row["acknowledged"]]:
            r = await client.patch(
                f"{base}/reports/{report}/results/{row['id']}",
                headers=h,
                json={"acknowledge": [issue]},
            )
            assert r.status_code == 200, r.text
    r = await client.post(f"{base}/reports/{report}/confirm", headers=h)
    assert r.status_code == 200, r.text
    assert (r.json()["status"], r.json()["has_unconfirmed_critical"]) == ("confirmed", False)
    document_id = r.json()["document_id"]
    doc = await client.get(f"{base}/documents/{document_id}", headers=h)
    assert doc.json()["status"] == "confirmed"
    # never edited again
    r = await client.patch(
        f"{base}/reports/{report}/results/{first['id']}", headers=h, json={"raw_value": "1"}
    )
    assert (r.status_code, r.json()["code"]) == (409, "review.not_draft")


async def test_a_new_text_drops_what_was_accepted_about_the_old_one(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    h, base, report = await _draft(client, owner_engine)
    first = _rows((await client.get(f"{base}/reports/{report}", headers=h)).json())[0]
    url = f"{base}/reports/{report}/results/{first['id']}"
    r = await client.patch(url, headers=h, json={"acknowledge": ["unknown_test"]})
    assert _rows(r.json())[0]["acknowledged"] == ["unknown_test"]
    r = await client.patch(url, headers=h, json={"raw_value": "12,50"})
    assert _rows(r.json())[0]["acknowledged"] == []
    r = await client.patch(
        url, headers=h, json={"raw_value": "12,60", "acknowledge": ["unknown_test"]}
    )
    assert (r.status_code, r.json()["code"]) == (422, "review.acknowledge_alone")


async def test_rows_are_added_and_deleted_and_the_date_is_set(
    client: AsyncClient, owner_engine: AsyncEngine, code: str
) -> None:
    h, base, report = await _draft(client, owner_engine)
    r = await client.post(
        f"{base}/reports/{report}/results",
        headers=h,
        json={"raw_name": "Гараар", "raw_value": "4,2", "raw_unit": "г/л",
              "ref_text": "3.5 - 5.1", "test_code": code},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    added = _rows(r.json())[-1]
    assert (added["position"], added["flag"], added["edited_by_user"]) == (2, "normal", True)
    r = await client.delete(f"{base}/reports/{report}/results/{added['id']}", headers=h)
    assert r.status_code == 204
    r = await client.patch(
        f"{base}/reports/{report}",
        headers=h,
        json={"collected_at": "2025-05-03T08:30:00+08:00", "collected_precision": "minute"},
    )
    assert r.status_code == 200, r.text
    assert (r.json()["collected_precision"], len(r.json()["results"])) == ("minute", 2)
    for body in (
        {"collected_at": "2025-05-03T08:30:00", "collected_precision": "minute"},  # no zone
        {"collected_at": "2025-05-03T08:30:00+08:00"},  # a day or a minute? always said
    ):
        r = await client.patch(f"{base}/reports/{report}", headers=h, json=body)
        assert r.status_code == 422, body


async def test_readers_and_strangers_cannot_review(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    h, base, report = await _draft(client, owner_engine)
    first = _rows((await client.get(f"{base}/reports/{report}", headers=h)).json())[0]
    doctor, hd = await _signed_in(client, owner_engine)
    await _grant(owner_engine, base, doctor, "doctor")
    _, hs = await _signed_in(client, owner_engine)
    for headers in (hd, hs):
        for method, url, body in (
            ("PATCH", f"{base}/reports/{report}/results/{first['id']}", {"raw_value": "1"}),
            ("POST", f"{base}/reports/{report}/confirm", None),
            ("POST", f"{base}/reports/{report}/reject", None),
            ("DELETE", f"{base}/reports/{report}/results/{first['id']}", None),
        ):
            r = await client.request(method, url, headers=headers, json=body)
            assert r.status_code in {403, 404}, (method, url, r.status_code)
    # the doctor does not see the draft either
    r = await client.get(f"{base}/reports/{report}", headers=hd)
    assert (r.status_code, r.json()["code"]) == (404, "review.not_found")


async def test_reject_keeps_the_draft_out_of_the_trend(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    h, base, report = await _draft(client, owner_engine)
    r = await client.post(f"{base}/reports/{report}/reject", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "rejected"
    r = await client.post(f"{base}/reports/{report}/confirm", headers=h)
    assert (r.status_code, r.json()["code"]) == (409, "review.not_draft")


async def test_the_last_dose_before_a_drug_level_sample(
    client: AsyncClient, owner_engine: AsyncEngine, code: str
) -> None:
    h, base, report = await _draft(client, owner_engine)
    patient = base.rsplit("/", 1)[1]
    medication = uuid4()
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "insert into medication_catalog (code, generic_mn, generic_en, category,"
                " related_test_code) values (:m, 'Эм', 'Drug', 'immunosuppressant', :c)"
            ),
            {"m": f"M_{code}", "c": code},
        )
        await conn.execute(
            bound_text(
                "insert into medications (id, patient_id, client_id, catalog_code, name)"
                " values (:i, cast(:p as uuid), :cl, :m, 'Такролимус')"
            ),
            {"i": medication, "p": patient, "cl": uuid4(), "m": f"M_{code}"},
        )
        for at in ("2025-05-02T20:05:00+08:00", "2025-05-03T09:00:00+08:00"):
            await conn.execute(
                bound_text(
                    "insert into medication_intakes (patient_id, medication_id, client_id,"
                    " taken_at, status) values (cast(:p as uuid), :i, :cl,"
                    " cast(:at as timestamptz), 'taken')"
                ),
                {"p": patient, "i": medication, "cl": uuid4(), "at": datetime.fromisoformat(at)},
            )
    first = _rows((await client.get(f"{base}/reports/{report}", headers=h)).json())[0]
    await client.patch(
        f"{base}/reports/{report}/results/{first['id']}", headers=h, json={"test_code": code}
    )
    # the stored day only: which dose came before is not known
    r = await client.get(f"{base}/reports/{report}", headers=h)
    [dose] = r.json()["last_doses"]
    assert (dose["time_unknown"], dose["taken_at"]) == (True, None)
    r = await client.patch(
        f"{base}/reports/{report}",
        headers=h,
        json={"collected_at": "2025-05-03T08:05:00+08:00", "collected_precision": "minute"},
    )
    [dose] = r.json()["last_doses"]
    # the evening dose, not the one after the sample; 12 hours as a fact
    assert (dose["medication_id"], dose["minutes_before"], dose["time_unknown"]) == (
        str(medication),
        720,
        False,
    )


async def test_unknown_report_or_test(client: AsyncClient, owner_engine: AsyncEngine) -> None:
    h, base, report = await _draft(client, owner_engine)
    first = _rows((await client.get(f"{base}/reports/{report}", headers=h)).json())[0]
    r = await client.patch(
        f"{base}/reports/{report}/results/{first['id']}", headers=h, json={"test_code": "NOPE"}
    )
    assert (r.status_code, r.json()["code"]) == (422, "review.unknown_test")
    r = await client.get(f"{base}/reports/{uuid4()}", headers=h)
    assert r.status_code == 404
    r = await client.post(f"{base}/reports/{UUID(int=0)}/confirm", headers=h)
    assert r.status_code == 404


async def _critical_row(
    client: AsyncClient, base: str, h: dict[str, str], report: str, code: str
) -> dict[str, Any]:
    r = await client.post(
        f"{base}/reports/{report}/results",
        headers=h,
        json={"raw_name": "Кали", "raw_value": "2,0", "raw_unit": "г/л",
              "ref_text": "3.5 - 5.1", "critical_text": "< 2.5", "test_code": code},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    assert r.json()["has_unconfirmed_critical"]
    row: dict[str, Any] = _rows(r.json())[-1]
    assert row["flag"] == "critical_low"
    return row


async def test_an_edit_that_ends_a_critical_reading_must_be_accepted_alone(
    client: AsyncClient, owner_engine: AsyncEngine, code: str
) -> None:
    h, base, report = await _draft(client, owner_engine)
    row = await _critical_row(client, base, h, report, code)
    url = f"{base}/reports/{report}/results/{row['id']}"
    r = await client.patch(url, headers=h, json={"raw_value": "3,0"})
    edited = _rows(r.json())[-1]
    # what was read is kept; the banner stays until the change is accepted (H5)
    assert (edited["flag"], edited["read_value"], edited["read_critical_text"]) == (
        "low",
        "2,0",
        "< 2.5",
    )
    assert "critical_edited" in edited["issues"]
    assert r.json()["has_unconfirmed_critical"]
    others = [i for i in edited["issues"] if i != "critical_edited"]
    if others:
        r = await client.patch(url, headers=h, json={"acknowledge": ["critical_edited", others[0]]})
        assert (r.status_code, r.json()["code"]) == (422, "review.acknowledge_one")
    r = await client.patch(url, headers=h, json={"acknowledge": ["critical_edited"]})
    assert r.status_code == 200, r.text
    assert not r.json()["has_unconfirmed_critical"]


async def test_a_possibly_critical_draft_is_not_dropped_unseen(
    client: AsyncClient, owner_engine: AsyncEngine, code: str
) -> None:
    h, base, report = await _draft(client, owner_engine)
    row = await _critical_row(client, base, h, report, code)
    url = f"{base}/reports/{report}/results/{row['id']}"
    r = await client.delete(url, headers=h)
    assert (r.status_code, r.json()["code"]) == (409, "review.critical_needs_ack")
    r = await client.post(f"{base}/reports/{report}/reject", headers=h)
    assert (r.status_code, r.json()["code"]) == (409, "review.critical_needs_ack")
    r = await client.post(
        f"{base}/reports/{report}/reject", headers=h, json={"critical_seen": True}
    )
    assert (r.status_code, r.json()["status"]) == (200, "rejected")


async def test_an_ambiguous_date_is_chosen_never_accepted(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    h, base, report = await _draft(client, owner_engine)
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text("update lab_reports set date_ambiguous = true where id = cast(:r as uuid)"),
            {"r": report},
        )
        await conn.execute(
            bound_text(
                "update lab_results set acknowledged = '{}', issues = '{date_ambiguous}'"
                " where report_id = cast(:r as uuid)"
            ),
            {"r": report},
        )
    r = await client.patch(
        f"{base}/reports/{report}", headers=h, json={"acknowledge": ["date_ambiguous"]}
    )
    assert (r.status_code, r.json()["code"]) == (422, "review.issue_not_open")
    async with owner_engine.connect() as conn, conn.begin():  # past the app's own check
        await conn.execute(
            bound_text("update lab_results set issues = '{}' where report_id = cast(:r as uuid)"),
            {"r": report},
        )
    r = await client.post(f"{base}/reports/{report}/confirm", headers=h)
    assert (r.status_code, r.json()["code"]) == (409, "review.no_date")  # the database
    r = await client.patch(
        f"{base}/reports/{report}",
        headers=h,
        json={"collected_at": "2025-03-05T00:00:00+08:00", "collected_precision": "day"},
    )
    assert r.status_code == 200, r.text
    assert "date_ambiguous" not in {i for x in r.json()["results"] for i in x["issues"]}


async def test_the_test_catalog_lists_the_tests(
    client: AsyncClient, owner_engine: AsyncEngine, code: str
) -> None:
    _, h, _ = await _profile(client, owner_engine)
    r = await client.get("/api/v1/lab-tests", headers=h)
    assert r.status_code == 200, r.text
    assert any(t["code"] == code and t["canonical_unit"] == "g/L" for t in r.json())


async def test_an_implausible_value_is_accepted_only_when_typed_again(
    client: AsyncClient, owner_engine: AsyncEngine, code: str
) -> None:
    """Q57 (physician 2026-11-18): a value outside what a body can hold is kept only after the
    person types it again from the printed report - a matching retype, never a bare tap."""
    h, base, report = await _draft(client, owner_engine)
    first = _rows((await client.get(f"{base}/reports/{report}", headers=h)).json())[0]
    url = f"{base}/reports/{report}/results/{first['id']}"
    r = await client.patch(
        url, headers=h, json={"test_code": code, "raw_value": "950,5", "raw_unit": "г/л"}
    )
    assert r.status_code == 200, r.text
    assert "implausible" in _rows(r.json())[0]["issues"]
    for body in (
        {"acknowledge": ["implausible"]},  # a tap is not enough
        {"acknowledge": ["implausible"], "retyped_value": "95,05"},  # another number
        {"acknowledge": ["unknown_test"], "retyped_value": "950,5"},  # a retype for nothing
    ):
        r = await client.patch(url, headers=h, json=body)
        assert r.status_code == 422, body
    r = await client.patch(
        url, headers=h, json={"acknowledge": ["implausible"], "retyped_value": " 950.5 "}
    )
    assert r.status_code == 200, r.text
    assert "implausible" in _rows(r.json())[0]["acknowledged"]


async def test_a_sample_time_the_person_sets_is_marked_theirs_for_good(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    """Q65: the database marks a changed date/time; the app can neither set nor clear it."""
    h, base, report = await _draft(client, owner_engine)
    async with owner_engine.connect() as conn, conn.begin():  # as if read from the PDF
        await conn.execute(
            bound_text("update lab_reports set source = 'read' where id = :r"), {"r": UUID(report)}
        )
    r = await client.patch(f"{base}/reports/{report}", headers=h, json={"lab_name": "Лаб 2"})
    assert r.json()["collected_by_user"] is False  # read from the document, untouched
    r = await client.patch(
        f"{base}/reports/{report}",
        headers=h,
        json={"collected_at": "2025-05-03T08:30:00+08:00", "collected_precision": "minute"},
    )
    assert r.json()["collected_by_user"] is True
    r = await client.patch(f"{base}/reports/{report}", headers=h, json={"lab_name": "Лаб 3"})
    assert r.json()["collected_by_user"] is True  # an edit of something else keeps it
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text("update lab_reports set collected_edited = false where id = :r"),
            {"r": UUID(report)},
        )
    r = await client.get(f"{base}/reports/{report}", headers=h)
    assert r.json()["collected_by_user"] is True  # never cleared, not even by the owner role
