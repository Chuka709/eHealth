"""Admin user management end to end: register -> QR -> the user sets their own password;
identity check -> reset by SMS or QR; status, unlock, phone reveal; the issuing admin cannot
use the token (docs/04 §1, §6.1; Phase 1 DoD)."""

import time
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from labtrack.sms import ConsoleSmsSender, SmsTemplate, get_sms_sender

from .conftest import PASSWORD, ClientFactory, login_body
from .test_admin_auth import OFFICE, admin_login, bearer, make_admin

pytestmark = pytest.mark.db

NEW_PASSWORD = "Тэрэлжийн уулс өвөл 2027 цагаан"
NID = "УБ90010101"
HOME = "198.51.100.23"  # the user's phone, not the office


def _outbox() -> ConsoleSmsSender:
    sender = get_sms_sender()
    assert isinstance(sender, ConsoleSmsSender)
    return sender


async def _admin(c: AsyncClient, role: str = "super_admin") -> dict[str, str]:
    username, secret = await make_admin(role)
    status, body = await admin_login(c, username, secret)
    assert status == 200
    return bearer(body["session_token"])


async def _create(c: AsyncClient, h: dict[str, str], **extra: Any) -> tuple[UUID, str]:
    username = f"u{uuid4().hex[:10]}"
    body = {"username": username, "display_name": "Болд", "phone": "+976 9911-2233"} | extra
    r = await c.post("/api/v1/admin/users", json=body, headers=h)
    assert r.status_code == 201, r.json()
    return UUID(r.json()["id"]), username


def _token(link: str) -> str:
    return link.split("#", 1)[1]


async def _activate(client_from: ClientFactory, link: str, **headers: str) -> int:
    async with client_from(HOME) as phone:
        r = await phone.post(
            "/api/v1/auth/activate",
            json={"token": _token(link), "new_password": NEW_PASSWORD},
            headers=headers,
        )
    return r.status_code


async def test_registered_user_activates_with_qr_and_sets_own_password(
    client_from: ClientFactory,
) -> None:
    started = time.monotonic()
    async with client_from(OFFICE) as c:
        h = await _admin(c)
        uid, username = await _create(c, h, national_id=NID.lower())
        detail = (await c.get(f"/api/v1/admin/users/{uid}", headers=h)).json()
        assert (detail["account_status"], detail["phone_last4"]) == ("pending_activation", "2233")
        r = await c.post(
            f"/api/v1/admin/users/{uid}/tokens",
            json={"purpose": "activation", "channel": "in_person_qr"},
            headers=h,
        )
        assert r.status_code == 200
        link = r.json()["link"]
        assert link.startswith("labtrack://activate#")
        detail = (await c.get(f"/api/v1/admin/users/{uid}", headers=h)).json()
        assert detail["live_token"]["channel"] == "in_person_qr"
    assert await _activate(client_from, link) == 204
    async with client_from(HOME) as phone:
        login = await phone.post(
            "/api/v1/auth/login", json=login_body(username, password=NEW_PASSWORD)
        )
    assert login.status_code == 200
    assert time.monotonic() - started < 120  # DoD: <= 2 minutes


async def test_only_super_admins_register_and_issue(client_from: ClientFactory) -> None:
    async with client_from(OFFICE) as c:
        support = await _admin(c, "support")
        r = await c.post(
            "/api/v1/admin/users",
            json={"username": f"x{uuid4().hex[:8]}", "display_name": "X"},
            headers=support,
        )
        assert (r.status_code, r.json()["code"]) == (403, "admin.forbidden")


async def test_registration_validation(client_from: ClientFactory) -> None:
    async with client_from(OFFICE) as c:
        h = await _admin(c)
        _, username = await _create(c, h)
        dup = await c.post(
            "/api/v1/admin/users", json={"username": username, "display_name": "Б"}, headers=h
        )
        assert (dup.status_code, dup.json()["code"]) == (409, "admin.username_taken")
        bad_phone = await c.post(
            "/api/v1/admin/users",
            json={"username": f"p{uuid4().hex[:8]}", "display_name": "Б", "phone": "12345"},
            headers=h,
        )
        assert bad_phone.json()["code"] == "admin.invalid_phone"
        bad_nid = await c.post(
            "/api/v1/admin/users",
            json={"username": f"n{uuid4().hex[:8]}", "display_name": "Б", "national_id": "123"},
            headers=h,
        )
        assert bad_nid.status_code == 422
        # pydantic's echo of submitted values is never returned
        assert "123" not in bad_nid.text


async def test_search_lists_users_not_admins(client_from: ClientFactory) -> None:
    async with client_from(OFFICE) as c:
        h = await _admin(c)
        marker = uuid4().hex[:6]
        for i in range(3):
            await _create(c, h, display_name=f"Сараа{marker}{i}")
        page = (
            await c.get("/api/v1/admin/users", params={"q": marker, "limit": 2}, headers=h)
        ).json()
        assert len(page["items"]) == 2
        rest = (
            await c.get(
                "/api/v1/admin/users",
                params={"q": marker, "after": page["next_after"]},
                headers=h,
            )
        ).json()
        assert len(rest["items"]) == 1
        everyone = (await c.get("/api/v1/admin/users", params={"limit": 100}, headers=h)).json()
        assert {u["role"] for u in everyone["items"]} <= {"user", "doctor"}
        wildcard = (await c.get("/api/v1/admin/users", params={"q": "%"}, headers=h)).json()
        assert wildcard["items"] == []


async def test_reset_by_sms_after_identity_check(client_from: ClientFactory) -> None:
    async with client_from(OFFICE) as c:
        enrolling = await _admin(c)
        uid, username = await _create(c, enrolling, national_id=NID)
        # the admin who enrolled the national id may not reset this user (one-admin takeover)
        h = await _admin(c)
        r = await c.post(
            f"/api/v1/admin/users/{uid}/tokens",
            json={"purpose": "activation", "channel": "in_person_qr"},
            headers=h,
        )
        assert await _activate(client_from, r.json()["link"]) == 204
        async with client_from(HOME) as phone:
            old = (
                await phone.post(
                    "/api/v1/auth/login", json=login_body(username, password=NEW_PASSWORD)
                )
            ).json()
        wrong = await c.post(
            f"/api/v1/admin/users/{uid}/identity-check",
            json={"national_id": "УБ00000000"},
            headers=h,
        )
        assert wrong.json()["match"] is False
        # no reset without a matching check
        r = await c.post(
            f"/api/v1/admin/users/{uid}/tokens",
            json={
                "purpose": "admin_reset",
                "channel": "sms",
                "identity_check_id": wrong.json()["check_id"],
                "reason": "forgot_password",
            },
            headers=h,
        )
        assert r.json()["code"] == "admin.identity_check_required"
        ok = await c.post(
            f"/api/v1/admin/users/{uid}/identity-check", json={"national_id": NID}, headers=h
        )
        assert ok.json()["match"] is True
        sent_before = len(_outbox().outbox)
        r = await c.post(
            f"/api/v1/admin/users/{uid}/tokens",
            json={
                "purpose": "admin_reset",
                "channel": "sms",
                "identity_check_id": ok.json()["check_id"],
                "reason": "forgot_password",
            },
            headers=h,
        )
        assert r.status_code == 200
        assert r.json()["link"] is None  # the admin never sees an SMS token
    user_id, number, template, link = _outbox().outbox[-1]
    assert len(_outbox().outbox) == sent_before + 1
    assert (user_id, number, template) == (uid, "99112233", SmsTemplate.RESET_LINK)
    assert link is not None
    async with client_from(HOME) as phone:
        refreshed = await phone.post(
            "/api/v1/auth/refresh", json={"refresh_token": old["refresh_token"]}
        )
        assert refreshed.json()["code"] == "auth.admin_reset"
    assert await _activate(client_from, link) == 204


async def test_in_person_reset_still_notifies_the_registered_phone(
    client_from: ClientFactory,
) -> None:
    async with client_from(OFFICE) as c:
        uid, _ = await _create(c, await _admin(c), national_id=NID)
        h = await _admin(c)
        r = await c.post(
            f"/api/v1/admin/users/{uid}/tokens",
            json={"purpose": "activation", "channel": "in_person_qr"},
            headers=h,
        )
        assert await _activate(client_from, r.json()["link"]) == 204
        check = await c.post(
            f"/api/v1/admin/users/{uid}/identity-check", json={"national_id": NID}, headers=h
        )
        r = await c.post(
            f"/api/v1/admin/users/{uid}/tokens",
            json={
                "purpose": "admin_reset",
                "channel": "in_person_qr",
                "identity_check_id": check.json()["check_id"],
                "reason": "lost_device",
            },
            headers=h,
        )
        assert r.json()["link"]
    assert _outbox().outbox[-1][:3] == (uid, "99112233", SmsTemplate.RESET_NOTICE)


async def test_sms_needs_a_registered_phone(client_from: ClientFactory) -> None:
    async with client_from(OFFICE) as c:
        h = await _admin(c)
        r = await c.post(
            "/api/v1/admin/users",
            json={"username": f"np{uuid4().hex[:8]}", "display_name": "Б"},
            headers=h,
        )
        uid = r.json()["id"]
        r = await c.post(
            f"/api/v1/admin/users/{uid}/tokens",
            json={"purpose": "activation", "channel": "sms"},
            headers=h,
        )
        assert (r.status_code, r.json()["code"]) == (409, "admin.no_phone")


async def test_status_unlock_and_phone_reveal(client_from: ClientFactory) -> None:
    async with client_from(OFFICE) as c:
        h = await _admin(c)
        support = await _admin(c, "support")
        uid, _ = await _create(c, h)
        r = await c.post(
            f"/api/v1/admin/users/{uid}/tokens",
            json={"purpose": "activation", "channel": "in_person_qr"},
            headers=h,
        )
        assert await _activate(client_from, r.json()["link"]) == 204
        lock = await c.post(
            f"/api/v1/admin/users/{uid}/status",
            json={"status": "locked", "reason": "user_request"},
            headers=h,
        )
        assert lock.status_code == 204
        cannot = await c.post(
            f"/api/v1/admin/users/{uid}/status",
            json={"status": "disabled", "reason": "other"},
            headers=support,
        )
        assert cannot.status_code == 403
        unlock = await c.post(
            f"/api/v1/admin/users/{uid}/status",
            json={"status": "active", "reason": "identity_verified"},
            headers=support,
        )
        assert unlock.status_code == 204
        assert (
            await c.post(f"/api/v1/admin/users/{uid}/unlock-login", headers=support)
        ).status_code == 204
        phone = await c.post(f"/api/v1/admin/users/{uid}/phone", headers=support)
        assert phone.json() == {"phone": "99112233"}
        missing = await c.post(f"/api/v1/admin/users/{uuid4()}/phone", headers=support)
        assert missing.status_code == 404


async def test_a_user_bearer_does_not_burn_the_token_but_an_admin_session_does(
    client_from: ClientFactory,
) -> None:
    async with client_from(OFFICE) as c:
        h = await _admin(c)
        uid, _ = await _create(c, h)
        r = await c.post(
            f"/api/v1/admin/users/{uid}/tokens",
            json={"purpose": "activation", "channel": "in_person_qr"},
            headers=h,
        )
        link = r.json()["link"]
        # the issuing admin's own session presented with the token: refused and reported
        assert await _activate(client_from, link, Authorization=h["Authorization"]) == 400
        events = (await c.get("/api/v1/admin/security-events", headers=h)).json()
        assert any(
            e["action"] == "security.admin_token_self_use" and e["target_user_id"] == str(uid)
            for e in events
        )
        r = await c.post(
            f"/api/v1/admin/users/{uid}/tokens",
            json={"purpose": "activation", "channel": "in_person_qr"},
            headers=h,
        )
        fresh = r.json()["link"]
    # a stale non-admin bearer (e.g. an old app token) is not an admin credential
    assert await _activate(client_from, fresh, Authorization="Bearer not-an-admin-token") == 204


async def test_password_is_never_known_to_the_admin(client_from: ClientFactory) -> None:
    async with client_from(OFFICE) as c:
        h = await _admin(c)
        _, username = await _create(c, h)
        # a pending account has no password: nobody, the admin included, can log in
        r = await c.post("/api/v1/auth/login", json=login_body(username, password=PASSWORD))
        assert r.status_code == 401


async def test_the_enrolling_admin_must_leave_the_reset_to_another(
    client_from: ClientFactory,
) -> None:
    async with client_from(OFFICE) as c:
        h = await _admin(c)
        uid, _ = await _create(c, h, national_id=NID)
        r = await c.post(
            f"/api/v1/admin/users/{uid}/tokens",
            json={"purpose": "activation", "channel": "in_person_qr"},
            headers=h,
        )
        assert await _activate(client_from, r.json()["link"]) == 204
        check = await c.post(
            f"/api/v1/admin/users/{uid}/identity-check", json={"national_id": NID}, headers=h
        )
        r = await c.post(
            f"/api/v1/admin/users/{uid}/tokens",
            json={
                "purpose": "admin_reset",
                "channel": "in_person_qr",
                "identity_check_id": check.json()["check_id"],
                "reason": "forgot_password",
            },
            headers=h,
        )
        assert r.json()["code"] == "admin.reset_needs_other_admin"
