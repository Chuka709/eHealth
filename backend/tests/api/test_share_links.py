"""Share links (Phase 7.2): the owner makes one (token and PIN shown once), someone opens it
with the PIN and reads the profile through a short session; wrong PINs lock it."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from .conftest import ClientFactory
from .test_patients import _create, _signed_in

pytestmark = pytest.mark.db

Headers = dict[str, str]


async def _owner_link(
    c: AsyncClient, owner_engine: AsyncEngine, **body: object
) -> tuple[Headers, str, dict[str, object]]:
    _, owner = await _signed_in(c, owner_engine)
    _, profile = await _create(c, owner, full_name="Бат", relation="self")
    base = f"/api/v1/patients/{profile['id']}"
    r = await c.post(
        f"{base}/share-links",
        json={"scopes": ["summary", "labs"], "days": 7, **body},
        headers=owner,
    )
    assert r.status_code == 201
    assert r.headers["cache-control"] == "no-store"
    return owner, base, r.json()


async def test_make_open_read_and_revoke(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        owner, base, link = await _owner_link(c, owner_engine)
        assert len(str(link["token"])) == 43
        assert len(str(link["pin"])) == 6
        # neither the token nor the PIN can be read again
        [listed] = (await c.get(f"{base}/share-links", headers=owner)).json()
        assert "token" not in listed
        assert "pin" not in listed
        r = await c.post("/api/v1/share/open", json={"token": link["token"], "pin": link["pin"]})
        assert r.status_code == 200
        session = r.json()["session"]
        assert r.json()["scopes"] == ["summary", "labs"]
        h = {"X-Share-Session": session}
        r = await c.get("/api/v1/share/profile", headers=h)
        assert r.status_code == 200
        assert r.json()["full_name"] == "Бат"
        assert (await c.get("/api/v1/share/profile")).status_code == 401
        [view] = (await c.get(f"{base}/share-links/{link['id']}/views", headers=owner)).json()
        assert view["opened_at"]
        assert (
            await c.delete(f"{base}/share-links/{link['id']}", headers=owner)
        ).status_code == 204
        assert (await c.get("/api/v1/share/profile", headers=h)).status_code == 401


async def test_wrong_pins_answer_alike_and_the_fifth_locks_the_link(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        owner, base, link = await _owner_link(c, owner_engine)
        wrong = "000000" if link["pin"] != "000000" else "111111"
        unknown = await c.post("/api/v1/share/open", json={"token": "A" * 43, "pin": wrong})
        assert unknown.status_code == 401
        for _ in range(5):
            r = await c.post("/api/v1/share/open", json={"token": link["token"], "pin": wrong})
            assert r.status_code == 401
            assert r.json()["code"] == unknown.json()["code"]
        # locked: even the right PIN no longer opens it
        r = await c.post("/api/v1/share/open", json={"token": link["token"], "pin": link["pin"]})
        assert r.status_code == 401
        [listed] = (await c.get(f"{base}/share-links", headers=owner)).json()
        assert listed["revoked_reason"] == "pin_locked"
        notices = (await c.get("/api/v1/me/notifications", headers=owner)).json()
        assert [n["kind"] for n in notices] == ["share_link_locked"]


async def test_a_right_pin_gives_back_its_attempt_and_one_open_is_one_view(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        owner, base, link = await _owner_link(c, owner_engine, max_views=2)
        wrong = "000000" if link["pin"] != "000000" else "111111"
        for _ in range(4):
            await c.post("/api/v1/share/open", json={"token": link["token"], "pin": wrong})
        body = {"token": link["token"], "pin": link["pin"]}
        assert (await c.post("/api/v1/share/open", json=body)).status_code == 200
        assert (await c.post("/api/v1/share/open", json=body)).status_code == 200
        assert (await c.post("/api/v1/share/open", json=body)).status_code == 401  # 2 opens
        [listed] = (await c.get(f"{base}/share-links", headers=owner)).json()
        assert listed["view_count"] == 2
        assert listed["revoked_at"] is None


async def test_only_the_owner_manages_links_and_input_is_checked(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        _, base, link = await _owner_link(c, owner_engine)
        _, stranger = await _signed_in(c, owner_engine)
        assert (await c.get(f"{base}/share-links", headers=stranger)).status_code == 404
        r = await c.post(
            f"{base}/share-links", json={"scopes": ["labs"], "days": 7}, headers=stranger
        )
        assert r.status_code == 404
        _, owner = await _signed_in(c, owner_engine)
        _, mine = await _create(c, owner, full_name="Дорж", relation="self")
        mine_base = f"/api/v1/patients/{mine['id']}"
        for bad in (
            {"scopes": [], "days": 7},
            {"scopes": ["labs", "labs"], "days": 7},
            {"scopes": ["notes"], "days": 7},
            {"scopes": ["labs"], "days": 90},
            {"scopes": ["labs"], "days": 7, "date_from": "2026-02-01", "date_to": "2026-01-01"},
        ):
            r = await c.post(f"{mine_base}/share-links", json=bad, headers=owner)
            assert r.status_code == 422, bad
        # another profile's link id is not this profile's
        r = await c.delete(f"{mine_base}/share-links/{link['id']}", headers=owner)
        assert r.status_code == 404
        r = await c.post("/api/v1/share/open", json={"token": "short", "pin": "12"})
        assert r.status_code == 422


async def test_the_record_shows_only_the_links_sections(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        owner, base, _ = await _owner_link(c, owner_engine)
        r = await c.post(
            f"{base}/share-links",
            json={"scopes": ["transplant", "vitals"], "days": 1},
            headers=owner,
        )
        link = r.json()
        r = await c.post("/api/v1/share/open", json={"token": link["token"], "pin": link["pin"]})
        h = {"X-Share-Session": r.json()["session"]}
        r = await c.get("/api/v1/share/record", headers=h)
        assert r.status_code == 200
        assert r.headers["cache-control"] == "no-store"
        record = r.json()
        assert record["full_name"] == "Бат"
        assert record["transplants"] == []
        assert record["vitals"] == []
        for absent in ("summary", "labs", "medications", "events"):
            assert record[absent] is None, absent
        assert (await c.get("/api/v1/share/record")).status_code == 401
        # the viewer finishes: the session ends on the server
        assert (await c.post("/api/v1/share/close", headers=h)).status_code == 204
        assert (await c.get("/api/v1/share/record", headers=h)).status_code == 401


async def test_the_summary_carries_a_confirmed_no_known_allergies(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        owner, base, link = await _owner_link(c, owner_engine)
        day = (await c.put(f"{base}/no-known-allergies", headers=owner)).json()["confirmed_on"]
        r = await c.post("/api/v1/share/open", json={"token": link["token"], "pin": link["pin"]})
        h = {"X-Share-Session": r.json()["session"]}
        summary = (await c.get("/api/v1/share/record", headers=h)).json()["summary"]
        assert (summary["allergies"], summary["no_known_allergies_on"]) == ([], day)
