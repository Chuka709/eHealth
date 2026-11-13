"""Home dashboard API (Phase 6.3; docs/06 §1; rule 4, 7, 10b)."""

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.core.lab_drafts import LOCAL_ZONE
from labtrack.db.sql import bound_text
from labtrack.seed import run

from .conftest import ClientFactory, login_body, make_active_user
from .test_patients import REQUIRED, _auth
from .test_records import _grant, _medication, _profile, _transplant

pytestmark = pytest.mark.db

_NOW = datetime.now(UTC)


@pytest.fixture(scope="module", autouse=True)
async def seeded() -> None:
    """The catalog (cards are catalog tests)."""
    await run(os.environ["MIGRATION_DATABASE_URL"], Path(os.environ.get("SEED_DIR", "/seed")))


@pytest.fixture
async def client(client_from: ClientFactory) -> AsyncIterator[AsyncClient]:
    async with client_from() as c:
        yield c


async def _report(
    owner_engine: AsyncEngine,
    base: str,
    days_ago: int,
    rows: dict[str, tuple[str, str]],
    *,
    status: str = "confirmed",
    issues: tuple[str, ...] = (),
) -> UUID:
    """A report as review leaves it: test -> (value in the catalog unit, flag)."""
    patient = base.rsplit("/", 1)[1]
    report = uuid4()
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "insert into lab_reports (id, patient_id, lab_name, collected_at, status,"
                " confirmed_at) values (:i, cast(:p as uuid), 'lab', :at,"
                " cast(:s as report_status), case when :s = 'confirmed' then now() end)"
            ),
            {"i": report, "p": patient, "at": _NOW - timedelta(days=days_ago), "s": status},
        )
        for n, (code, (value, flag)) in enumerate(rows.items()):
            await conn.execute(
                bound_text(
                    "insert into lab_results (report_id, patient_id, position, test_code,"
                    " raw_name, raw_value, value_numeric, value_canonical, unit_canonical,"
                    " ref_text, ref_low_canonical, ref_high_canonical, flag, issues)"
                    " select :r, cast(:p as uuid), :n, :c, :c, cast(:v as text),"
                    " cast(:v as numeric), cast(:v as numeric), t.canonical_unit, '1 - 2', 1, 2,"
                    " cast(:f as result_flag), cast(:iss as text[])"
                    " from test_catalog t where t.code = :c"
                ),
                {"r": report, "p": patient, "n": n, "c": code, "v": value, "f": flag,
                 "iss": list(issues)},
            )  # fmt: skip
    return report


async def _dashboard(c: AsyncClient, base: str, h: dict[str, str]) -> dict[str, Any]:
    r = await c.get(f"{base}/dashboard", headers=h)
    assert r.status_code == 200, r.text
    body: dict[str, Any] = r.json()
    return body


async def test_kidney_cards_with_tacrolimus_and_only_confirmed_values(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    assert (await client.post(f"{base}/transplants", json=_transplant(), headers=h)).is_success
    med = _medication(catalog_code="TACROLIMUS")
    assert (await client.post(f"{base}/medications", json=med, headers=h)).is_success
    await _report(owner_engine, base, 30, {"CREA": ("1.00", "normal"), "TAC": ("6.1", "normal")})
    await _report(owner_engine, base, 10, {"CREA": ("1.20", "high")})
    await _report(owner_engine, base, 1, {"CREA": ("9.90", "critical_high")}, status="needs_review")
    body = await _dashboard(client, base, h)
    assert body["custom"] is False
    codes = [c["test_code"] for c in body["cards"]]
    assert codes == ["CREA", "TAC", "HGB", "K", "UPCR", "BKV_DNA"]
    crea = body["cards"][0]
    # the draft never reaches the dashboard (rule 4); numbers are strings (rule 7)
    assert (crea["latest"]["raw_value"], crea["latest"]["value"]) == ("1.20", "1.20")
    assert crea["latest"]["flag"] == "high"
    assert (crea["latest"]["ref_low"], crea["latest"]["ref_high"]) == ("1", "2")
    assert crea["change"]["percent"] == "20"
    assert crea["change"]["previous_value"] == "1.00"
    assert crea["change"]["previous_raw_value"] == "1.00"
    assert [p["value"] for p in crea["spark"]] == ["1.00", "1.20"]
    assert crea["spark_unit"] == crea["latest"]["unit"]
    hgb = body["cards"][2]
    assert (hgb["latest"], hgb["change"], hgb["spark"]) == (None, None, [])
    assert [a["test_code"] for a in body["attention"]] == ["CREA"]


async def test_attention_puts_a_lab_critical_mark_first_and_viral_loads_have_no_percent(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    await _report(owner_engine, base, 40, {"BKV_DNA": ("500", "normal")})
    await _report(owner_engine, base, 5, {"HGB": ("90", "low"), "BKV_DNA": ("5000", "high")})
    await _report(owner_engine, base, 3, {"K": ("6.9", "unknown")}, issues=("possible_critical",))
    r = await client.put(f"{base}/dashboard/cards", headers=h, json={"test_codes": ["BKV_DNA"]})
    assert r.status_code == 204, r.text
    body = await _dashboard(client, base, h)
    assert body["custom"] is True
    assert [a["test_code"] for a in body["attention"]] == ["K", "BKV_DNA", "HGB"]
    assert body["attention"][0]["latest"]["possibly_critical"] is True
    (bkv,) = body["cards"]
    assert bkv["change"] is None  # a viral load: compared on a log scale clinically (Q60)
    assert [p["value"] for p in bkv["spark"]] == ["500", "5000"]


async def test_own_list_is_kept_checked_and_reset(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    for bad in (["K", "K"], ["NOPE"], [f"X{n}" for n in range(25)], ["lower"]):
        r = await client.put(f"{base}/dashboard/cards", headers=h, json={"test_codes": bad})
        assert r.status_code == 422, bad
    r = await client.put(f"{base}/dashboard/cards", headers=h, json={"test_codes": ["K", "CREA"]})
    assert r.status_code == 204
    body = await _dashboard(client, base, h)
    assert [c["test_code"] for c in body["cards"]] == ["K", "CREA"]
    assert (await client.put(f"{base}/dashboard/cards", headers=h,
                             json={"test_codes": []})).status_code == 204  # fmt: skip
    assert (await _dashboard(client, base, h))["cards"] == []
    assert (await client.delete(f"{base}/dashboard/cards", headers=h)).status_code == 204
    assert (await _dashboard(client, base, h))["custom"] is False
    async with owner_engine.connect() as conn:
        actions = (
            await conn.execute(
                bound_text(
                    "select action, diff from audit_logs where patient_id = cast(:p as uuid)"
                    " and action like 'dashboard.%' order by at"
                ),
                {"p": base.rsplit("/", 1)[1]},
            )
        ).all()
    assert [a.action for a in actions] == ["dashboard.cards_set"] * 2 + ["dashboard.cards_reset"]
    assert all(a.diff is None for a in actions)  # no codes in the audit (rule 3)


async def test_readers_see_confirmed_values_but_never_change_the_cards(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    await _report(owner_engine, base, 2, {"K": ("6.1", "high")})
    await client.put(f"{base}/dashboard/cards", headers=h, json={"test_codes": ["K"]})
    doctor, username = await make_active_user(owner_engine)
    await _grant(owner_engine, base, doctor, "doctor")
    dh = _auth((await client.post("/api/v1/auth/login", json=login_body(username))).json()[
        "access_token"
    ])  # fmt: skip
    await client.post("/api/v1/me/consents", json={"items": REQUIRED}, headers=dh)
    body = await _dashboard(client, base, dh)
    # a reader never sees the writers' list: the organ's cards (none here - no transplant)
    assert (body["custom"], body["cards"]) == (False, [])
    (k,) = body["attention"]  # the confirmed value reaches a reader
    assert (k["test_code"], k["latest"]["value"], k["latest"]["flag"]) == ("K", "6.1", "high")
    for r in (
        await client.put(f"{base}/dashboard/cards", headers=dh, json={"test_codes": []}),
        await client.delete(f"{base}/dashboard/cards", headers=dh),
    ):
        assert r.status_code == 403


async def test_a_stranger_gets_nothing(client: AsyncClient, owner_engine: AsyncEngine) -> None:
    _, _, base = await _profile(client, owner_engine)
    _, other_h, _ = await _profile(client, owner_engine)
    assert (await client.get(f"{base}/dashboard", headers=other_h)).status_code in {403, 404}
    r = await client.put(f"{base}/dashboard/cards", headers=other_h, json={"test_codes": []})
    assert r.status_code in {403, 404}


async def test_an_expired_reader_gets_nothing(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    _, _, base = await _profile(client, owner_engine)
    reader, username = await make_active_user(owner_engine)
    await _grant(owner_engine, base, reader, "viewer")
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "update patient_access set expires_at = now() - interval '1 minute'"
                " where user_id = :u"
            ),
            {"u": reader},
        )
    rh = _auth((await client.post("/api/v1/auth/login", json=login_body(username))).json()[
        "access_token"
    ])  # fmt: skip
    await client.post("/api/v1/me/consents", json={"items": REQUIRED}, headers=rh)
    assert (await client.get(f"{base}/dashboard", headers=rh)).status_code in {403, 404}


async def test_a_retired_test_on_the_list_does_not_block_reordering(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    put = f"{base}/dashboard/cards"
    assert (await client.put(put, headers=h, json={"test_codes": ["K", "ESR"]})).status_code == 204
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text("update test_catalog set is_active = false where code = 'ESR'")
        )
    try:
        r = await client.put(put, headers=h, json={"test_codes": ["ESR", "K"]})
        assert r.status_code == 204, r.text
        # but it is not shown, and not added anew elsewhere
        assert [c["test_code"] for c in (await _dashboard(client, base, h))["cards"]] == ["K"]
        _, h2, base2 = await _profile(client, owner_engine)
        r = await client.put(f"{base2}/dashboard/cards", headers=h2, json={"test_codes": ["ESR"]})
        assert r.status_code == 422
    finally:
        async with owner_engine.connect() as conn, conn.begin():
            await conn.execute(
                bound_text("update test_catalog set is_active = true where code = 'ESR'")
            )


async def test_a_failed_graft_and_a_stopped_medicine_choose_no_cards(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    kidney = _transplant(transplant_date="2020-01-10")
    liver = _transplant(organ="liver", transplant_date="2024-05-02")
    for body in (kidney, liver):
        assert (await client.post(f"{base}/transplants", json=body, headers=h)).is_success
    tac = (await client.post(f"{base}/medications", headers=h,
                             json=_medication(catalog_code="TACROLIMUS"))).json()  # fmt: skip
    evr = _medication(catalog_code="EVEROLIMUS", name="Эверолимус")
    assert (await client.post(f"{base}/medications", json=evr, headers=h)).is_success
    today = datetime.now(UTC).astimezone(LOCAL_ZONE).date()
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text("update transplants set graft_status = 'failed' where organ = 'liver'"
                       " and patient_id = cast(:p as uuid)"),
            {"p": base.rsplit("/", 1)[1]},
        )  # fmt: skip
        # switched from tacrolimus to everolimus today: the stop day is not taken (Q21)
        await conn.execute(
            bound_text("update medications set stopped_on = :d where id = cast(:m as uuid)"),
            {"d": today, "m": tac["id"]},
        )
    codes = [c["test_code"] for c in (await _dashboard(client, base, h))["cards"]]
    assert codes == ["CREA", "EVR", "HGB", "K", "UPCR", "BKV_DNA"]
