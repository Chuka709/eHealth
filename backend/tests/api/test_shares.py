"""Share routes (Phase 7.1): invite a doctor or a viewer by username, answer, read-only access,
who opened the profile, end and leave."""

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from .conftest import ClientFactory
from .test_caregivers import _username
from .test_patients import _create, _signed_in

pytestmark = pytest.mark.db

Headers = dict[str, str]


async def _shared(
    c: AsyncClient, owner_engine: AsyncEngine, level: str = "doctor", days: int | None = 7
) -> tuple[Headers, str, UUID, Headers]:
    _, owner = await _signed_in(c, owner_engine)
    _, profile = await _create(c, owner, full_name="Бат", relation="self")
    base = f"/api/v1/patients/{profile['id']}"
    doc_id, doc = await _signed_in(c, owner_engine)
    name = await _username(owner_engine, doc_id)
    r = await c.post(
        f"{base}/share-invitations",
        json={"username": name, "level": level, "days": days},
        headers=owner,
    )
    assert r.status_code == 202
    return owner, base, doc_id, doc


async def test_invite_accept_read_only_and_the_owner_sees_who_opened_it(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        owner, base, doc_id, doc = await _shared(c, owner_engine)
        # before accepting: nothing
        assert (await c.get(f"{base}/transplants", headers=doc)).status_code == 404
        [inv] = (await c.get("/api/v1/me/share-invitations", headers=doc)).json()
        assert (inv["level"], inv["access_days"]) == ("doctor", 7)
        # the invited person is told, in the app too
        [notice] = (await c.get("/api/v1/me/notifications", headers=doc)).json()
        assert (notice["kind"], notice["title_key"], notice["entity_id"]) == (
            "share_invite",
            "notification.share_invite",
            inv["id"],
        )
        assert "patient" not in str(inv).lower()  # the profile's name only after accepting
        r = await c.post(
            "/api/v1/me/share-invitations/respond",
            json={"invitation_id": inv["id"], "accept": True},
            headers=doc,
        )
        assert r.status_code == 204
        assert (await c.get(f"{base}/transplants", headers=doc)).status_code == 200
        # read-only: no writes, no management
        r = await c.delete(f"{base}/vitals/00000000-0000-4000-8000-000000000009", headers=doc)
        assert r.status_code == 403
        assert (await c.get(f"{base}/shares", headers=doc)).status_code == 403
        shares = (await c.get(f"{base}/shares", headers=owner)).json()
        [share] = shares["shares"]
        assert (share["user_id"], share["level"]) == (str(doc_id), "doctor")
        assert share["expires_at"] is not None
        assert share["last_viewed_at"] is not None
        [view] = (await c.get(f"{base}/share-views", headers=owner)).json()
        assert view["user_id"] == str(doc_id)
        # the owner's own reads are not noted
        await c.get(f"{base}/transplants", headers=owner)
        assert len((await c.get(f"{base}/share-views", headers=owner)).json()) == 1


async def test_any_username_gets_the_same_answer_and_strangers_see_nothing(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        owner, base, _, _doc = await _shared(c, owner_engine, "viewer", None)
        r = await c.post(
            f"{base}/share-invitations",
            json={"username": "nobody.at.all", "level": "viewer", "days": 30},
            headers=owner,
        )
        assert r.status_code == 202
        # only the real invitation is listed
        assert len((await c.get(f"{base}/shares", headers=owner)).json()["invitations"]) == 1
        for bad in ({"level": "caregiver", "days": 7}, {"level": "doctor", "days": 3}):
            r = await c.post(
                f"{base}/share-invitations", json={"username": "x.y.z", **bad}, headers=owner
            )
            assert r.status_code == 422
        _, stranger = await _signed_in(c, owner_engine)
        assert (await c.get(f"{base}/shares", headers=stranger)).status_code == 404
        assert (await c.get(f"{base}/share-views", headers=stranger)).status_code == 404
        assert (await c.get("/api/v1/me/share-invitations", headers=stranger)).json() == []


async def test_decline_cancel_end_and_leave(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        owner, base, doc_id, doc = await _shared(c, owner_engine)
        [inv] = (await c.get(f"{base}/shares", headers=owner)).json()["invitations"]
        assert (
            await c.delete(f"{base}/share-invitations/{inv['id']}", headers=owner)
        ).status_code == 204
        assert (await c.get("/api/v1/me/share-invitations", headers=doc)).json() == []
        r = await c.post(
            "/api/v1/me/share-invitations/respond",
            json={"invitation_id": inv["id"], "accept": True},
            headers=doc,
        )
        assert r.status_code == 404
        # invited again, accepted, ended by the owner
        name = await _username(owner_engine, doc_id)
        await c.post(
            f"{base}/share-invitations",
            json={"username": name, "level": "doctor", "days": 30},
            headers=owner,
        )
        [inv] = (await c.get("/api/v1/me/share-invitations", headers=doc)).json()
        await c.post(
            "/api/v1/me/share-invitations/respond",
            json={"invitation_id": inv["id"], "accept": True},
            headers=doc,
        )
        assert (await c.delete(f"{base}/shares/{doc_id}", headers=owner)).status_code == 204
        assert (await c.get(f"{base}/transplants", headers=doc)).status_code == 404
        assert (await c.delete(f"{base}/shares/{doc_id}", headers=owner)).status_code == 404
        # once more, and this time the doctor leaves
        await c.post(
            f"{base}/share-invitations",
            json={"username": name, "level": "doctor", "days": 1},
            headers=owner,
        )
        [inv] = (await c.get("/api/v1/me/share-invitations", headers=doc)).json()
        await c.post(
            "/api/v1/me/share-invitations/respond",
            json={"invitation_id": inv["id"], "accept": True},
            headers=doc,
        )
        assert (
            await c.post(
                "/api/v1/me/shares/leave", json={"patient_id": base.rsplit("/", 1)[1]}, headers=doc
            )
        ).status_code == 204
        assert (await c.get(f"{base}/transplants", headers=doc)).status_code == 404


async def test_a_doctor_opens_a_childs_shared_profile_while_the_parents_consents_stand(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    from .test_patients import REQUIRED, _child_birth  # noqa: PLC0415

    async with client_from() as c:
        _, parent = await _signed_in(c, owner_engine)
        await _create(c, parent, full_name="Аав", relation="self")
        _, child = await _create(
            c, parent, full_name="Хүү", relation="child", birth_date=_child_birth()
        )
        base = f"/api/v1/patients/{child['id']}"
        body = {"items": REQUIRED, "patient_id": child["id"]}
        assert (await c.post("/api/v1/me/consents", json=body, headers=parent)).status_code == 204
        doc_id, doc = await _signed_in(c, owner_engine)
        await c.post(
            f"{base}/share-invitations",
            json={"username": await _username(owner_engine, doc_id), "level": "doctor", "days": 7},
            headers=parent,
        )
        [inv] = (await c.get("/api/v1/me/share-invitations", headers=doc)).json()
        await c.post(
            "/api/v1/me/share-invitations/respond",
            json={"invitation_id": inv["id"], "accept": True},
            headers=doc,
        )
        assert (await c.get(f"{base}/transplants", headers=doc)).status_code == 200
        # the parent withdraws a required consent for the child: closed to the doctor too
        body = {"items": [{**REQUIRED[0], "granted": False}], "patient_id": child["id"]}
        assert (await c.post("/api/v1/me/consents", json=body, headers=parent)).status_code == 204
        r = await c.get(f"{base}/transplants", headers=doc)
        assert r.json()["code"] == "consent.profile_required"
