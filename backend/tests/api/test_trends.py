"""Trend chart API (Phase 6.4; docs/06 §2; rule 4, 5, 7, 10; H23, H24)."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.db.sql import bound_text

from .conftest import ClientFactory, login_body, make_active_user
from .test_dashboard import seeded  # noqa: F401 - fixture (the catalog)
from .test_patients import REQUIRED, _auth
from .test_records import _grant, _medication, _profile, _transplant

pytestmark = pytest.mark.db


@pytest.fixture
async def client(client_from: ClientFactory) -> AsyncIterator[AsyncClient]:
    async with client_from() as c:
        yield c


async def _value(
    owner_engine: AsyncEngine,
    base: str,
    at: datetime,
    value: str,
    *,
    lab: str = "lab A",
    ref: tuple[str, str] = ("5", "10"),
    status: str = "confirmed",
    test: str = "TAC",
) -> UUID:
    patient = base.rsplit("/", 1)[1]
    report = uuid4()
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "insert into lab_reports (id, patient_id, lab_name, collected_at, status,"
                " confirmed_at) values (:i, cast(:p as uuid), :lab, :at,"
                " cast(:s as report_status), case when :s = 'confirmed' then now() end)"
            ),
            {"i": report, "p": patient, "lab": lab, "at": at, "s": status},
        )
        await conn.execute(
            bound_text(
                "insert into lab_results (report_id, patient_id, position, test_code, raw_name,"
                " raw_value, value_numeric, value_canonical, unit_canonical, ref_text,"
                " ref_low_canonical, ref_high_canonical, flag)"
                " select :r, cast(:p as uuid), 0, :c, :c, cast(:v as text), cast(:v as numeric),"
                " cast(:v as numeric), t.canonical_unit, :rt, cast(:lo as numeric),"
                " cast(:hi as numeric), 'normal' from test_catalog t where t.code = :c"
            ),
            {"r": report, "p": patient, "c": test, "v": value, "rt": f"{ref[0]}-{ref[1]}",
             "lo": ref[0], "hi": ref[1]},
        )  # fmt: skip
    return report


async def _trend(c: AsyncClient, base: str, h: dict[str, str], query: str = "") -> dict[str, Any]:
    r = await c.get(f"{base}/trends/TAC{query}", headers=h)
    assert r.status_code == 200, r.text
    body: dict[str, Any] = r.json()
    return body


async def test_points_keep_their_own_ranges_and_drafts_stay_out(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    t0 = datetime(2025, 3, 1, 8, tzinfo=UTC)
    await _value(owner_engine, base, t0, "7.2")
    await _value(owner_engine, base, t0 + timedelta(days=30), "8.40", lab="lab B", ref=("4", "12"))
    await _value(owner_engine, base, t0 + timedelta(days=40), "99", status="needs_review")
    body = await _trend(client, base, h)
    assert body["test"]["code"] == "TAC"
    assert [(p["value"], p["ref_low"], p["ref_high"], p["lab_name"]) for p in body["points"]] == [
        ("7.2", "5", "10", "lab A"),
        ("8.40", "4", "12", "lab B"),  # another lab: the band changes with it (rule 5)
    ]
    assert body["truncated"] is False
    assert body["axis"] is None  # no transplant recorded
    assert body["points"][0]["days_since_transplant"] is None
    assert body["points"][0]["raw_name"] == "TAC"  # the printed name (Q70)


async def test_period_filter(client: AsyncClient, owner_engine: AsyncEngine) -> None:
    _, h, base = await _profile(client, owner_engine)
    t0 = datetime(2025, 3, 1, 8, tzinfo=UTC)
    for d in (0, 100, 200):
        await _value(owner_engine, base, t0 + timedelta(days=d), str(5 + d / 100))
    q = "?since=2025-05-01T00:00:00%2B08:00&until=2025-08-01T00:00:00%2B08:00"
    assert [p["value"] for p in (await _trend(client, base, h, q))["points"]] == ["6.0"]
    for bad in ("?since=2025-05-01T00:00:00", "?since=2025-06-01T00:00Z&until=2025-05-01T00:00Z"):
        assert (await client.get(f"{base}/trends/TAC{bad}", headers=h)).status_code == 422
    assert (await client.get(f"{base}/trends/NOPE", headers=h)).status_code == 404
    assert (await client.get(f"{base}/trends/lower", headers=h)).status_code == 422


async def test_dose_steps_events_and_days_since_a_month_only_transplant(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    tx = _transplant(transplant_date="2025-01-01", date_precision="month")
    r = await client.post(f"{base}/transplants", json=tx, headers=h)
    assert r.status_code == 201, r.text
    med = _medication(catalog_code="TACROLIMUS")
    med["regimen"]["effective_from"] = "2025-02-01"
    r = await client.post(f"{base}/medications", json=med, headers=h)
    assert r.status_code == 201, r.text
    other = _medication(catalog_code=None, name="Витамин Д")  # not linked: no steps
    assert (await client.post(f"{base}/medications", json=other, headers=h)).is_success
    await _value(owner_engine, base, datetime(2025, 2, 10, 0, 30, tzinfo=UTC), "7.0")
    body = await _trend(client, base, h)
    # January 2025 known only to the month: counted from Jan 31, never ahead (H24)
    assert body["axis"]["day_zero"] == "2025-01-31"
    assert body["axis"]["approximate"] is True
    assert body["points"][0]["days_since_transplant"] == 10
    assert body["points"][0]["around_transplant"] is False
    (dose,) = body["doses"]
    (series,) = dose["series"]
    assert series["unit"] == "mg"
    assert [(s["starts_on"], s["ends_before"], s["amount"]) for s in series["steps"]] == [
        ("2025-02-01", None, "3.5")  # 2 mg + 1.5 mg a day, as recorded
    ]
    assert (series["unit_text"], series["steps"][0]["planned"]) == (None, False)
    assert [t["organ"] for t in body["transplants"]] == ["kidney"]


async def test_a_value_in_the_month_of_a_month_only_transplant_is_around_it(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    tx = _transplant(transplant_date="2025-01-01", date_precision="month")
    assert (await client.post(f"{base}/transplants", json=tx, headers=h)).status_code == 201
    await _value(owner_engine, base, datetime(2025, 1, 20, 1, tzinfo=UTC), "12.0")
    (point,) = (await _trend(client, base, h))["points"]
    assert (point["days_since_transplant"], point["around_transplant"]) == (None, True)


async def test_an_unknown_or_foreign_transplant_is_404_and_a_stranger_gets_nothing(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    r = await client.get(f"{base}/trends/TAC?transplant_id={uuid4()}", headers=h)
    assert r.status_code == 404
    _, other_h, other_base = await _profile(client, owner_engine)
    r = await client.post(f"{other_base}/transplants", json=_transplant(), headers=other_h)
    foreign = r.json()["id"]
    r = await client.get(f"{base}/trends/TAC?transplant_id={foreign}", headers=h)
    assert r.status_code == 404
    assert (await client.get(f"{base}/trends/TAC", headers=other_h)).status_code == 404


async def test_a_reader_sees_the_trend(client: AsyncClient, owner_engine: AsyncEngine) -> None:
    _, h, base = await _profile(client, owner_engine)
    assert (await client.post(f"{base}/transplants", json=_transplant(), headers=h)).is_success
    med = _medication(catalog_code="TACROLIMUS")
    assert (await client.post(f"{base}/medications", json=med, headers=h)).is_success
    await _value(owner_engine, base, datetime(2025, 3, 1, tzinfo=UTC), "7.0")
    doctor, username = await make_active_user(owner_engine)
    await _grant(owner_engine, base, doctor, "doctor")
    dh = _auth((await client.post("/api/v1/auth/login", json=login_body(username))).json()[
        "access_token"
    ])  # fmt: skip
    await client.post("/api/v1/me/consents", json={"items": REQUIRED}, headers=dh)
    body = await _trend(client, base, dh)
    assert [p["value"] for p in body["points"]] == ["7.0"]
    assert len(body["doses"]) == 1
    assert body["axis"] is not None


async def test_the_tested_list_has_confirmed_tests_only(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    t0 = datetime(2025, 3, 1, 8, tzinfo=UTC)
    await _value(owner_engine, base, t0, "7.2")
    await _value(owner_engine, base, t0 + timedelta(days=5), "7.9")
    await _value(owner_engine, base, t0 + timedelta(days=9), "1.0", test="CREA")
    await _value(owner_engine, base, t0 + timedelta(days=20), "5", test="K", status="needs_review")
    r = await client.get(f"{base}/trends", headers=h)
    assert r.status_code == 200, r.text
    assert [(x["test_code"], x["results"]) for x in r.json()] == [("CREA", 1), ("TAC", 2)]
