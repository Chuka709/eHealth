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

        def ai(processing: bool | None, cross_border: bool | None) -> list[dict[str, object]]:
            pairs: tuple[tuple[consents.Kind, bool | None], ...] = (
                ("ai_processing", processing),
                ("cross_border", cross_border),
            )
            return [
                {"kind": kind, "version": consents.VERSIONS[kind], "granted": granted}
                for kind, granted in pairs
                if granted is not None
            ]

        # The AI pair is given together (both are needed for AI extraction)...
        for half in (ai(True, None), ai(None, True), ai(True, False)):
            r = await c.post("/api/v1/me/consents", json={"items": half}, headers=h)
            assert r.status_code == 422
        # ...but withdrawing is never harder than giving: one alone is fine.
        r = await c.post("/api/v1/me/consents", json={"items": ai(False, None)}, headers=h)
        assert r.status_code == 204
        await c.post("/api/v1/me/consents", json={"items": ai(None, False)}, headers=h)
        after = {
            s["kind"]: s["granted"] for s in (await c.get("/api/v1/me/consents", headers=h)).json()
        }
        assert after == {k: k not in consents.AI_EXTRACTION for k in consents.VERSIONS}
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
        assert await _activate(client_from, r.json()["link"], username) == 204
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
        # A device that missed the response learns why on its next refresh (0011).
        refresh = await phone.post(
            "/api/v1/auth/refresh", json={"refresh_token": login.json()["refresh_token"]}
        )
        assert (refresh.status_code, refresh.json()["code"]) == (401, "auth.account_reported")
    async with client_from(OFFICE) as c:
        detail = (await c.get(f"/api/v1/admin/users/{uid}", headers=admin)).json()
        assert detail["account_status"] == "locked"
        events = (await c.get("/api/v1/admin/security-events", headers=admin)).json()
        assert any(
            e["action"] == "security.user_report" and e["target_user_id"] == str(uid)
            for e in events
        )
        # nobody lifts a self-reported lock by a status change (the password may be known)
        for who in (support, admin):
            r = await c.post(
                f"/api/v1/admin/users/{uid}/status",
                json={"status": "active", "reason": "identity_verified"},
                headers=who,
            )
            assert r.status_code in {403, 409}
        assert r.json()["code"] == "admin.reset_required"
        # recovery: another admin (not the one who enrolled the id) checks identity and resets
        other = await _admin(c)
        check = await c.post(
            f"/api/v1/admin/users/{uid}/identity-check",
            json={"national_id": "УБ90010101"},
            headers=other,
        )
        r = await c.post(
            f"/api/v1/admin/users/{uid}/tokens",
            json={
                "purpose": "admin_reset",
                "channel": "in_person_qr",
                "identity_check_id": check.json()["check_id"],
                "reason": "suspected_compromise",
            },
            headers=other,
        )
        link = r.json()["link"]
    async with client_from("198.51.100.23") as phone:
        old = await phone.post(
            "/api/v1/auth/login",
            json=login_body(username, password="Тэрэлжийн уулс өвөл 2027 цагаан"),
        )
        assert old.status_code == 401
    async with client_from("198.51.100.23") as phone:
        r = await phone.post(
            "/api/v1/auth/activate",
            json={
                "token": link.split("#", 1)[1],
                "username": username,
                "new_password": "Шинэ нууц үг Хангай 2028 ногоон",
            },
        )
        assert r.status_code == 204
        new = await phone.post(
            "/api/v1/auth/login",
            json=login_body(username, password="Шинэ нууц үг Хангай 2028 ногоон"),
        )
        assert new.status_code == 200


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


async def test_withdrawing_works_with_any_version_and_profile_changes_are_audited(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        uid, h = await _signed_in(c, owner_engine)
        await c.post("/api/v1/me/consents", json={"items": ALL}, headers=h)
        old_client = [{"kind": "cross_border", "version": "0", "granted": False}]
        assert (
            await c.post("/api/v1/me/consents", json={"items": old_client}, headers=h)
        ).status_code == 204
        state = {s["kind"]: s for s in (await c.get("/api/v1/me/consents", headers=h)).json()}
        assert state["cross_border"]["granted"] is False
        assert state["cross_border"]["granted_version"] == consents.VERSIONS["cross_border"]
        await c.patch("/api/v1/me", json={"display_name": "Шинэ нэр"}, headers=h)
    async with owner_engine.connect() as conn:
        diff = (
            await conn.execute(
                bound_text(
                    "select diff from audit_logs where action = 'user.profile_update'"
                    " and actor_id = :u"
                ),
                {"u": uid},
            )
        ).scalar_one()
    assert diff == {"fields": ["display_name"]}  # never the value


async def test_profile_update_touches_only_the_callers_row(owner_engine: AsyncEngine) -> None:
    me, other = (await make_active_user(owner_engine))[0], (await make_active_user(owner_engine))[0]
    engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
    try:
        async with as_user(engine, me) as conn:
            n = (
                await conn.execute(
                    bound_text("update users set display_name = 'x' where id = :o"), {"o": other}
                )
            ).rowcount
        assert n == 0
    finally:
        await engine.dispose()
