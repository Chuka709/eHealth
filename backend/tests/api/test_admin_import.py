"""CSV bulk registration: preview, commit the same file, all or none (docs/04 §1)."""

import hashlib
import logging
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.db.sql import bound_text

from .conftest import ClientFactory
from .test_admin_auth import OFFICE, admin_login, bearer, make_admin

pytestmark = pytest.mark.db

CSV = {"Content-Type": "text/csv"}


async def _admin_headers(c: object, role: str = "super_admin") -> dict[str, str]:
    username, secret = await make_admin(role)
    _, body = await admin_login(c, username, secret)  # type: ignore[arg-type]
    return bearer(body["session_token"]) | CSV


def _file(*rows: str) -> bytes:
    return ("username,display_name,phone\n" + "\n".join(rows) + "\n").encode()


async def test_preview_then_commit_creates_pending_accounts(
    owner_engine: AsyncEngine, client_from: ClientFactory, caplog: pytest.LogCaptureFixture
) -> None:
    tag = uuid4().hex[:8]
    data = _file(f"a{tag},Нямсүрэн,99887766", f"b{tag},Ганбаатар,")
    caplog.set_level(logging.DEBUG)
    async with client_from(OFFICE) as c:
        h = await _admin_headers(c)
        preview = (
            await c.post("/api/v1/admin/users/import/preview", content=data, headers=h)
        ).json()
        assert preview["problems"] == []
        assert [r["phone_last4"] for r in preview["rows"]] == ["7766", None]
        sha = hashlib.sha256(data).hexdigest()
        assert preview["sha256"] == sha
        r = await c.post(
            "/api/v1/admin/users/import", params={"sha256": sha}, content=data, headers=h
        )
        assert r.json() == {"created": 2}
    async with owner_engine.connect() as conn:
        statuses = (
            await conn.execute(
                bound_text(
                    "select account_status, password_hash is null as no_pw from users"
                    " where username in (:a, :b)"
                ),
                {"a": f"a{tag}", "b": f"b{tag}"},
            )
        ).all()
        audit = (
            await conn.execute(
                bound_text(
                    "select diff from audit_logs where action = 'admin.csv_import'"
                    " and diff ->> 'sha256' = :s"
                ),
                {"s": sha},
            )
        ).scalar_one()
    assert {tuple(s) for s in statuses} == {("pending_activation", True)}
    assert audit == {"sha256": sha, "rows": 2}  # no names, no numbers
    for secret in ("Нямсүрэн", "Ганбаатар", "99887766"):
        assert secret not in caplog.text


async def test_commit_refuses_a_changed_file(client_from: ClientFactory) -> None:
    data = _file(f"c{uuid4().hex[:8]},Бат,")
    async with client_from(OFFICE) as c:
        h = await _admin_headers(c)
        r = await c.post(
            "/api/v1/admin/users/import",
            params={"sha256": hashlib.sha256(b"other").hexdigest()},
            content=data,
            headers=h,
        )
        assert (r.status_code, r.json()["code"]) == (409, "admin.import_changed")


async def test_one_bad_row_creates_nothing(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    tag = uuid4().hex[:8]
    async with client_from(OFFICE) as c:
        h = await _admin_headers(c)
        existing = _file(f"x{tag},Бат,")
        await c.post(
            "/api/v1/admin/users/import",
            params={"sha256": hashlib.sha256(existing).hexdigest()},
            content=existing,
            headers=h,
        )
        data = _file(f"y{tag},Дорж,", f"x{tag},Бат дахин,")
        r = await c.post(
            "/api/v1/admin/users/import",
            params={"sha256": hashlib.sha256(data).hexdigest()},
            content=data,
            headers=h,
        )
        assert r.status_code == 422
        assert r.json()["problems"] == [{"row": 3, "field": "username_taken"}]
        invalid = _file(f"z{tag},Сараа,123")
        r = await c.post(
            "/api/v1/admin/users/import",
            params={"sha256": hashlib.sha256(invalid).hexdigest()},
            content=invalid,
            headers=h,
        )
        assert r.json()["problems"] == [{"row": 2, "field": "phone"}]
        assert "123" not in r.text.replace(hashlib.sha256(invalid).hexdigest(), "")
    async with owner_engine.connect() as conn:
        created = (
            await conn.execute(
                bound_text("select count(*) from users where username in (:y, :z)"),
                {"y": f"y{tag}", "z": f"z{tag}"},
            )
        ).scalar_one()
    assert created == 0


async def test_import_is_super_admin_only_and_size_limited(client_from: ClientFactory) -> None:
    async with client_from(OFFICE) as c:
        support = await _admin_headers(c, "support")
        r = await c.post(
            "/api/v1/admin/users/import/preview", content=_file("a1b,Б,"), headers=support
        )
        assert r.status_code == 403
        h = await _admin_headers(c)
        big = b"username,display_name\n" + b"x" * 1_000_001
        r = await c.post("/api/v1/admin/users/import/preview", content=big, headers=h)
        assert (r.status_code, r.json()["code"]) == (413, "admin.import_too_large")
