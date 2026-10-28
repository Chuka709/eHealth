"""/me: profile, consents (append-only, current version, minors), admin history,
notifications and the "Би хүсээгүй" report (Phase 1.7)."""

import os
from datetime import date
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from labtrack import consents
from labtrack.api.errors import AppError
from labtrack.db.sql import bound_text
from tests.rls.conftest import as_user

from .conftest import ClientFactory, login_body, make_active_user
from .test_admin_auth import OFFICE
from .test_admin_users import _activate, _admin, _create

pytestmark = pytest.mark.db

ALL = [{"kind": k, "version": v, "granted": True} for k, v in consents.VERSIONS.items()]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _signed_in(c: AsyncClient, owner_engine: AsyncEngine) -> tuple[UUID, dict[str, str]]:
    uid, username = await make_active_user(owner_engine)
    r = await c.post("/api/v1/auth/login", json=login_body(username))
    return uid, _auth(r.json()["access_token"])


async def test_profile_read_and_update(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        _, h = await _signed_in(c, owner_engine)
        me = (await c.get("/api/v1/me", headers=h)).json()
        assert (me["account_status"], me["locale"]) == ("active", "mn")
        r = await c.patch("/api/v1/me", json={"display_name": " Сараа ", "locale": "en"}, headers=h)
        assert (r.json()["display_name"], r.json()["locale"]) == ("Сараа", "en")
        for bad in ({"display_name": "Б\u202eБ"}, {"locale": "ru"}, {"role": "super_admin"}):
            assert (await c.patch("/api/v1/me", json=bad, headers=h)).status_code == 422


async def test_consents_are_appended_and_versioned(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        _, h = await _signed_in(c, owner_engine)
        before = {s["kind"]: s for s in (await c.get("/api/v1/me/consents", headers=h)).json()}
        assert set(before) == set(consents.VERSIONS)
        assert {k for k, s in before.items() if s["required"]} == {
            "terms",
            "privacy",
            "sensitive_data",
        }
        assert not any(s["granted"] for s in before.values())
        assert (
            await c.post("/api/v1/me/consents", json={"items": ALL}, headers=h)
        ).status_code == 204
        withdraw = [
            {
                "kind": "ai_processing",
                "version": consents.VERSIONS["ai_processing"],
                "granted": False,
            }
        ]
        await c.post("/api/v1/me/consents", json={"items": withdraw}, headers=h)
        after = {
            s["kind"]: s["granted"] for s in (await c.get("/api/v1/me/consents", headers=h)).json()
        }
        assert after == {k: k != "ai_processing" for k in consents.VERSIONS}
        old = [{"kind": "terms", "version": "0", "granted": True}]
        r = await c.post("/api/v1/me/consents", json={"items": old}, headers=h)
        assert (r.status_code, r.json()["code"]) == (409, "consent.version_outdated")
        dup = [ALL[0], ALL[0]]
        assert (
            await c.post("/api/v1/me/consents", json={"items": dup}, headers=h)
        ).status_code == 422
        unknown = [{"kind": "research", "version": "1", "granted": True}]
        r = await c.post("/api/v1/me/consents", json={"items": unknown}, headers=h)
        assert r.status_code == 422


async def test_a_new_text_version_asks_again(
    owner_engine: AsyncEngine, client_from: ClientFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with client_from() as c:
        _, h = await _signed_in(c, owner_engine)
        await c.post("/api/v1/me/consents", json={"items": ALL}, headers=h)
        monkeypatch.setitem(consents.VERSIONS, "privacy", "draft-2027-01")
        state = {s["kind"]: s for s in (await c.get("/api/v1/me/consents", headers=h)).json()}
    assert state["privacy"]["granted"] is False
    assert state["privacy"]["granted_version"] == "draft-2026-10"
    assert state["terms"]["granted"] is True


async def test_consent_for_a_minor_profile_only_by_its_owner(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        parent, h = await _signed_in(c, owner_engine)
        _, stranger = await _signed_in(c, owner_engine)
        async with owner_engine.connect() as conn, conn.begin():
            child = (
                await conn.execute(
                    bound_text(
                        "insert into patients (full_name, relation, birth_date, created_by)"
                        " values ('Хүүхэд', 'child', :b, :u) returning id"
                    ),
                    {"b": date(2016, 5, 1), "u": parent},
                )
            ).scalar_one()
            await conn.execute(
                bound_text(
                    "insert into patient_access (patient_id, user_id, level, granted_by)"
                    " values (:p, :u, 'owner', :u)"
                ),
                {"p": child, "u": parent},
            )
            adult_self = (
                await conn.execute(
                    bound_text(
                        "insert into patients (full_name, relation, birth_date, created_by)"
                        " values ('Эцэг', 'self', '1980-01-01', :u) returning id"
                    ),
                    {"u": parent},
                )
            ).scalar_one()
            await conn.execute(
                bound_text(
                    "insert into patient_access (patient_id, user_id, level, granted_by)"
                    " values (:p, :u, 'owner', :u)"
                ),
                {"p": adult_self, "u": parent},
            )
        body = {"items": ALL[:1], "patient_id": str(child)}
        assert (await c.post("/api/v1/me/consents", json=body, headers=h)).status_code == 204
        r = await c.post("/api/v1/me/consents", json=body, headers=stranger)
        assert (r.status_code, r.json()["code"]) == (403, "consent.not_allowed")
        # an adult's profile (even one's own "self") takes no proxy consent
        r = await c.post(
            "/api/v1/me/consents",
            json={"items": ALL[:1], "patient_id": str(adult_self)},
            headers=h,
        )
        assert r.status_code == 403
        own = {
            s["kind"]: s["granted"] for s in (await c.get("/api/v1/me/consents", headers=h)).json()
        }
        assert own["terms"] is False  # the child's consent is not the parent's


async def test_admin_history_notifications_and_report(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from(OFFICE) as c:
        admin = await _admin(c)
        support = await _admin(c, "support")
        uid, username = await _create(c, admin)
        r = await c.post(
            f"/api/v1/admin/users/{uid}/tokens",
            json={"purpose": "activation", "channel": "in_person_qr"},
            headers=admin,
        )
        assert await _activate(client_from, r.json()["link"]) == 204
        await c.put(
            f"/api/v1/admin/users/{uid}/identity", json={"national_id": "УБ90010101"}, headers=admin
        )
    async with client_from("198.51.100.23") as phone:
        login = await phone.post(
            "/api/v1/auth/login",
            json=login_body(username, password="Тэрэлжийн уулс өвөл 2027 цагаан"),
        )
        h = _auth(login.json()["access_token"])
        actions = [
            a["action"] for a in (await phone.get("/api/v1/me/admin-actions", headers=h)).json()
        ]
        assert {"admin.user_create", "admin.token_issue", "admin.identity_set"} <= set(actions)
        assert all(
            "actor_id" not in a
            for a in (await phone.get("/api/v1/me/admin-actions", headers=h)).json()
        )
        unread = (await phone.get("/api/v1/me/notifications?unread_only=true", headers=h)).json()
        assert [n["kind"] for n in unread] == ["admin_action"]
        nid = unread[0]["id"]
        assert (
            await phone.post(f"/api/v1/me/notifications/{nid}/read", headers=h)
        ).status_code == 204
        assert (
            await phone.get("/api/v1/me/notifications?unread_only=true", headers=h)
        ).json() == []
        assert (
            await phone.post("/api/v1/me/notifications/999999999/read", headers=h)
        ).status_code == 404

        r = await phone.post("/api/v1/me/report-unwanted-admin-action", headers=h)
        assert r.status_code == 204
        assert (await phone.get("/api/v1/me", headers=h)).status_code == 401  # sessions ended
    async with client_from(OFFICE) as c:
        detail = (await c.get(f"/api/v1/admin/users/{uid}", headers=admin)).json()
        assert detail["account_status"] == "locked"
        events = (await c.get("/api/v1/admin/security-events", headers=admin)).json()
        assert any(
            e["action"] == "security.user_report" and e["target_user_id"] == str(uid)
            for e in events
        )
        # support cannot lift a self-reported lock; a super admin can
        r = await c.post(
            f"/api/v1/admin/users/{uid}/status",
            json={"status": "active", "reason": "identity_verified"},
            headers=support,
        )
        assert r.status_code == 403
        r = await c.post(
            f"/api/v1/admin/users/{uid}/status",
            json={"status": "active", "reason": "identity_verified"},
            headers=admin,
        )
        assert r.status_code == 204


async def test_report_needs_a_recent_admin_action(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        _, h = await _signed_in(c, owner_engine)
        r = await c.post("/api/v1/me/report-unwanted-admin-action", headers=h)
        assert (r.status_code, r.json()["code"]) == (409, "me.no_recent_admin_action")
        assert (await c.get("/api/v1/me", headers=h)).status_code == 200


async def test_consent_gate_for_future_phi_routes(owner_engine: AsyncEngine) -> None:
    uid, _ = await make_active_user(owner_engine)
    engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
    try:
        gate = consents.require(consents.REQUIRED)
        async with as_user(engine, uid) as conn:
            session = AsyncSession(bind=conn)
            with pytest.raises(AppError, match=r"consent\.required"):
                await gate(session)
            for kind in consents.REQUIRED:
                await session.execute(
                    bound_text(
                        "insert into consents (user_id, kind, version, granted)"
                        " values (app_user_id(), :k, :v, true)"
                    ),
                    {"k": kind, "v": consents.VERSIONS[kind]},
                )
            await gate(session)
    finally:
        await engine.dispose()
