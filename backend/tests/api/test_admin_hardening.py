"""Final 1.6 security review: input hardening, quotas, SMS failures, no-store, DB errors."""

from uuid import uuid4

import pytest

from labtrack.admin.users import _db_error
from labtrack.sms import ConsoleSmsSender, get_sms_sender

from .conftest import ClientFactory
from .test_admin_users import NID, _activate, _admin, _create

pytestmark = pytest.mark.db


@pytest.mark.parametrize("phone", ["9١٢٣٤٥٦٧", "９" * 8, "99112233\u200b"])
async def test_non_ascii_digits_are_not_phone_numbers(
    client_from: ClientFactory, phone: str
) -> None:
    async with client_from("10.20.0.5") as c:
        h = await _admin(c)
        r = await c.post(
            "/api/v1/admin/users",
            json={"username": f"p{uuid4().hex[:8]}", "display_name": "Б", "phone": phone},
            headers=h,
        )
    if phone.endswith("\u200b"):  # separators are dropped, the 8 ASCII digits stay
        assert r.status_code == 201
    else:
        assert (r.status_code, r.json()["code"]) == (422, "admin.invalid_phone")


async def test_display_names_reject_control_and_bidi_characters(
    client_from: ClientFactory,
) -> None:
    async with client_from("10.20.0.5") as c:
        h = await _admin(c)
        for name in ("Бат\u202eтаБ", "Бат\x07"):
            r = await c.post(
                "/api/v1/admin/users",
                json={"username": f"d{uuid4().hex[:8]}", "display_name": name},
                headers=h,
            )
            assert r.status_code == 422


async def test_support_limits(client_from: ClientFactory) -> None:
    async with client_from("10.20.0.5") as c:
        h = await _admin(c)
        support = await _admin(c, "support")
        uid, _ = await _create(c, h, national_id=NID)
        for method, path, body in (
            (
                "post",
                f"/api/v1/admin/users/{uid}/tokens",
                {"purpose": "activation", "channel": "in_person_qr"},
            ),
            ("post", f"/api/v1/admin/users/{uid}/identity-check", {"national_id": NID}),
            ("put", f"/api/v1/admin/users/{uid}/identity", {"national_id": NID}),
            ("get", "/api/v1/admin/security-events", None),
        ):
            r = await c.request(method, path, json=body, headers=support)
            assert r.status_code == 403, path
        r = await c.post(
            f"/api/v1/admin/users/{uid}/status",
            json={"status": "locked", "reason": "other"},
            headers=support,
        )
        assert r.status_code in {403, 409}  # pending accounts cannot be locked either


async def test_phone_reveal_and_lockout_clear_are_rationed(client_from: ClientFactory) -> None:
    async with client_from("10.20.0.5") as c:
        h = await _admin(c)
        support = await _admin(c, "support")
        uid, _ = await _create(c, h)
        for _ in range(3):
            r = await c.post(f"/api/v1/admin/users/{uid}/unlock-login", headers=support)
            assert r.status_code == 204
        r = await c.post(f"/api/v1/admin/users/{uid}/unlock-login", headers=support)
        assert (r.status_code, r.json()["code"]) == (429, "admin.lockout_clear_limit")
        for _ in range(20):
            assert (
                await c.post(f"/api/v1/admin/users/{uid}/phone", headers=support)
            ).status_code == 200
        r = await c.post(f"/api/v1/admin/users/{uid}/phone", headers=support)
        assert (r.status_code, r.json()["code"]) == (429, "admin.phone_reveal_limit")


class _FailingSender(ConsoleSmsSender):
    async def send(self, **_: object) -> None:  # type: ignore[override]
        raise RuntimeError("gateway down")


async def test_sms_failures(client_from: ClientFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    async with client_from("10.20.0.5") as c:
        enrolling = await _admin(c)
        uid, username = await _create(c, enrolling, national_id=NID)
        r = await c.post(
            f"/api/v1/admin/users/{uid}/tokens",
            json={"purpose": "activation", "channel": "in_person_qr"},
            headers=enrolling,
        )
        assert await _activate(client_from, r.json()["link"], username) == 204
        h = await _admin(c)
        monkeypatch.setattr(get_sms_sender(), "send", _FailingSender().send)
        check = await c.post(
            f"/api/v1/admin/users/{uid}/identity-check", json={"national_id": NID}, headers=h
        )
        # in person: the QR survives a failed notice, the admin is told it was not sent
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
        assert r.status_code == 200
        assert r.json()["link"]
        assert r.json()["notice_sent"] is False
        # SMS link: a failed send is an error (the token stands; issue again)
        other, _ = await _create(c, h)
        r = await c.post(
            f"/api/v1/admin/users/{other}/tokens",
            json={"purpose": "activation", "channel": "sms"},
            headers=h,
        )
        assert (r.status_code, r.json()["code"]) == (502, "admin.sms_failed")


async def test_responses_are_not_cached(client_from: ClientFactory) -> None:
    async with client_from("10.20.0.5") as c:
        h = await _admin(c)
        r = await c.get("/api/v1/admin/users", headers=h)
        assert r.headers["cache-control"] == "no-store"
        r = await c.post(
            "/api/v1/auth/login", json={"username": "nobody1", "password": "x", "platform": "ios"}
        )
        assert r.headers["cache-control"] == "no-store"


def test_unknown_database_errors_say_nothing() -> None:
    from sqlalchemy.exc import DBAPIError  # noqa: PLC0415

    class PgError(Exception):
        sqlstate = "23514"
        constraint_name = "users_display_name_check"
        message = "new row violates check constraint; Failing row contains (Болд, 99112233)"

    orig = Exception("wrapped")
    orig.__cause__ = PgError()
    err = _db_error(DBAPIError("select 1", None, orig))
    assert (err.status, err.code) == (500, "internal")
    assert "Болд" not in str(err)
