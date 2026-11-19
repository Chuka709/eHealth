"""Links for someone without an account (0041; Phase 7.2, H37): made by the owner only, the
attempt counted before the PIN, locked after 5 wrong in a row or 10 in all, a session reads only
through its own functions, and a link ends with its maker's standing."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from labtrack.core.security import hash_password, new_opaque_token
from labtrack.db.sql import bound_text

from .conftest import as_user, make_patient, make_user, scalar

pytestmark = pytest.mark.db

PIN_HASH = hash_password("123456")


async def _consented(owner_engine: AsyncEngine, user: UUID) -> None:
    """The required consents a link's maker must hold (as the API asks before anything)."""
    async with owner_engine.connect() as conn, conn.begin():
        for kind in ("terms", "privacy", "sensitive_data"):
            await conn.execute(
                bound_text(
                    "insert into consents (user_id, kind, version, granted)"
                    " values (:u, :k, 'v1', true)"
                ),
                {"u": user, "k": kind},
            )


async def _owner(app_engine: AsyncEngine, owner_engine: AsyncEngine) -> tuple[UUID, UUID]:
    owner = await make_user(owner_engine)
    await _consented(owner_engine, owner)
    return owner, await make_patient(app_engine, owner)


async def _link(
    app_engine: AsyncEngine, owner: UUID, patient: UUID, *, max_views: int | None = None
) -> tuple[UUID, str]:
    _, token_hash = new_opaque_token()
    async with as_user(app_engine, owner) as conn:
        link: UUID = await scalar(
            conn,
            bound_text(
                "select create_share_link(:p, :t, :h, array['summary','labs'], null, null, 7, :m)"
            ),
            {"p": patient, "t": token_hash, "h": PIN_HASH, "m": max_views},
        )
    return link, token_hash


@asynccontextmanager
async def _anonymous(app_engine: AsyncEngine) -> AsyncGenerator[AsyncConnection]:
    async with as_user(app_engine, None) as conn:
        yield conn


async def _open(app_engine: AsyncEngine, token_hash: str) -> str | None:
    """An attempt, then the open a right PIN leads to: the session's hash, or None."""
    _, session_hash = new_opaque_token()
    async with _anonymous(app_engine) as conn:
        rows = (
            await conn.execute(
                bound_text("select * from share_link_attempt(:t)"), {"t": token_hash}
            )
        ).all()
        if not rows:
            return None
        opened = await scalar(
            conn,
            bound_text("select share_link_open(:t, :s)"),
            {"t": token_hash, "s": session_hash},
        )
    return session_hash if opened else None


async def _profile(app_engine: AsyncEngine, session: str) -> str | None:
    async with _anonymous(app_engine) as conn:
        name: str | None = await scalar(
            conn, bound_text("select share_profile(:s)"), {"s": session}
        )
    return name


async def test_only_the_owner_makes_lists_and_revokes_links(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, patient = await _owner(app_engine, owner_engine)
    stranger = await make_user(owner_engine)
    _, token_hash = new_opaque_token()
    for user in (stranger, None):
        async with as_user(app_engine, user) as conn:
            with pytest.raises(DBAPIError):
                await conn.execute(
                    bound_text(
                        "select create_share_link(:p, :t, :h, array['labs'], null, null, 7, null)"
                    ),
                    {"p": patient, "t": token_hash, "h": PIN_HASH},
                )
    link, _ = await _link(app_engine, owner, patient)
    async with as_user(app_engine, stranger) as conn:
        assert (
            await conn.execute(bound_text("select * from owner_share_links(:p)"), {"p": patient})
        ).all() == []
        assert not await scalar(conn, bound_text("select revoke_share_link(:l)"), {"l": link})
        for table in ("share_links", "share_sessions"):
            with pytest.raises(DBAPIError):
                await conn.execute(bound_text(f"select * from {table}"))  # noqa: S608
    async with as_user(app_engine, owner) as conn:
        [row] = (
            await conn.execute(bound_text("select * from owner_share_links(:p)"), {"p": patient})
        ).all()
        assert row.scopes == ["summary", "labs"]
        # no other sections, no longer than 30 days
        for scopes, days in ((["labs", "notes"], 7), (["labs"], 31)):
            with pytest.raises(DBAPIError):
                await conn.execute(
                    bound_text(
                        "select create_share_link(:p, :t, :h, cast(:s as text[]), null, null,"
                        " :d, null)"
                    ),
                    {
                        "p": patient,
                        "t": new_opaque_token()[1],
                        "h": PIN_HASH,
                        "s": scopes,
                        "d": days,
                    },
                )


async def test_attempts_are_counted_first_and_five_wrong_in_a_row_lock(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, patient = await _owner(app_engine, owner_engine)
    link, token_hash = await _link(app_engine, owner, patient)
    for _ in range(5):
        async with _anonymous(app_engine) as conn:
            row = (
                await conn.execute(
                    bound_text("select * from share_link_attempt(:t)"), {"t": token_hash}
                )
            ).one()
            assert row.link_id == link
            await conn.execute(bound_text("select share_link_failed(:l)"), {"l": link})
    assert await _open(app_engine, token_hash) is None
    async with as_user(app_engine, owner) as conn:
        [row] = (
            await conn.execute(bound_text("select * from owner_share_links(:p)"), {"p": patient})
        ).all()
        assert row.revoked_reason == "pin_locked"
        kinds = (
            (
                await conn.execute(
                    bound_text("select kind from notifications where patient_id = :p"),
                    {"p": patient},
                )
            )
            .scalars()
            .all()
        )
    assert kinds == ["share_link_locked"]
    # a signed-in user cannot use the anonymous functions
    async with as_user(app_engine, owner) as conn:
        with pytest.raises(DBAPIError):
            await conn.execute(
                bound_text("select * from share_link_attempt(:t)"), {"t": token_hash}
            )


async def test_right_pins_between_do_not_reset_the_total_of_wrong_ones(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, patient = await _owner(app_engine, owner_engine)
    link, token_hash = await _link(app_engine, owner, patient)
    for n in range(10):
        async with _anonymous(app_engine) as conn:
            await conn.execute(
                bound_text("select * from share_link_attempt(:t)"), {"t": token_hash}
            )
            await conn.execute(bound_text("select share_link_failed(:l)"), {"l": link})
        if n < 9:  # a right PIN after each wrong one
            assert await _open(app_engine, token_hash) is not None
    assert await _open(app_engine, token_hash) is None  # 10 wrong in all: locked


async def test_an_open_needs_the_token_and_a_counted_attempt(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, patient = await _owner(app_engine, owner_engine)
    _, token_hash = await _link(app_engine, owner, patient)
    async with _anonymous(app_engine) as conn:
        for token in (token_hash, new_opaque_token()[1]):
            assert not await scalar(
                conn,
                bound_text("select share_link_open(:t, :s)"),
                {"t": token, "s": new_opaque_token()[1]},
            )


async def test_a_session_reads_only_through_its_functions(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, patient = await _owner(app_engine, owner_engine)
    async with as_user(app_engine, owner) as conn:
        await conn.execute(
            bound_text(
                "insert into emergency_contacts (patient_id, client_id, name, phone)"
                " values (:p, :c, 'X', '+97699112233')"
            ),
            {"p": patient, "c": uuid4()},
        )
    link, token_hash = await _link(app_engine, owner, patient)
    session = await _open(app_engine, token_hash)
    assert session is not None
    assert await _profile(app_engine, session) is not None
    async with _anonymous(app_engine) as conn:
        await conn.execute(
            bound_text("select set_config('app.share_session', :s, true)"), {"s": session}
        )
        assert not await scalar(conn, bound_text("select can_read_patient(:p)"), {"p": patient})
        for table in ("patients", "emergency_contacts", "documents", "allergies", "vitals"):
            assert await scalar(conn, bound_text(f"select count(*) from {table}")) == 0  # noqa: S608
    # the owner revokes the link: the session sees nothing more
    async with as_user(app_engine, owner) as conn:
        assert await scalar(conn, bound_text("select revoke_share_link(:l)"), {"l": link})
    assert await _profile(app_engine, session) is None


async def test_a_link_ends_with_its_makers_standing(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, patient = await _owner(app_engine, owner_engine)
    _, reset_token = await _link(app_engine, owner, patient)
    _, other_token = await _link(app_engine, owner, patient)
    session = await _open(app_engine, reset_token)
    assert session is not None
    # an admin reset (or a password change) moves token_version: links and sessions end
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text("update users set token_version = token_version + 1 where id = :u"),
            {"u": owner},
        )
    assert await _profile(app_engine, session) is None
    assert await _open(app_engine, reset_token) is None
    assert await _open(app_engine, other_token) is None
    # a new link after the reset works until a required consent is withdrawn
    _, token_hash = await _link(app_engine, owner, patient)
    session = await _open(app_engine, token_hash)
    assert session is not None
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "insert into consents (user_id, kind, version, granted)"
                " values (:u, 'sensitive_data', 'v1', false)"
            ),
            {"u": owner},
        )
    assert await _profile(app_engine, session) is None


async def test_a_limit_of_opens_is_kept(app_engine: AsyncEngine, owner_engine: AsyncEngine) -> None:
    owner, patient = await _owner(app_engine, owner_engine)
    link, token_hash = await _link(app_engine, owner, patient, max_views=1)
    assert await _open(app_engine, token_hash) is not None
    assert await _open(app_engine, token_hash) is None
    async with as_user(app_engine, owner) as conn:
        views = (
            await conn.execute(bound_text("select * from owner_share_link_views(:l)"), {"l": link})
        ).all()
    assert len(views) == 1
