"""Account deletion through the API: request with password, admin view and cancellation,
purge after 30 days (Phase 1.8; App Store / Play in-app deletion)."""

import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.db.sql import bound_text
from labtrack.worker.maintenance import run_daily

from .conftest import ClientFactory, login_body
from .test_admin_auth import OFFICE
from .test_admin_users import NEW_PASSWORD, NID, _activate, _admin, _create

pytestmark = pytest.mark.db

HOME = "198.51.100.23"


async def _active_user(client_from: ClientFactory) -> tuple[str, str, dict[str, str]]:
    async with client_from(OFFICE) as c:
        enrolling = await _admin(c)
        uid, username = await _create(c, enrolling, national_id=NID)
        r = await c.post(
            f"/api/v1/admin/users/{uid}/tokens",
            json={"purpose": "activation", "channel": "in_person_qr"},
            headers=enrolling,
        )
    assert await _activate(client_from, r.json()["link"]) == 204
    async with client_from(HOME) as phone:
        login = await phone.post(
            "/api/v1/auth/login", json=login_body(username, password=NEW_PASSWORD)
        )
    return str(uid), username, {"Authorization": f"Bearer {login.json()['access_token']}"}


async def test_delete_needs_the_password_and_signs_out_everywhere(
    client_from: ClientFactory,
) -> None:
    uid, username, h = await _active_user(client_from)
    async with client_from(HOME) as phone:
        wrong = await phone.post(
            "/api/v1/me/delete", json={"password": "Буруу нууц 2026!"}, headers=h
        )
        assert wrong.status_code == 401
        assert (await phone.get("/api/v1/me", headers=h)).status_code == 200  # nothing happened
        r = await phone.post("/api/v1/me/delete", json={"password": NEW_PASSWORD}, headers=h)
        assert r.status_code == 202
        scheduled = datetime.fromisoformat(r.json()["scheduled_for"])
        assert timedelta(days=29) < scheduled - datetime.now(UTC) <= timedelta(days=30)
        assert (await phone.get("/api/v1/me", headers=h)).status_code == 401
        again = await phone.post(
            "/api/v1/auth/login", json=login_body(username, password=NEW_PASSWORD)
        )
        assert again.status_code == 401
    async with client_from(OFFICE) as c:
        admin = await _admin(c)
        pending = (
            await c.get(
                "/api/v1/admin/users",
                params={"deletion_pending": "true", "q": username},
                headers=admin,
            )
        ).json()["items"]
        assert [u["id"] for u in pending] == [uid]
        assert pending[0]["deletion_scheduled_for"]
        active = (await c.get("/api/v1/admin/users", params={"q": username}, headers=admin)).json()
        assert active["items"] == []


async def test_cancellation_goes_through_a_reset(client_from: ClientFactory) -> None:
    uid, username, h = await _active_user(client_from)
    async with client_from(HOME) as phone:
        await phone.post("/api/v1/me/delete", json={"password": NEW_PASSWORD}, headers=h)
    async with client_from(OFFICE) as c:
        admin = await _admin(c)  # not the admin who enrolled the national id
        assert (
            await c.post(f"/api/v1/admin/users/{uid}/cancel-deletion", headers=admin)
        ).status_code == 204
        detail = (await c.get(f"/api/v1/admin/users/{uid}", headers=admin)).json()
        assert (detail["account_status"], detail["deletion_scheduled_for"]) == ("locked", None)
        r = await c.post(
            f"/api/v1/admin/users/{uid}/status",
            json={"status": "active", "reason": "user_request"},
            headers=admin,
        )
        assert r.json()["code"] == "admin.reset_required"
        check = await c.post(
            f"/api/v1/admin/users/{uid}/identity-check", json={"national_id": NID}, headers=admin
        )
        r = await c.post(
            f"/api/v1/admin/users/{uid}/tokens",
            json={
                "purpose": "admin_reset",
                "channel": "in_person_qr",
                "identity_check_id": check.json()["check_id"],
                "reason": "other",
            },
            headers=admin,
        )
        again = await c.post(f"/api/v1/admin/users/{uid}/cancel-deletion", headers=admin)
        assert (again.status_code, again.json()["code"]) == (409, "admin.no_pending_deletion")
    assert await _activate(client_from, r.json()["link"]) == 204
    async with client_from(HOME) as phone:
        login = await phone.post(
            "/api/v1/auth/login",
            json=login_body(username, password="Тэрэлжийн уулс өвөл 2027 цагаан"),
        )
    assert login.status_code == 200


async def test_purged_accounts_are_gone(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    uid, _, h = await _active_user(client_from)
    async with client_from(HOME) as phone:
        await phone.post("/api/v1/me/delete", json={"password": NEW_PASSWORD}, headers=h)
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text("update users set deleted_at = now() - interval '31 days' where id = :u"),
            {"u": uid},
        )
    await run_daily(os.environ["TEST_MAINT_DATABASE_URL"])
    async with client_from(OFFICE) as c:
        admin = await _admin(c)
        r = await c.get(f"/api/v1/admin/users/{uid}", headers=admin)
        assert r.status_code == 404
        r = await c.post(f"/api/v1/admin/users/{uid}/cancel-deletion", headers=admin)
        assert r.status_code == 409
