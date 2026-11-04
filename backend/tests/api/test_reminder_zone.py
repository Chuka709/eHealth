"""Reminder time zone (Q22, H7) and the monthly summary (Q23) over the API (Phase 2.5)."""

import asyncio
import calendar
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.db.sql import bound_text

from .conftest import ClientFactory
from .test_patients import _signed_in
from .test_records import _audit, _grant, _medication, _profile

pytestmark = pytest.mark.db

_UB = ZoneInfo("Asia/Ulaanbaatar")


@pytest.fixture
async def client(client_from: ClientFactory) -> AsyncIterator[AsyncClient]:
    async with client_from() as c:
        yield c


def _switch(
    tz: str = "Asia/Seoul", at: datetime | None = None, cid: str | None = None
) -> dict[str, str]:
    moment = at or datetime.now(UTC) - timedelta(minutes=1)
    return {"client_id": cid or str(uuid4()), "timezone": tz, "effective_at": moment.isoformat()}


async def test_home_until_the_first_switch(client: AsyncClient, owner_engine: AsyncEngine) -> None:
    _, h, base = await _profile(client, owner_engine)
    r = await client.get(f"{base}/timezone", headers=h)
    assert r.status_code == 200, r.text
    assert r.json() == {"home": "Asia/Ulaanbaatar", "current": "Asia/Ulaanbaatar", "switches": []}


async def test_a_switch_is_idempotent_and_audited_without_the_zone(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    body = _switch()
    first = await client.post(f"{base}/timezone", json=body, headers=h)
    assert first.status_code == 201, first.text
    again = await client.post(f"{base}/timezone", json=body, headers=h)
    assert again.status_code == 200
    assert again.json()["id"] == first.json()["id"]
    # the same client_id for another switch is a conflict, never "success"
    other = await client.post(
        f"{base}/timezone", json={**body, "timezone": "Asia/Tokyo"}, headers=h
    )
    assert other.status_code == 409
    assert other.json()["code"] == "record.conflict"
    got = (await client.get(f"{base}/timezone", headers=h)).json()
    assert got["current"] == "Asia/Seoul"
    assert len(got["switches"]) == 1
    entries = await _audit(owner_engine, base)
    assert ("timezone.switch", None) in entries
    assert all("Seoul" not in (diff or "") for _, diff in entries)


async def test_the_latest_switch_is_current(client: AsyncClient, owner_engine: AsyncEngine) -> None:
    _, h, base = await _profile(client, owner_engine)
    now = datetime.now(UTC)
    for tz, ago in (("Asia/Seoul", 120), ("Asia/Kolkata", 60), ("Asia/Ulaanbaatar", 30)):
        r = await client.post(
            f"{base}/timezone", json=_switch(tz, now - timedelta(minutes=ago)), headers=h
        )
        assert r.status_code == 201, r.text
    got = (await client.get(f"{base}/timezone", headers=h)).json()
    assert got["current"] == "Asia/Ulaanbaatar"
    assert [s["timezone"] for s in got["switches"]] == [
        "Asia/Ulaanbaatar",
        "Asia/Kolkata",
        "Asia/Seoul",
    ]


@pytest.mark.parametrize(
    "body",
    [
        _switch("Mars/Olympus"),
        _switch("asia/seoul"),
        _switch("Asia/Seoul/../x"),
        _switch(at=datetime.now(UTC) + timedelta(hours=1)),
        _switch(at=datetime.now(UTC) - timedelta(days=8)),
        {**_switch(), "effective_at": "2026-11-01T08:00:00"},  # no zone
        {**_switch(), "extra": 1},
    ],
)
async def test_bad_switches_are_refused(
    client: AsyncClient, owner_engine: AsyncEngine, body: dict[str, object]
) -> None:
    _, h, base = await _profile(client, owner_engine)
    r = await client.post(f"{base}/timezone", json=body, headers=h)
    assert r.status_code == 422, r.text


async def test_readers_see_but_do_not_switch_and_strangers_see_nothing(
    client: AsyncClient, client_from: ClientFactory, owner_engine: AsyncEngine
) -> None:
    _, _h, base = await _profile(client, owner_engine)
    async with client_from("203.0.113.11") as other:
        uid, oh = await _signed_in(other, owner_engine)
        assert (await other.get(f"{base}/timezone", headers=oh)).status_code == 404
        assert (await other.get(f"{base}/adherence?month=2026-10", headers=oh)).status_code == 404
        await _grant(owner_engine, base, uid, "viewer")
        assert (await other.get(f"{base}/timezone", headers=oh)).status_code == 200
        r = await other.post(f"{base}/timezone", json=_switch(), headers=oh)
        assert r.status_code == 403
        assert r.json()["code"] == "patient.read_only"


def _two_months_ago() -> tuple[str, int]:
    """A whole past month whose recording windows have all closed."""
    today = datetime.now(_UB).date()
    index = today.year * 12 + today.month - 1 - 2
    year, month = divmod(index, 12)
    month += 1
    return f"{year}-{month:02d}", calendar.monthrange(year, month)[1]


async def _entered_on(owner_engine: AsyncEngine, medication_id: str, when: str) -> None:
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "update medications set created_at = cast(:w as timestamptz)"
                " where id = cast(:i as uuid)"
            ),
            {"w": datetime.fromisoformat(when), "i": medication_id},
        )


async def test_monthly_summary_counts_planned_and_recorded_doses(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    med = (await client.post(f"{base}/medications", json=_medication(), headers=h)).json()
    prn = _medication(name="Парацетамол")
    prn["regimen"] = {
        "client_id": str(uuid4()),
        "effective_from": "2026-01-01",
        "schedule": {"type": "prn"},
    }
    assert (await client.post(f"{base}/medications", json=prn, headers=h)).status_code == 201
    await _entered_on(owner_engine, med["id"], "2026-01-01T00:00:00Z")
    month, days = _two_months_ago()
    year, mon = (int(p) for p in month.split("-"))
    first = datetime(year, mon, 1, 8, tzinfo=_UB).astimezone(UTC)
    second = datetime(year, mon, 1, 20, tzinfo=_UB).astimezone(UTC)
    for at, status in ((first, "taken"), (second, "skipped")):
        body = {
            "client_id": str(uuid4()),
            "medication_id": med["id"],
            "scheduled_at": at.isoformat(),
            "taken_at": at.isoformat() if status == "taken" else None,
            "status": status,
        }
        r = await client.post(f"{base}/intakes", json=body, headers=h)
        assert r.status_code == 201, r.text
    r = await client.get(f"{base}/adherence", params={"month": month}, headers=h)
    assert r.status_code == 200, r.text
    planned = days * 2
    expected = {
        "planned": planned,
        "taken": 1,
        "skipped": 1,
        "unrecorded": planned - 2,
        "open": 0,
        "percent_taken": str(100 // planned),
    }
    assert r.json()["total"] == expected
    # the as-needed medication plans no doses: not listed
    assert r.json()["medications"] == [{"medication_id": med["id"], **expected}]


@pytest.mark.parametrize("month", ["2099-01", "2026-13", "26-01", "2026-1"])
async def test_summary_months_are_past_or_current(
    client: AsyncClient, owner_engine: AsyncEngine, month: str
) -> None:
    _, h, base = await _profile(client, owner_engine)
    r = await client.get(f"{base}/adherence", params={"month": month}, headers=h)
    assert r.status_code == 422


async def test_an_empty_month_has_no_percent(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    r = await client.get(f"{base}/adherence", params={"month": "2025-01"}, headers=h)
    assert r.status_code == 200
    assert r.json()["total"] == {
        "planned": 0,
        "taken": 0,
        "skipped": 0,
        "unrecorded": 0,
        "open": 0,
        "percent_taken": None,
    }


async def test_doses_before_the_medication_was_entered_are_not_counted(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    """Medical review M2: tacrolimus taken since 2019 and entered today has no "not recorded"
    doses from before today."""
    _, h, base = await _profile(client, owner_engine)
    assert (
        await client.post(f"{base}/medications", json=_medication(), headers=h)
    ).status_code == 201
    month, _ = _two_months_ago()
    r = await client.get(f"{base}/adherence", params={"month": month}, headers=h)
    assert r.json()["total"]["planned"] == 0
    now = datetime.now(_UB)
    r = await client.get(
        f"{base}/adherence", params={"month": f"{now.year}-{now.month:02d}"}, headers=h
    )
    total = r.json()["total"]
    assert total["unrecorded"] == 0  # every dose so far is still within its recording window
    assert total["open"] == total["planned"]


async def test_switches_are_capped_per_day(client: AsyncClient, owner_engine: AsyncEngine) -> None:
    _, h, base = await _profile(client, owner_engine)
    zones = ["Asia/Seoul", "Asia/Ulaanbaatar"]
    for i in range(20):
        r = await client.post(f"{base}/timezone", json=_switch(zones[i % 2]), headers=h)
        assert r.status_code == 201, (i, r.text)
    r = await client.post(f"{base}/timezone", json=_switch(), headers=h)
    assert r.status_code == 429
    assert r.json()["code"] == "timezone.too_many"
    assert r.headers["Retry-After"] == "3600"


async def test_a_late_retry_of_a_stored_switch_is_that_switch(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    """A queued write retried after the week: the stored switch (200), never a refusal."""
    _, h, base = await _profile(client, owner_engine)
    body = _switch(at=datetime.now(UTC) - timedelta(days=6, hours=23))
    first = await client.post(f"{base}/timezone", json=body, headers=h)
    assert first.status_code == 201
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "update patient_timezones set effective_at = effective_at - interval '2 days',"
                " created_at = created_at - interval '2 days' where client_id = cast(:c as uuid)"
            ),
            {"c": body["client_id"]},
        )
    stored = (await client.get(f"{base}/timezone", headers=h)).json()
    moved = {**body, "effective_at": stored["switches"][0]["effective_at"]}
    again = await client.post(f"{base}/timezone", json=moved, headers=h)
    assert again.status_code == 200, again.text
    assert again.json()["id"] == first.json()["id"]
    other = await client.post(
        f"{base}/timezone", json={**moved, "client_id": str(uuid4())}, headers=h
    )
    assert other.status_code == 422


async def test_phones_get_only_the_switches_that_can_place_a_dose(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    """Security review L4: not a travel history - the switch in force two days ago and later."""
    _, h, base = await _profile(client, owner_engine)
    now = datetime.now(UTC)
    for tz, ago in (
        ("Asia/Seoul", 6 * 24),
        ("Asia/Kolkata", 5 * 24),
        ("Asia/Tokyo", 4 * 24),
        ("Asia/Seoul", 1),
    ):
        r = await client.post(
            f"{base}/timezone", json=_switch(tz, now - timedelta(hours=ago)), headers=h
        )
        assert r.status_code == 201, r.text
    got = (await client.get(f"{base}/timezone", headers=h)).json()
    assert [s["timezone"] for s in got["switches"]] == ["Asia/Seoul", "Asia/Tokyo"]
    assert got["current"] == "Asia/Seoul"


async def test_a_zone_unknown_to_the_server_does_not_break_the_summary(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    med = (
        await client.post(
            f"{base}/medications", json=_medication(reminder_timezone_mode="local"), headers=h
        )
    ).json()
    await _entered_on(owner_engine, med["id"], "2026-01-01T00:00:00Z")
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "insert into patient_timezones (patient_id, client_id, timezone, effective_at)"
                " values (cast(:p as uuid), gen_random_uuid(), 'Mars/Olympus',"
                " now() - interval '1 day')"
            ),
            {"p": base.rsplit("/", 1)[1]},
        )
    month, _ = _two_months_ago()
    r = await client.get(f"{base}/adherence", params={"month": month}, headers=h)
    assert r.status_code == 200, r.text


async def test_parallel_switches_respect_the_cap(
    client: AsyncClient, client_from: ClientFactory, owner_engine: AsyncEngine
) -> None:
    """Security re-review M1: one switch at a time per profile (advisory lock)."""
    _, h, base = await _profile(client, owner_engine)
    zones = ["Asia/Seoul", "Asia/Ulaanbaatar"]

    async def post(i: int) -> int:
        async with client_from() as c:
            r = await c.post(f"{base}/timezone", json=_switch(zones[i % 2]), headers=h)
            return r.status_code

    codes = await asyncio.gather(*(post(i) for i in range(25)))
    assert sorted(codes).count(201) == 20
    assert sorted(codes).count(429) == 5


async def test_caregivers_together_cannot_block_the_owner(
    client: AsyncClient, client_from: ClientFactory, owner_engine: AsyncEngine
) -> None:
    """Commit security review: two caregivers fill the profile cap (40); the owner still
    switches, a third caregiver does not."""
    _, h, base = await _profile(client, owner_engine)
    for n in range(3):
        async with client_from(f"203.0.113.{20 + n}") as other:
            uid, ch = await _signed_in(other, owner_engine)
            await _grant(owner_engine, base, uid, "caregiver")
            for _ in range(20 if n < 2 else 1):
                r = await other.post(f"{base}/timezone", json=_switch(), headers=ch)
                assert r.status_code == (201 if n < 2 else 429), r.text
    assert (await client.post(f"{base}/timezone", json=_switch(), headers=h)).status_code == 201


async def test_a_caregiver_cannot_use_up_the_owners_switches(
    client: AsyncClient, client_from: ClientFactory, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    async with client_from("203.0.113.12") as other:
        uid, ch = await _signed_in(other, owner_engine)
        await _grant(owner_engine, base, uid, "caregiver")
        for _ in range(20):
            assert (
                await other.post(f"{base}/timezone", json=_switch(), headers=ch)
            ).status_code == 201
        assert (await other.post(f"{base}/timezone", json=_switch(), headers=ch)).status_code == 429
    assert (await client.post(f"{base}/timezone", json=_switch(), headers=h)).status_code == 201


async def test_a_late_switch_never_starts_before_the_newest(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    """Medical re-review L-c: a switch from an offline phone, older than one already stored,
    starts when the newest did - doses already due are not moved."""
    _, h, base = await _profile(client, owner_engine)
    now = datetime.now(UTC)
    newest = await client.post(
        f"{base}/timezone", json=_switch("Asia/Seoul", now - timedelta(hours=2)), headers=h
    )
    late = _switch("Asia/Kolkata", now - timedelta(days=3))
    r = await client.post(f"{base}/timezone", json=late, headers=h)
    assert r.status_code == 201
    assert r.json()["effective_at"] == newest.json()["effective_at"]
    again = await client.post(f"{base}/timezone", json=late, headers=h)
    assert again.status_code == 200  # its retry is still that switch
    assert again.json()["id"] == r.json()["id"]
    got = (await client.get(f"{base}/timezone", headers=h)).json()
    assert got["current"] == "Asia/Kolkata"
