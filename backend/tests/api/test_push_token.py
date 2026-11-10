"""PUT/DELETE /me/push-token (Phase 2.8b): this session's Expo token only, a strict shape, a
per-account limit, and nothing for a session that has ended."""

import asyncio
import time
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.api import me as me_api
from labtrack.api.ratelimit import WINDOW_SECONDS
from labtrack.config import get_settings
from labtrack.db.sql import bound_text

from .conftest import ClientFactory, login_body, make_active_user

pytestmark = pytest.mark.db

URL = "/api/v1/me/push-token"


def _token() -> str:
    return f"ExponentPushToken[{uuid4().hex[:22]}]"


async def _login(c: AsyncClient, username: str) -> dict[str, str]:
    body = (await c.post("/api/v1/auth/login", json=login_body(username))).json()
    return {
        "Authorization": f"Bearer {body['access_token']}",
        "refresh": body["refresh_token"],
    }


def _h(session: dict[str, str]) -> dict[str, str]:
    return {"Authorization": session["Authorization"]}


async def _tokens(owner_engine: AsyncEngine, user: UUID) -> list[str | None]:
    async with owner_engine.connect() as conn:
        rows = (
            await conn.execute(
                bound_text(
                    "select push_token from sessions where user_id = :u order by created_at"
                ),
                {"u": user},
            )
        ).scalars()
        return list(rows)


async def test_the_token_goes_on_this_session_only_and_can_be_cleared(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    uid, username = await make_active_user(owner_engine)
    token = _token()
    async with client_from() as c:
        first, second = await _login(c, username), await _login(c, username)
        r = await c.put(URL, json={"token": token}, headers=_h(second))
        assert (r.status_code, r.content) == (204, b"")
        assert await _tokens(owner_engine, uid) == [None, token]
        assert (await c.put(URL, json={"token": None}, headers=_h(second))).status_code == 204
        assert await _tokens(owner_engine, uid) == [None, None]
        await c.put(URL, json={"token": token}, headers=_h(first))
        assert (await c.delete(URL, headers=_h(first))).status_code == 204
        assert await _tokens(owner_engine, uid) == [None, None]


async def test_the_phone_moves_to_the_account_now_signed_in(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    alice, alice_name = await make_active_user(owner_engine)
    bob, bob_name = await make_active_user(owner_engine)
    token = _token()
    async with client_from() as c:
        await c.put(URL, json={"token": token}, headers=_h(await _login(c, alice_name)))
        await c.put(URL, json={"token": token}, headers=_h(await _login(c, bob_name)))
    assert await _tokens(owner_engine, alice) == [None]
    assert await _tokens(owner_engine, bob) == [token]


@pytest.mark.parametrize(
    "body",
    [
        {"token": "https://evil.example/hook"},
        {"token": "ExponentPushToken[short]"},
        {"token": "ExponentPushToken[" + "a" * 101 + "]"},
        {"token": "ExponentPushToken[abc def ghi jk]"},
        {"token": 12345},
        {},
        {"token": _token(), "session_id": str(uuid4())},  # no other session can be named
    ],
)
async def test_a_malformed_body_is_422_and_is_not_echoed(
    owner_engine: AsyncEngine, client_from: ClientFactory, body: dict[str, object]
) -> None:
    uid, username = await make_active_user(owner_engine)
    async with client_from() as c:
        r = await c.put(URL, json=body, headers=_h(await _login(c, username)))
    assert r.status_code == 422
    if isinstance(body.get("token"), str):
        assert str(body["token"]) not in r.text
    assert await _tokens(owner_engine, uid) == [None]


async def test_signed_out_or_anonymous_gets_401(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    uid, username = await make_active_user(owner_engine)
    async with client_from() as c:
        assert (await c.put(URL, json={"token": _token()})).status_code == 401
        session = await _login(c, username)
        await c.post("/api/v1/auth/logout", json={"refresh_token": session["refresh"]})
        assert (await c.put(URL, json={"token": _token()}, headers=_h(session))).status_code == 401
        assert (await c.delete(URL, headers=_h(session))).status_code == 401
    assert await _tokens(owner_engine, uid) == [None]


async def test_registrations_are_limited_per_account(
    owner_engine: AsyncEngine, client_from: ClientFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, username = await make_active_user(owner_engine)
    limit = 2
    low = get_settings().model_copy(update={"rate_push_token_per_minute": limit})
    monkeypatch.setattr(me_api, "get_settings", lambda: low)
    async with client_from() as c:
        h = _h(await _login(c, username))
        # fixed one-minute windows: start well inside one, or the count splits across two
        if time.time() % WINDOW_SECONDS > WINDOW_SECONDS - 10:
            await asyncio.sleep(WINDOW_SECONDS - time.time() % WINDOW_SECONDS + 0.5)
        codes = [
            (await c.put(URL, json={"token": _token()}, headers=h)).status_code
            for _ in range(limit + 1)
        ]
    assert codes[:limit] == [204] * limit
    assert codes[limit] == 429
