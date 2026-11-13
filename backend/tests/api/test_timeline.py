"""Timeline API (Phase 6.5; docs/08 "Цагийн хэлхээс"; rule 4; Q21, H24)."""

import base64
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.db.sql import bound_text

from .conftest import ClientFactory, login_body, make_active_user
from .test_dashboard import seeded  # noqa: F401 - fixture (the catalog)
from .test_patients import REQUIRED, _auth
from .test_records import _grant, _medication, _profile, _transplant
from .test_trends import _value

pytestmark = pytest.mark.db


@pytest.fixture
async def client(client_from: ClientFactory) -> AsyncIterator[AsyncClient]:
    async with client_from() as c:
        yield c


async def _page(c: AsyncClient, base: str, h: dict[str, str], query: str = "") -> dict[str, Any]:
    r = await c.get(f"{base}/timeline{query}", headers=h)
    assert r.status_code == 200, r.text
    body: dict[str, Any] = r.json()
    return body


async def _history(c: AsyncClient, owner_engine: AsyncEngine) -> tuple[dict[str, str], str]:
    _, h, base = await _profile(c, owner_engine)
    tx = _transplant(transplant_date="2021-06-01", date_precision="month")
    assert (await c.post(f"{base}/transplants", json=tx, headers=h)).status_code == 201
    med = _medication(catalog_code="TACROLIMUS", started_on="2021-06-10")
    med["regimen"]["effective_from"] = "2021-06-10"
    m = (await c.post(f"{base}/medications", json=med, headers=h)).json()
    regimen = {
        "client_id": "6a0d7c9e-2a1b-4c3d-8e9f-000000000001",
        "effective_from": "2022-01-05",
        "dose_unit": "mg",
        "schedule": {"type": "daily", "times": [{"at": "08:00", "amount": "2"}]},
    }
    r = await c.post(f"{base}/medications/{m['id']}/regimens", json=regimen, headers=h)
    assert r.status_code == 201, r.text
    event = {"client_id": "6a0d7c9e-2a1b-4c3d-8e9f-000000000002", "kind": "biopsy",
             "title": "Биопси", "started_on": "2022-03-01"}  # fmt: skip
    assert (await c.post(f"{base}/events", json=event, headers=h)).status_code == 201
    await _value(owner_engine, base, datetime(2022, 4, 1, 1, tzinfo=UTC), "7.0", lab="УНТЭ")
    await _value(
        owner_engine, base, datetime(2022, 5, 1, 1, tzinfo=UTC), "99", status="needs_review"
    )
    return h, base


async def test_one_stream_newest_first_without_drafts(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    h, base = await _history(client, owner_engine)
    items = (await _page(client, base, h))["items"]
    assert [(i["kind"], i["day"]) for i in items] == [
        ("report", "2022-04-01"),  # the draft of May is not history yet (rule 4)
        ("event", "2022-03-01"),
        ("regimen_changed", "2022-01-05"),
        ("medication_started", "2021-06-10"),
        ("transplant", "2021-06-01"),
    ]
    report = items[0]
    assert (report["title"], report["results"], report["flagged"]) == ("УНТЭ", 1, 0)
    assert items[2]["ref_id"] is not None  # the medicine of the dose change
    assert (items[4]["title"], items[4]["precision"]) == ("kidney", "month")


async def test_pages_filters_and_labs(client: AsyncClient, owner_engine: AsyncEngine) -> None:
    h, base = await _history(client, owner_engine)
    first = await _page(client, base, h, "?limit=2")
    assert len(first["items"]) == 2
    assert first["next"]
    second = await _page(client, base, h, f"?limit=2&cursor={first['next']}")
    third = await _page(client, base, h, f"?limit=2&cursor={second['next']}")
    days = [i["day"] for p in (first, second, third) for i in p["items"]]
    assert days == ["2022-04-01", "2022-03-01", "2022-01-05", "2021-06-10", "2021-06-01"]
    assert third["next"] is None
    only = await _page(client, base, h, "?kinds=report&kinds=event")
    assert [i["kind"] for i in only["items"]] == ["report", "event"]
    assert (await _page(client, base, h, "?kinds=report&lab=other"))["items"] == []
    # a lab filter alone means that lab's reports
    assert [i["kind"] for i in (await _page(client, base, h, "?lab=УНТЭ"))["items"]] == ["report"]
    labs = (await client.get(f"{base}/timeline/labs", headers=h)).json()
    assert [(x["lab_name"], x["reports"]) for x in labs] == [("УНТЭ", 1)]
    huge = base64.urlsafe_b64encode(f"2025-01-01|99999999999|{uuid4()}".encode()).decode()
    odd = base64.urlsafe_b64encode(b"x|1|y").decode()
    for bad in ("?cursor=nope", f"?cursor={huge}", f"?cursor={odd}", "?kinds=draft", "?limit=0"):
        assert (await client.get(f"{base}/timeline{bad}", headers=h)).status_code == 422


async def test_a_reader_sees_it_and_a_stranger_does_not(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    _, base = await _history(client, owner_engine)
    doctor, username = await make_active_user(owner_engine)
    await _grant(owner_engine, base, doctor, "doctor")
    dh = _auth((await client.post("/api/v1/auth/login", json=login_body(username))).json()[
        "access_token"
    ])  # fmt: skip
    await client.post("/api/v1/me/consents", json={"items": REQUIRED}, headers=dh)
    assert len((await _page(client, base, dh))["items"]) == 5
    _, other_h, _ = await _profile(client, owner_engine)
    assert (await client.get(f"{base}/timeline", headers=other_h)).status_code == 404


async def _regimen(
    c: AsyncClient, base: str, h: dict[str, str], medication: str, day: str, amount: str
) -> dict[str, Any]:
    body = {
        "client_id": str(uuid4()),
        "effective_from": day,
        "dose_unit": "mg",
        "schedule": {"type": "daily", "times": [{"at": "08:00", "amount": amount}]},
    }
    r = await c.post(f"{base}/medications/{medication}/regimens", json=body, headers=h)
    assert r.status_code == 201, r.text
    out: dict[str, Any] = r.json()
    return out


async def test_stops_corrections_voided_and_planned_regimens(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    med = _medication(catalog_code="TACROLIMUS", started_on="2024-01-10")
    med["regimen"]["effective_from"] = "2024-01-10"
    m = (await client.post(f"{base}/medications", json=med, headers=h)).json()
    await _regimen(client, base, h, m["id"], "2024-03-01", "2")
    await _regimen(client, base, h, m["id"], "2024-03-01", "3")  # a same-day correction
    future = (datetime.now(UTC) + timedelta(days=30)).date().isoformat()
    await _regimen(client, base, h, m["id"], future, "1")
    gone = await _regimen(client, base, h, m["id"], future, "9")
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "update medication_regimens set voided_at = now(), void_reason = 'test'"
                " where id = cast(:i as uuid)"
            ),
            {"i": gone["id"]},
        )
        await conn.execute(
            bound_text(
                "update medications set stopped_on = '2024-06-01' where id = cast(:i as uuid)"
            ),
            {"i": m["id"]},
        )
    items = (await _page(client, base, h, "?kinds=regimen_changed&kinds=medication_stopped"))[
        "items"
    ]
    assert [(i["kind"], i["day"], i["planned"]) for i in items] == [
        ("regimen_changed", future, True),  # entered ahead: not history yet
        ("medication_stopped", "2024-06-01", False),  # the first day no longer taken (Q21)
        ("regimen_changed", "2024-03-01", False),  # one per day: the correction
    ]


async def test_a_voided_first_regimen_does_not_make_the_next_a_change(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    first = (datetime.now(UTC) + timedelta(days=10)).date().isoformat()
    second = (datetime.now(UTC) + timedelta(days=20)).date().isoformat()
    med = _medication(catalog_code="TACROLIMUS")
    med["regimen"]["effective_from"] = first
    r = await client.post(f"{base}/medications", json=med, headers=h)
    assert r.status_code == 201, r.text
    m = r.json()
    await _regimen(client, base, h, m["id"], second, "2")
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "update medication_regimens set voided_at = now(), void_reason = 'test'"
                " where medication_id ="
                " cast(:m as uuid) and effective_from = cast(:d as date)"
            ),
            {"m": m["id"], "d": date.fromisoformat(first)},
        )
    assert (await _page(client, base, h, "?kinds=regimen_changed"))["items"] == []


async def test_report_counts_days_and_rejected_reports(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    # 20:00 UTC is 04:00 the next day in Ulaanbaatar
    report = await _value(owner_engine, base, datetime(2022, 3, 31, 20, tzinfo=UTC), "7.0")
    async with owner_engine.connect() as conn, conn.begin():
        for n, flag in enumerate(("high", "abnormal", "critical_low", "no_reference", "unknown")):
            await conn.execute(
                bound_text(
                    "insert into lab_results (report_id, patient_id, position, raw_name,"
                    " raw_value, flag) select :r, patient_id, :n, 'x', '1',"
                    " cast(:f as result_flag) from lab_reports where id = :r"
                ),
                {"r": report, "n": n + 1, "f": flag},
            )
    await _value(owner_engine, base, datetime(2022, 5, 1, tzinfo=UTC), "8", status="rejected")
    (item,) = (await _page(client, base, h, "?kinds=report"))["items"]
    assert item["day"] == "2022-04-01"
    assert (item["results"], item["flagged"], item["unflagged"]) == (6, 3, 2)
